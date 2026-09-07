"""Geometría de Alinear caras. Su ciclo de vida pertenece a ToolSession."""

import math

import bpy
from mathutils import Matrix, Quaternion, Vector

from ..errors import BadPayload, CommandError
from .snap import query_face_frame


DEFAULTS = {"mode": "CONTACT", "pick_role": "SOURCE", "twist": "0", "gap": 0.0}


def controls(params):
    result = [
        {"id": "pick_role", "label": "Elegir cara", "type": "enum",
         "values": ["SOURCE", "TARGET"], "labels": {"SOURCE": "Fuente", "TARGET": "Destino"}},
        {"id": "mode", "label": "Acción", "type": "enum",
         "values": ["CONTACT", "ORIENT", "COPY_ROTATION"],
         "labels": {"CONTACT": "Juntar caras", "ORIENT": "Orientar caras", "COPY_ROTATION": "Copiar rotación"}},
    ]
    if params["mode"] != "COPY_ROTATION":
        result.append({"id": "twist", "label": "Giro", "type": "enum",
                       "values": ["0", "90", "180", "270"],
                       "labels": {str(i): f"{i}°" for i in (0, 90, 180, 270)}})
    if params["mode"] == "CONTACT":
        result.append({"id": "gap", "label": "Separación", "type": "float",
                       "unit": "length", "step": 0.001, "min": 0.0})
    return result


def parameters(changes, current=None):
    result = dict(DEFAULTS if current is None else current)
    if set(changes) - set(DEFAULTS):
        raise BadPayload("Unknown alignment parameter")
    result.update(changes)
    for key, allowed in (("mode", {"CONTACT", "ORIENT", "COPY_ROTATION"}),
                         ("pick_role", {"SOURCE", "TARGET"}), ("twist", {"0", "90", "180", "270"})):
        result[key] = str(result[key]).upper()
        if result[key] not in allowed:
            raise BadPayload(f"Invalid alignment {key}")
    try:
        result["gap"] = float(result["gap"])
    except (TypeError, ValueError):
        raise BadPayload("Invalid alignment gap") from None
    if not math.isfinite(result["gap"]) or result["gap"] < 0:
        raise BadPayload("Alignment gap must be finite and non-negative")
    return result


def face_world(face, matrix):
    points = [matrix @ Vector(p) for p in face["vertices"]]
    center = matrix @ Vector(face["center"])
    normal = matrix.to_3x3().inverted().transposed() @ Vector(face["normal"])
    normal.normalize()
    edges = [points[(i + 1) % len(points)] - p for i, p in enumerate(points)]
    tangent = max(edges, key=lambda edge: edge.length_squared)
    tangent -= normal * tangent.dot(normal)
    if tangent.length < 1e-9 or normal.length < 1e-9:
        raise CommandError("La cara no tiene una orientación válida", code="degenerate_face")
    tangent.normalize()
    size = max(edge.length for edge in edges)
    if any(abs((p-center).dot(normal)) > max(1e-6, size*1e-5) for p in points):
        raise CommandError("Elige una cara plana para alinear", code="nonplanar_face")
    return center, normal, tangent, points


def aligned_matrix(baseline, source, target, target_matrix, params):
    """Rotación rígida: conserva tamaño y reconstruye siempre desde baseline."""
    if params["mode"] == "COPY_ROTATION":
        rotation = (target_matrix.to_quaternion() @ baseline.to_quaternion().conjugated()).to_matrix()
    else:
        sc, sn, st, _ = face_world(source, baseline)
        tc, tn, tt, _ = face_world(target, target_matrix)
        desired_normal = -tn  # caras enfrentadas, los sólidos quedan a lados opuestos
        desired_tangent = Quaternion(tn, math.radians(float(params["twist"]))) @ tt
        source_basis = Matrix((st, sn.cross(st), sn)).transposed()
        target_basis = Matrix((desired_tangent, desired_normal.cross(desired_tangent), desired_normal)).transposed()
        rotation = target_basis @ source_basis.transposed()
    result = rotation.to_4x4() @ baseline
    result.translation = baseline.translation
    if params["mode"] == "CONTACT":
        result.translation = tc + tn * params["gap"] - rotation @ (sc-baseline.translation)
    return result


class Alignment:
    def __init__(self, obj):
        if any(not c.mute and c.influence > 0 for c in obj.constraints):
            raise CommandError("Desactiva las restricciones del objeto fuente antes de alinear", code="constrained_object")
        if abs(obj.matrix_world.determinant()) < 1e-12:
            raise CommandError("El objeto fuente tiene escala cero", code="singular_transform")
        self.obj = obj
        self.baseline = obj.matrix_world.copy()
        self.mesh = obj.data
        self.topology = (len(obj.data.vertices), len(obj.data.edges), len(obj.data.polygons))
        self.source = None
        self.target = None
        self.target_obj = None
        self.target_mesh = None
        self.target_topology = None
        self.candidate = None
        self.candidate_role = None

    def valid(self):
        try:
            if (self.obj.name not in bpy.data.objects or self.obj.mode != "OBJECT"
                    or self.obj.data != self.mesh or self.topology !=
                    (len(self.obj.data.vertices), len(self.obj.data.edges), len(self.obj.data.polygons))):
                return False
            if self.target_obj is not None:
                obj = self.target_obj
                return (obj.name in bpy.data.objects and obj.data == self.target_mesh
                        and obj.mode == "OBJECT" and self.target_topology ==
                        (len(obj.data.vertices), len(obj.data.edges), len(obj.data.polygons)))
            return True
        except (ReferenceError, RuntimeError):
            return False

    def restore(self):
        try:
            if self.obj.name in bpy.data.objects:
                self.obj.matrix_world = self.baseline
                bpy.context.view_layer.update()
        except ReferenceError:
            pass

    def preview(self, params):
        if self.source is None or self.target is None:
            return
        desired = aligned_matrix(self.baseline, self.source, self.target, self.target_obj.matrix_world, params)
        self.obj.matrix_world = desired
        bpy.context.view_layer.update()
        if any(abs(self.obj.matrix_world[i][j]-desired[i][j]) > 1e-4 for i in range(4) for j in range(4)):
            self.restore()
            raise CommandError("La jerarquía del objeto impide esta alineación exacta", code="unsupported_transform")

    def pick(self, payload, params):
        phase = str(payload.get("phase", "TAP")).upper()
        role = str(payload.get("role", params["pick_role"])).upper()
        if phase not in {"TAP", "UPDATE", "END", "CANCEL"} or role not in {"SOURCE", "TARGET"}:
            raise BadPayload("Invalid face-pick phase or role")
        if phase == "CANCEL":
            self.candidate = self.candidate_role = None
            return
        if role == "TARGET" and self.source is None:
            raise CommandError("Elige primero la cara fuente", code="missing_source")
        if phase != "END":
            query = dict(payload)
            if role == "SOURCE":
                query["include_objects"] = [self.obj.name]
            else:
                query["exclude_objects"] = [self.obj.name]
            self.candidate = query_face_frame(query)
            self.candidate_role = role
        if phase not in {"END", "TAP"} or self.candidate_role != role or self.candidate is None:
            return
        candidate = self.candidate
        if role == "SOURCE":
            self.source = candidate
            params["pick_role"] = "TARGET"
        else:
            target = bpy.data.objects.get(candidate["object"])
            if target is None or target == self.obj or target in self.obj.children_recursive:
                raise CommandError("El destino debe ser otro objeto independiente", code="invalid_target")
            self.target, self.target_obj = candidate, target
            self.target_mesh = target.data
            self.target_topology = (len(target.data.vertices), len(target.data.edges), len(target.data.polygons))
        self.candidate = self.candidate_role = None

    def status(self, params):
        ready = self.source is not None and self.target is not None
        instruction = (f"{self.obj.name} → {self.target_obj.name} · Confirma o ajusta" if ready else
                       f"Señala una cara de {self.obj.name}" if self.source is None else
                       "Señala la cara destino de otro objeto")
        if self.candidate is not None:
            instruction = "Suelta para fijar la cara " + ("fuente" if self.candidate_role == "SOURCE" else "destino")
        return {"input": "FACE_PAIR", "controls": controls(params), "instruction": instruction,
                "can_confirm": ready, "source_object": self.obj.name,
                "target_object": self.target_obj.name if self.target_obj is not None else None}

    def outlines(self):
        result = []
        if self.source:
            result.append(("SOURCE", [self.obj.matrix_world @ Vector(p) for p in self.source["vertices"]]))
        if self.target:
            result.append(("TARGET", [self.target_obj.matrix_world @ Vector(p) for p in self.target["vertices"]]))
        if self.candidate:
            obj = bpy.data.objects.get(self.candidate["object"])
            if obj:
                result.append(("CANDIDATE", [obj.matrix_world @ Vector(p) for p in self.candidate["vertices"]]))
        return result
