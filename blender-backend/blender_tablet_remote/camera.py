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

MIN_DISTANCE = 1e-9
MAX_DISTANCE = 100000.0

# Rango de profundidad del vídeo de la tablet.
#
# No se hereda el del viewport del PC: su valor por defecto (0,01 m a 1000 m) reparte
# el z-buffer sobre un rango 100.000 veces mayor que la pieza, y a partir de ahí las
# caras cercanas compiten por el mismo valor de profundidad — la malla se ve rota y con
# artefactos aunque la geometría esté perfecta. La proyección sigue heredando el FOV de
# la ventana (ver `projection_matrix`), así que el rayo del toque continúa coincidiendo
# con lo que se ve; lo único que cambia es dónde empieza y acaba la profundidad.
DEFAULT_CLIP_START = 0.01
DEFAULT_CLIP_END = 1000.0


class RemoteCamera:
    """Cámara orbital: un punto de interés, una orientación y una distancia."""

    def __init__(self):
        self.location = Vector((0.0, 0.0, 0.0))
        self.rotation = Quaternion((1.0, 0.0, 0.0, 0.0))
        self.distance = 10.0
        self._ortho_depth = self.distance * 4.0
        self._synced = False
        self.perspective = "PERSP"
        self.axis_view = None
        self.clip_start = DEFAULT_CLIP_START
        self.clip_end = DEFAULT_CLIP_END
        # Caché de matrices del frame en curso: (rv3d, window_matrix, perspectiva,
        # inversa). `project`/`ray` se llaman decenas de veces por frame (picking,
        # box/circle y captura) y reconstruir la cadena completa cada vez
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
        self.perspective = 'ORTHO' if getattr(rv3d, 'view_perspective', self.perspective) == 'ORTHO' else 'PERSP'
        self._ortho_depth = self.distance * 4.0
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
        """Se hereda el FOV de la región y se impone el rango de profundidad propio.

        El encuadre sigue viniendo de la ventana del PC: replicar el manejo de sensor
        y lente de Blender arriesgaría que el rayo del toque no coincidiese con lo que
        se ve. Pero el clipping sí es nuestro, porque el del PC está pensado para su
        pantalla y no para la escala de la pieza (ver `DEFAULT_CLIP_START`). Solo se
        reescribe la fila de profundidad, así que el FOV heredado queda intacto.
        """
        persp = self._perspective_window(rv3d)
        if self.perspective == "PERSP":
            return self._reclipped(persp)
        # Proyección ortográfica propia: conserva el encuadre que tenía la vista
        # perspectiva en el plano del pivote, por lo que el cambio no da saltos.
        width = 2.0 * self.distance / max(abs(persp[0][0]), 1e-9)
        height = 2.0 * self.distance / max(abs(persp[1][1]), 1e-9)
        # El zoom ortográfico cambia la ampliación, no atraviesa la pieza. El rango
        # de profundidad se centra en el pivote y conserva el volumen encuadrado.
        depth = max(min(self.clip_end, self.distance * 100.0), self._ortho_depth, self.distance * 4.0)
        near, far = self.distance - depth, self.distance + depth
        return Matrix(((2.0 / width, 0.0, 0.0, 0.0),
                       (0.0, 2.0 / height, 0.0, 0.0),
                       (0.0, 0.0, -2.0 / (far - near), -(far + near) / (far - near)),
                       (0.0, 0.0, 0.0, 1.0)))

    def _perspective_window(self, rv3d) -> Matrix:
        """FOV de la ventana, también cuando el PC muestra una vista ortográfica."""
        window = rv3d.window_matrix
        if abs(window[3][2]) > 1e-9:
            return window
        # m00/m11 ortográficos incluyen el zoom del PC. Recuperar el FOV evita
        # multiplicar ese zoom otra vez por la distancia de la tablet.
        distance = max(float(rv3d.view_distance), MIN_DISTANCE)
        return Matrix(((window[0][0] * distance, 0.0, 0.0, 0.0),
                       (0.0, window[1][1] * distance, 0.0, 0.0),
                       (0.0, 0.0, -1.0, -1.0),
                       (0.0, 0.0, -1.0, 0.0)))

    def _reclipped(self, window: Matrix) -> Matrix:
        """La matriz de la ventana con `clip_start`/`clip_end` en vez de los suyos."""
        # Acercarse a una pieza pequeña reduce también el rango de profundidad;
        # alejarse lo amplía. El preset nunca obliga a separar la cámara de la pieza.
        near, far = self._depth_range(self.distance)
        if far <= near:
            return window.copy()
        matrix = window.copy()
        matrix[2][2] = -(far + near) / (far - near)
        matrix[2][3] = -2.0 * far * near / (far - near)
        return matrix

    def _depth_range(self, distance):
        # Clipping follows the working distance, including submillimeter pieces.
        # A preset is an upper range, never a minimum distance from the model.
        distance = max(distance, MIN_DISTANCE)
        far = max(distance * 4.0, min(self.clip_end, distance * 100.0))
        near = max(min(self.clip_start, distance * .01), far / 10_000.0)
        return near, far

    def set_clipping(self, start: float, end: float) -> None:
        self.clip_start = float(start)
        self.clip_end = float(end)
        self._invalidate()

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
        """Órbita: yaw sobre el eje vertical de pantalla, pitch sobre el derecho.

        El yaw ya no es sobre el Z GLOBAL: al mirar desde debajo o desde atrás, el Z
        global deja de ser el "arriba" de la pantalla y el arrastre horizontal se
        invertía (y en la cenital no movía nada). Girar alrededor del eje vertical
        LOCAL (la "up" de la cámara) hace que el contenido acompañe al dedo
        independientemente del lado desde el que se mire.

        El signo se fijó finalmente con la percepción en tablet real: `dx` positivo
        (dedo a la derecha) necesita yaw negativo sobre el eje local para que el
        contenido acompañe al dedo. El pitch conserva el signo anterior sobre el eje
        derecho local.

        El signo del giro y las orientaciones BACK/BOTTOM dependen de esta convención.
        """
        right = self.rotation @ Vector((1.0, 0.0, 0.0))
        up = self.rotation @ Vector((0.0, 1.0, 0.0))
        yaw = Quaternion(up, -dx * sensitivity)
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

    def roll(self, angle: float) -> None:
        """Gira la cámara sobre su eje de visión (roll), en radianes.

        `angle` positivo rueda la cámara en el sentido del reloj visto desde detrás de
        ella, de modo que la escena gira en sentido contrario: con un gesto de rueda
        de dos dedos en el sentido horario (ángulo positivo) la escena acompaña al
        dedo girando también en el sentido horario.
        """
        forward = self.rotation @ Vector((0.0, 0.0, -1.0))
        roll_q = Quaternion(forward, angle)
        self.rotation = (roll_q @ self.rotation).normalized()
        self.axis_view = None
        self._invalidate()

    def look_at(self, center, points, rv3d) -> None:
        """Encuadra los límites en el 85 % de la vista sin cambiar la orientación."""
        self.location = Vector(center)
        inverse_rotation = self.rotation.inverted()
        offsets = [inverse_rotation @ (Vector(point) - self.location) for point in points]
        window = self._perspective_window(rv3d)
        x_scale, y_scale = abs(window[0][0]) / .85, abs(window[1][1]) / .85
        distance = max((max(abs(p.x) * x_scale, abs(p.y) * y_scale) +
                        (p.z if self.perspective == 'PERSP' else 0.0) for p in offsets), default=MIN_DISTANCE)
        if self.perspective == 'PERSP':
            near, _ = self._depth_range(distance)
            distance = max(distance, max((p.z for p in offsets), default=0.0) + near * 2.0)
        self.distance = max(MIN_DISTANCE, min(MAX_DISTANCE, distance))
        self._ortho_depth = max((p.length * 2.0 for p in offsets), default=self.distance * 4.0)
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
        if clip.w <= 0.0:
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
