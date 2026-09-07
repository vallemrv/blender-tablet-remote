"""Main-thread CAD transactions and Blender materialization."""
import copy
from contextlib import contextmanager
import math
import bpy
from mathutils import Vector
from . import document as model
from .kernel import kernel, world
from ..errors import BadPayload, CommandError
from ..bpy_utils import find_view3d, undo_push
from ..camera import camera

FEATURE_KEY = 'btr_cad_feature_id'
DOC_KEY = 'btr_cad_document_id'


class CadRuntime:
    def __init__(self):
        self.workspace = False
        self.active_sketch_id = None
        self.selection = None
        self.session = None
        self._scene = None
        self.workspace_owner = None
        self._hidden = []
        self._save_suspended = False
        self._empty = model.new_document()

    def reset(self):
        self.__init__()

    def doc(self):
        scene = bpy.context.scene
        identity = scene.as_pointer()
        if self._scene != identity:
            # Undo replaces RNA addresses. Keep the workspace, but never hold an
            # old scene preview; explicit file loads call reset_session().
            workspace, active = self.workspace, self.active_sketch_id
            hidden, owner = self._hidden, self.workspace_owner
            self.reset()
            self.workspace, self.active_sketch_id = workspace, active
            self._hidden, self.workspace_owner = hidden, owner
            self._scene = identity
        raw = scene.get(model.KEY)
        return model.loads(raw) if raw else copy.deepcopy(self._empty)

    def isolate(self):
        """Same hide_set technique as view.local, with a separate restoration set."""
        if not self.workspace or self._save_suspended:
            return
        doc = self.doc()
        for obj in bpy.context.view_layer.objects:
            if obj.get(DOC_KEY) != doc['id'] and not obj.hide_get() and not obj.hide_viewport:
                if obj.name not in self._hidden:
                    self._hidden.append(obj.name)
                obj.hide_set(True)

    def restore_visibility(self, *, clear=True):
        if self._scene == bpy.context.scene.as_pointer():
            for name in self._hidden:
                obj = bpy.context.view_layer.objects.get(name)
                if obj is not None:
                    obj.hide_set(False)
        if clear:
            self._hidden = []

    def leave(self):
        self.cancel()
        self.restore_visibility()
        self.workspace = False
        self.workspace_owner = None
        self._save_suspended = False

    def suspend_save(self):
        if self._save_suspended:
            return
        self.cancel()
        self.restore_visibility(clear=False)
        self._save_suspended = True

    def resume_save(self):
        if not self._save_suspended:
            return
        self._save_suspended = False
        if self.workspace and self._scene == bpy.context.scene.as_pointer():
            for name in self._hidden:
                obj = bpy.context.view_layer.objects.get(name)
                if obj is not None:
                    obj.hide_set(True)

    @contextmanager
    def saving(self):
        self.suspend_save()
        try:
            yield
        finally:
            self.resume_save()

    def persist(self, doc, *, advance=False):
        if advance:
            doc["revision"] = doc.get("revision", 0) + 1
        bpy.context.scene[model.KEY] = model.dumps(doc)
        self._empty = copy.deepcopy(doc)

    def objects(self, doc):
        return [o for o in bpy.context.scene.objects if o.get(DOC_KEY) == doc['id'] and o.get(FEATURE_KEY)]

    def rebuild(self, doc):
        """Evaluate every feature first, then swap meshes; errors leave old data."""
        scale = max(float(bpy.context.scene.unit_settings.scale_length), 1e-12)
        evaluated = []
        for feature in doc['features']:
            if feature['enabled']:
                sketch, entity = model.profile(doc, feature['profile_id'])
                verts, faces = kernel.extrude(sketch, entity, model.number(feature['depth'], positive=True))
                evaluated.append((feature, [tuple(c/scale for c in v) for v in verts], faces))
        objects = {o[FEATURE_KEY]:o for o in self.objects(doc)}
        keep = {f['id'] for f in doc['features']}
        for feature in doc['features']:
            if feature['id'] in objects:
                objects[feature['id']].hide_viewport = not feature['enabled']
                objects[feature['id']].hide_render = not feature['enabled']
        for feature, verts, faces in evaluated:
            identifier = feature['id']
            keep.add(identifier)
            mesh = bpy.data.meshes.new(feature['name'])
            mesh.from_pydata(verts, [], faces)
            mesh.update()
            obj = objects.get(identifier)
            if obj is None:
                obj = bpy.data.objects.new(feature['name'], mesh)
                bpy.context.scene.collection.objects.link(obj)
                obj[FEATURE_KEY], obj[DOC_KEY] = identifier, doc['id']
            else:
                old = obj.data
                obj.data = mesh
                if old.users == 0:
                    bpy.data.meshes.remove(old)
        for identifier,obj in objects.items():
            if identifier not in keep:
                old = obj.data
                bpy.data.objects.remove(obj, do_unlink=True)
                if old.users == 0:
                    bpy.data.meshes.remove(old)
        bpy.context.view_layer.update()

    def require_workspace(self):
        if not self.workspace:
            raise CommandError('Activa CAD antes de editar el documento', code='wrong_mode')

    def require(self, payload):
        if not self.session:
            raise CommandError('No hay preview CAD activa', code='no_session')
        if self.session['owner'] != payload.get('_client_id'):
            raise CommandError('La preview pertenece a otra conexión', code='session_owned')
        return self.session

    def cancel(self, restore=True):
        if self.session:
            original = self.session['baseline']
            self.session = None
            if restore and self._scene == bpy.context.scene.as_pointer():
                self.rebuild(original)
            self.selection = None

    def begin(self, payload, operation):
        self.require_workspace()
        if self.session:
            self.require(payload)
            self.cancel()
        from ..commands.sessions import cancel_transform, cancel_tool
        cancel_transform()
        cancel_tool()
        self.session = dict(id=model.uid('session'), owner=payload.get('_client_id'),
                            operation=operation, baseline=self.doc(), candidate=None)
        return self.session

    def commit(self, doc, label):
        self.rebuild(doc)
        self.persist(doc, advance=True)
        with self.saving():
            undo_push(label)

    def transaction(self, payload, change, label):
        self.require_workspace()
        if self.session:
            raise CommandError('Confirma o cancela la preview primero', code='session_active')
        doc = self.doc()
        change(doc)
        self.commit(doc,label)
        return self.status()

    def point(self, payload, plane):
        found = find_view3d()
        if found is None:
            raise CommandError('Se necesita un viewport para dibujar', code='no_viewport')
        u,v = model.number(payload.get('u')),model.number(payload.get('v'))
        if not (0 <= u <= 1 and 0 <= v <= 1):
            raise BadPayload('El punto debe estar dentro del viewport')
        rv3d = found[3]
        camera.sync_from_region(rv3d)
        origin, direction = camera.ray(u,v,rv3d)
        normal = Vector(world(plane,0,0,1))
        denom = direction.dot(normal)
        if abs(denom) < 1e-7:
            raise CommandError('El plano está de canto; vuelve a la vista del sketch', code='cad_plane_parallel')
        distance = -origin.dot(normal)/denom
        if distance < 0:
            raise CommandError('El plano queda detrás de la cámara', code='cad_plane_parallel')
        p = (origin + direction*distance) * bpy.context.scene.unit_settings.scale_length
        return {'XY':(p.x,p.y), 'XZ':(p.x,p.z), 'YZ':(p.y,p.z)}[plane]

    def focus(self, sketch):
        found = find_view3d()
        if found:
            camera.sync_from_region(found[3])
        normal = Vector(world(sketch['plane'],0,0,1))
        up = Vector(world(sketch['plane'],0,1,0))
        from mathutils import Matrix
        right = up.cross(normal)
        camera.rotation = Matrix((right,up,normal)).transposed().to_quaternion()
        bounds = [p for e in sketch['entities'] for p in model.outline(e)]
        scale = max(float(bpy.context.scene.unit_settings.scale_length),1e-12)
        if bounds:
            lo = [min(p[i] for p in bounds) for i in (0,1)]
            hi = [max(p[i] for p in bounds) for i in (0,1)]
            camera.location = Vector(world(sketch['plane'],(lo[0]+hi[0])/2,(lo[1]+hi[1])/2))/scale
            camera.distance = max(.15, max(hi[i]-lo[i] for i in (0,1))*2)/scale
        else:
            camera.location = Vector((0,0,0))
            camera.distance = .2/scale
        camera.perspective = 'ORTHO'
        camera.axis_view = None
        camera._synced = True
        camera._frame_cache = None

    def overlay(self, doc):
        if not self.workspace:
            return []
        found = find_view3d()
        if not found:
            return []
        camera.sync_from_region(found[3])
        scale = max(float(bpy.context.scene.unit_settings.scale_length),1e-12)
        result = []
        for sketch in doc['sketches']:
            if self.active_sketch_id and sketch['id'] != self.active_sketch_id:
                continue
            for e in sketch['entities']:
                points = [camera.project(Vector(world(sketch['plane'],*p))/scale, found[3]) for p in model.outline(e)]
                if any(p is None for p in points):
                    continue
                selected = bool(self.selection and self.selection['id'] in (e['id'],'profile_'+e['id']))
                result.append(dict(id=e['id'],points=points,closed=e['type']!='LINE',selected=selected))
        return result

    def status(self):
        try:
            doc = self.doc()
            self.isolate()
            session = self.session
            if self.active_sketch_id and not any(s['id']==self.active_sketch_id for s in doc['sketches']):
                self.active_sketch_id = None
            if session and session.get('preview'):
                doc = session['preview']
            return dict(version=1,workspace=self.workspace,isolated=bool(self.workspace),document=model.public(doc),
                        active_sketch_id=self.active_sketch_id,selection=self.selection,
                        session=dict(active=bool(session),id=session['id'] if session else None,
                                     operation=session['operation'] if session else None,
                                     depth=session.get('depth') if session else None,
                                     can_confirm=bool(session and session.get('candidate'))),
                        overlay=self.overlay(doc),error=None)
        except CommandError as exc:
            return dict(version=1,workspace=self.workspace,isolated=bool(self.workspace),document=None,active_sketch_id=None,
                        selection=None,session=dict(active=False,id=None,operation=None),overlay=[],error=exc.message)


runtime = CadRuntime()
