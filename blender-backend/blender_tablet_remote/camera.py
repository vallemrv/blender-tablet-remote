"""Cámara de la tablet, independiente de la ventana de Blender.

Por qué existe: modificar `rv3d` (la cámara del viewport del PC) desde el timer marca
la región para redibujar, y ese redibujado hunde el bucle de eventos de Blender de
~48 Hz a 1 Hz, del que no se recupera. Medido, con y sin captura de vídeo:

    reposo ............ 16 fps / pump 48 Hz
    orbitando ......... 1 fps  / pump  1 Hz     <- tocando rv3d
    tras soltar ....... 1 fps  / pump  1 Hz     <- no se recupera

Llevando nosotros la cámara y pasándole la matriz a `draw_view3d`, la ventana de
Blender ni se entera y el ritmo se mantiene (medido: 23 fps *mientras* se orbita).

Efecto secundario buscado: la tablet y el PC pasan a tener puntos de vista
independientes. Quien esté delante del monitor puede seguir trabajando sin que la
tablet le mueva la cámara.

Todo esto se toca solo desde el hilo principal.
"""

from __future__ import annotations

import math

from mathutils import Matrix, Quaternion, Vector

MIN_DISTANCE = 0.001
MAX_DISTANCE = 100000.0


class RemoteCamera:
    """Cámara orbital: un punto de interés, una orientación y una distancia."""

    def __init__(self):
        self.location = Vector((0.0, 0.0, 0.0))
        self.rotation = Quaternion((1.0, 0.0, 0.0, 0.0))
        self.distance = 10.0
        self._synced = False
        self.perspective = "PERSP"
        self.axis_view = None
        # Caché de matrices del frame en curso: (rv3d, window_matrix, perspectiva,
        # inversa). `project`/`ray` se llaman decenas de veces por frame (picking,
        # box/circle, gizmo, captura) y reconstruir la cadena completa cada vez
        # dominaba el allocator del hilo principal. Se invalida con cualquier cambio
        # de cámara y si la ventana del PC cambia su window_matrix (redimensionado).
        self._frame_cache = None

    # ------------------------------------------------------------ ciclo de vida

    def sync_from_region(self, rv3d, force: bool = False) -> None:
        """Copia la vista del PC. Solo la primera vez, para arrancar donde él está."""
        if self._synced and not force:
            return
        self.location = rv3d.view_location.copy()
        self.rotation = rv3d.view_rotation.copy()
        self.distance = float(rv3d.view_distance)
        self._synced = True
        self._frame_cache = None

    def reset(self) -> None:
        self._synced = False
        self.axis_view = None
        self._frame_cache = None

    # ---------------------------------------------------------------- matrices

    def view_matrix(self) -> Matrix:
        """Igual que construye Blender la suya: pivote, giro y retroceso."""
        return (
            Matrix.Translation(self.location)
            @ self.rotation.to_matrix().to_4x4()
            @ Matrix.Translation((0.0, 0.0, self.distance))
        ).inverted()

    def projection_matrix(self, rv3d) -> Matrix:
        """Se hereda la de la región: así imagen y raycast usan exactamente la misma.

        Construirla por nuestra cuenta obligaría a replicar el manejo de sensor y
        lente de Blender, con el riesgo de que el rayo del toque no coincidiese con
        lo que se ve. Depende del tamaño de la ventana del PC, que es aceptable.
        """
        if self.perspective == "PERSP":
            return rv3d.window_matrix.copy()
        # Proyección ortográfica propia: conserva el encuadre que tenía la vista
        # perspectiva en el plano del pivote, por lo que el cambio no da saltos.
        persp = rv3d.window_matrix
        width = 2.0 * self.distance / max(abs(persp[0][0]), 1e-9)
        height = 2.0 * self.distance / max(abs(persp[1][1]), 1e-9)
        near, far = 0.001, MAX_DISTANCE * 2.0
        return Matrix(((2.0 / width, 0.0, 0.0, 0.0),
                       (0.0, 2.0 / height, 0.0, 0.0),
                       (0.0, 0.0, -2.0 / (far - near), -(far + near) / (far - near)),
                       (0.0, 0.0, 0.0, 1.0)))

    def perspective_matrix(self, rv3d) -> Matrix:
        """Proyección @ vista, con caché por frame (ver `_frame_cache`)."""
        cache = self._frame_cache
        window = rv3d.window_matrix
        if cache is not None and cache[0] is rv3d and cache[1] == window:
            return cache[2]
        persp = self.projection_matrix(rv3d) @ self.view_matrix()
        self._frame_cache = (rv3d, window.copy(), persp, None)
        return persp

    def _perspective_inverse(self, rv3d) -> Matrix:
        cache = self._frame_cache
        if cache is not None and cache[3] is not None and cache[0] is rv3d:
            return cache[3]
        inverse = self.perspective_matrix(rv3d).inverted()
        cache = self._frame_cache
        if cache is not None and cache[0] is rv3d:
            self._frame_cache = (cache[0], cache[1], cache[2], inverse)
        return inverse

    def _invalidate(self) -> None:
        self._frame_cache = None

    # ------------------------------------------------------------- navegación

    def orbit(self, dx: float, dy: float, sensitivity: float) -> None:
        """Órbita tipo turntable: yaw sobre Z global, pitch sobre el eje derecha.

        El signo es el que hace que, en la vista por defecto (la que el usuario ve al
        conectar), la escena acompañe al dedo: `dx` positivo (dedo a la derecha) mueve
        la escena hacia la derecha, `dy` positivo (dedo abajo) hacia abajo.

        OJO al medir esto: es un turntable alrededor del Z GLOBAL, así que el sentido
        EN PANTALLA depende de la vista (desde FRONT/BACK se invierte respecto a la
        vista por defecto, porque el "derecha" de pantalla cambia de lado). El signo
        se decide y se comprueba SIEMPRE en la vista por defecto, nunca en una vista
        de eje ni en la cenital. Se invirtió dos veces por medir desde esas vistas.
        """
        yaw = Quaternion(Vector((0.0, 0.0, 1.0)), -dx * sensitivity)
        right = self.rotation @ Vector((1.0, 0.0, 0.0))
        pitch = Quaternion(right, -dy * sensitivity)
        self.rotation = (yaw @ pitch @ self.rotation).normalized()
        self.axis_view = None
        self._invalidate()

    def pan(self, dx: float, dy: float, projection: Matrix | None = None) -> None:
        """Desplaza de forma que el punto bajo el dedo se queda bajo el dedo.

        En vez de una sensibilidad a ojo, se deduce de la propia proyección cuánto
        mundo abarca la pantalla a esta distancia: para una matriz en perspectiva, el
        ancho visible es 2·distancia/m00 y el alto 2·distancia/m11. `dx` y `dy` vienen
        normalizados por ancho y alto respectivamente, así que el arrastre coincide
        con el movimiento real de la escena.
        """
        right = self.rotation @ Vector((1.0, 0.0, 0.0))
        up = self.rotation @ Vector((0.0, 1.0, 0.0))
        span_x, span_y = self.screen_span(projection)
        self.location = self.location - right * (dx * span_x) + up * (dy * span_y)
        self._invalidate()

    def screen_span(self, projection: Matrix | None) -> tuple[float, float]:
        """Cuánto mundo abarca la pantalla completa a la distancia actual."""
        if projection is not None and abs(projection[0][0]) > 1e-9 and abs(projection[1][1]) > 1e-9:
            multiplier = self.distance if self.perspective == "PERSP" else 1.0
            return (2.0 * multiplier / abs(projection[0][0]),
                    2.0 * multiplier / abs(projection[1][1]))
        return self.distance, self.distance

    def zoom(self, factor: float) -> None:
        self.distance = max(MIN_DISTANCE, min(MAX_DISTANCE, self.distance / factor))
        self._invalidate()

    def look_at(self, center, radius: float, fov: float = 0.85) -> None:
        """Encuadra una esfera sin cambiar la orientación."""
        self.location = Vector(center)
        self.distance = max(MIN_DISTANCE, min(MAX_DISTANCE, max(radius, 1e-3) / max(1e-3, math.sin(fov / 2))))
        self._invalidate()

    def set_axis_view(self, name: str) -> None:
        """Vistas ortográficas estándar, en cuaterniones de vista de Blender."""
        quarter = math.sqrt(0.5)
        half = 0.5
        views = {
            "FRONT": Quaternion((quarter, quarter, 0.0, 0.0)),
            "BACK": Quaternion((0.0, 0.0, quarter, quarter)),
            "RIGHT": Quaternion((half, half, half, half)),
            "LEFT": Quaternion((half, half, -half, -half)),
            "TOP": Quaternion((1.0, 0.0, 0.0, 0.0)),
            "BOTTOM": Quaternion((0.0, 1.0, 0.0, 0.0)),
        }
        if name in views:
            self.rotation = views[name].normalized()
            self.axis_view = name
            self._invalidate()

    # ------------------------------------------------ proyección y des-proyección

    def project(self, point, rv3d) -> list[float] | None:
        """Punto del mundo -> (u, v) 0..1 con origen arriba-izquierda, o None si queda detrás."""
        clip = self.perspective_matrix(rv3d) @ Vector((point[0], point[1], point[2], 1.0))
        if clip.w <= 1e-6:
            return None
        return [(clip.x / clip.w + 1.0) * 0.5, (1.0 - clip.y / clip.w) * 0.5]

    def ray(self, u: float, v: float, rv3d) -> tuple[Vector, Vector]:
        """(u, v) 0..1 arriba-izquierda -> (origen, dirección) del rayo en el mundo."""
        inverse = self._perspective_inverse(rv3d)
        ndc_x = u * 2.0 - 1.0
        ndc_y = 1.0 - v * 2.0

        near = inverse @ Vector((ndc_x, ndc_y, -1.0, 1.0))
        far = inverse @ Vector((ndc_x, ndc_y, 1.0, 1.0))

        if abs(near.w) < 1e-9:
            raise ValueError("La matriz de proyección no es invertible en el plano cercano")
        origin = Vector(near[:3]) / near.w

        # Blender sitúa el plano lejano en el infinito, así que ahí w vale 0: ese
        # punto homogéneo ya *es* una dirección y dividir por w reventaría.
        if abs(far.w) < 1e-9:
            direction = Vector(far[:3]).normalized()
        else:
            direction = (Vector(far[:3]) / far.w - origin).normalized()
        return origin, direction

    # -------------------------------------------------------------------- estado

    def as_dict(self) -> dict:
        return {
            "location": list(self.location),
            "rotation": list(self.rotation),
            "distance": self.distance,
            "perspective": self.perspective,
            "axis_view": self.axis_view,
        }

    def apply(self, location=None, rotation=None, distance=None, perspective=None) -> None:
        if location is not None:
            self.location = Vector(location)
        if rotation is not None:
            self.rotation = Quaternion(rotation).normalized()
            self.axis_view = None
        if distance is not None:
            self.distance = max(MIN_DISTANCE, min(MAX_DISTANCE, float(distance)))
        if perspective is not None:
            self.perspective = perspective
        if location is not None or rotation is not None or distance is not None or perspective is not None:
            self._invalidate()


# Única instancia: la vista de la tablet.
camera = RemoteCamera()
