"""Main-thread CAD transactions and Blender materialization."""
import copy
from contextlib import contextmanager
import math
import bpy
from mathutils import Vector
from . import document as model
from .kernel import world, ExtrusionPreviewCache, operand as extrusion_operand
from .jobs import Calculation, blocking
from .editable_mesh import clean_mesh
from . import sketch as sketch_geometry
from ..errors import BadPayload, CommandError
from ..bpy_utils import find_view3d, undo_push
from ..camera import camera

FEATURE_KEY = 'btr_cad_feature_id'
DOC_KEY = 'btr_cad_document_id'
BODY_KEY = 'btr_cad_body_id'
COPY_SOURCE_KEY = 'btr_cad_copy_source'
PRISM_KEY = 'btr_cad_depth_prism'


def mesh_copy(obj):
    """Independent native mesh and modifier stack, without CAD ownership."""
    copy=obj.copy()
    owned_mesh = None
    try:
        owned_mesh = obj.data.copy()
        owned_mesh.name = obj.data.name + ' · editable'
        copy.data = owned_mesh
        clean_mesh(owned_mesh)
        copy.name=obj.name+' · malla'
        for key in (FEATURE_KEY,DOC_KEY,BODY_KEY,COPY_SOURCE_KEY):
            if key in copy: del copy[key]
        copy.hide_viewport=False;copy.hide_render=False
        return copy
    except Exception:
        bpy.data.objects.remove(copy)
        if owned_mesh is not None and owned_mesh.users == 0:
            bpy.data.meshes.remove(owned_mesh)
        raise


def archive_copy_sources(objects):
    """Keep design bodies available in CAD without overlapping their editable copy."""
    for obj in objects:
        obj[COPY_SOURCE_KEY]=True
        obj.hide_set(True);obj.hide_render=True


class CadRuntime:
    def __init__(self):
        self.workspace = False
        self.active_sketch_id = None
        self.selection = None
        self.session = None
        self._scene = None
        self.workspace_owner = None
        self._hidden = []
        self._shown = []
        self._save_suspended = False
        self._empty = model.new_document()
        self.step = .001
        self.increment = True
        self.construction = False
        self.active_body_id = None
        self.show_scene = False
        self.section = False
        # Projection of the face-on sketch view; orbit stays locked in both.
        self.sketch_projection = 'ORTHO'
        self._solid_view = None
        self.rollback_id = None
        self._extrusion_cache = ExtrusionPreviewCache()
        self._solids = {}
        self._evaluations = {}
        self._baseline_evaluation = {}
        self._current_evaluation = {}
        self._epoch = 0
        self._materialized = {}
        from .surface import SurfaceSelection
        self.surface = SurfaceSelection()

    def reset(self):
        from .worker import worker
        from .evaluation import evaluator
        worker.stop()
        evaluator.__init__()
        epoch = self._epoch + 1
        self.__init__()
        self._epoch = epoch
        self.sync_section(None)

    def doc(self):
        scene = bpy.context.scene
        identity = scene.as_pointer()
        if self._scene != identity:
            # Undo replaces RNA addresses. Keep the workspace, but never hold an
            # old scene preview; explicit file loads call reset_session().
            workspace, active = self.workspace, self.active_sketch_id
            settings={k:getattr(self,k) for k in ("active_body_id","step","increment","construction","show_scene","section","sketch_projection","_solid_view","rollback_id")}
            hidden, shown, owner = self._hidden, self._shown, self.workspace_owner
            self.reset()
            self.workspace, self.active_sketch_id = workspace, active
            for key,value in settings.items(): setattr(self,key,value)
            self._hidden, self._shown, self.workspace_owner = hidden, shown, owner
            self._scene = identity
        raw = scene.get(model.KEY)
        return model.loads(raw) if raw else copy.deepcopy(self._empty)

    def isolate(self):
        """Same hide_set technique as view.local, with a separate restoration set."""
        if not self.workspace or self._save_suspended:
            return
        doc = self.doc()
        for obj in bpy.context.view_layer.objects:
            if obj.get(DOC_KEY)==doc['id'] and obj.get(COPY_SOURCE_KEY) and obj.hide_get():
                if obj.name not in self._shown: self._shown.append(obj.name)
                obj.hide_set(False)
            elif not self.show_scene and obj.get(DOC_KEY) != doc['id'] and not obj.hide_get() and not obj.hide_viewport:
                if obj.name not in self._hidden:
                    self._hidden.append(obj.name)
                obj.hide_set(True)

    def restore_visibility(self, *, clear=True):
        if self._scene == bpy.context.scene.as_pointer():
            for name in self._hidden:
                obj = bpy.context.view_layer.objects.get(name)
                if obj is not None:
                    obj.hide_set(False)
            for name in self._shown:
                obj = bpy.context.view_layer.objects.get(name)
                if obj is not None: obj.hide_set(True)
        if clear:
            self._hidden = []
            self._shown = []

    def leave(self):
        self.cancel()
        self.surface.clear()
        self.restore_visibility()
        self.workspace = False
        self.workspace_owner = None
        self._save_suspended = False
        self.rollback_id = None
        self.sync_section(None)

    def sync_section(self, sketch):
        """Section the video at the open sketch plane while the option is on."""
        from ..camera import camera
        if not (self.workspace and self.section and sketch):
            camera.set_section(None); return
        f=model.frame(sketch)
        scale=max(float(bpy.context.scene.unit_settings.scale_length),1e-12)
        camera.set_section(([v/scale for v in f['origin']],f['normal']))

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
            for name in self._shown:
                obj = bpy.context.view_layer.objects.get(name)
                if obj is not None: obj.hide_set(False)

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

    def bar(self, doc=None):
        """Validated rollback node: None means the whole stack is visible."""
        if not self.rollback_id:
            return None
        doc = self.doc() if doc is None else doc
        if any(n['id'] == self.rollback_id for n in model.history(doc)):
            return self.rollback_id
        self.rollback_id = None
        return None

    def rebuild(self, doc, *, limit=None, extrusion_cache=None):
        return blocking(self.rebuild_steps(doc, limit=limit, extrusion_cache=extrusion_cache))

    def rebuild_steps(self, doc, *, limit=None, extrusion_cache=None):
        """Evaluate snapshots off-process; publish compact geometry on the pump."""
        model.resolve_supports(doc)
        scale = max(float(bpy.context.scene.unit_settings.scale_length), 1e-12)
        from .evaluation import geometry_key
        key = geometry_key(doc, limit, scale)
        cached = self._evaluations.get(key)
        if cached is None and not any(f['enabled'] for f in doc['features']):
            cached = dict(display={}, tips={}, solids={}, profiles={})
        if cached is None:
            epoch, scene, raw = self._epoch, bpy.context.scene.as_pointer(), bpy.context.scene.get(model.KEY)
            cached = yield Calculation(operation='evaluate', doc=copy.deepcopy(doc), limit=limit, scale=scale)
            if (epoch != self._epoch or scene != bpy.context.scene.as_pointer()
                    or raw != bpy.context.scene.get(model.KEY)):
                raise CommandError('Cálculo CAD cancelado', code='cad_cancelled')
        self._evaluations = {key: cached, **self._baseline_evaluation}
        self._current_evaluation = {key: cached}
        self._solids = cached['solids']
        self._extrusion_cache.entries = cached['profiles']
        if extrusion_cache is not None:
            extrusion_cache.entries = cached['profiles'].copy()
        self._publish(doc, cached)

    def _publish(self, doc, evaluated):
        from .surface import stamp
        self.drop_prisms()
        display, tips = evaluated['display'], evaluated['tips']
        existing=self.objects(doc)
        feature_bodies={f['id']:f['body_id'] for f in doc['features']}
        retained=set()
        for body in doc['bodies']:
            identifier=body['id']
            candidates=[o for o in existing if o.get(BODY_KEY,feature_bodies.get(o.get(FEATURE_KEY)))==identifier]
            obj=next((o for o in candidates if o.get(BODY_KEY)==identifier),None) or next(iter(candidates),None)
            if identifier not in display:
                if obj is not None and any(f['body_id']==identifier for f in doc['features']):
                    obj.hide_viewport=True; obj.hide_render=True; retained.add(obj.as_pointer())
                continue
            signature,(vertices,faces)=display[identifier]
            record=(obj.as_pointer(),obj.data.as_pointer(),signature,stamp(obj)) if obj else None
            if record is None or self._materialized.get(identifier)!=record:
                obj = self._paint(obj, vertices, faces)
                self._materialized[identifier]=(obj.as_pointer(),obj.data.as_pointer(),signature,stamp(obj))
            obj.name=body['name']
            obj[FEATURE_KEY]=tips[identifier];obj[DOC_KEY]=doc['id'];obj[BODY_KEY]=identifier
            obj.hide_viewport=False;obj.hide_render=bool(obj.get(COPY_SOURCE_KEY))
            retained.add(obj.as_pointer())
        for obj in existing:
            if obj.as_pointer() not in retained:
                old=obj.data;bpy.data.objects.remove(obj,do_unlink=True)
                if old.users==0:bpy.data.meshes.remove(old)
        self._materialized = {key: value for key, value in self._materialized.items()
                              if key in {body['id'] for body in doc['bodies']}}
        bpy.context.view_layer.update()

    def drop_prisms(self):
        """Remove the light stylus prism. A settled preview uses the real solid."""
        for obj in list(bpy.data.objects):
            if not obj.get(PRISM_KEY):
                continue
            mesh = obj.data
            bpy.data.objects.remove(obj, do_unlink=True)
            if mesh is not None and mesh.users == 0:
                bpy.data.meshes.remove(mesh)
        if self.session:
            self.session.pop('fast', None)
            self.session.pop('fast_sign', None)

    def _paint(self, obj, vertices, faces):
        mesh = obj.data if obj is not None else None
        flat = [c for v in vertices for c in v]
        if mesh is not None and len(mesh.vertices) == len(vertices) and len(mesh.polygons) == len(faces) and all(tuple(p.vertices) == tuple(f) for p, f in zip(mesh.polygons, faces)):
            mesh.vertices.foreach_set('co', flat)
            mesh.update()
            obj.update_tag()
            return obj
        new = bpy.data.meshes.new('CAD preview' if obj is None else obj.name)
        new.from_pydata(vertices, [], faces)
        new.update()
        if obj is None:
            obj = bpy.data.objects.new('CAD preview', new)
            bpy.context.scene.collection.objects.link(obj)
        else:
            old = obj.data
            obj.data = new
            if old.users == 0:
                bpy.data.meshes.remove(old)
        return obj

    def fast_depth(self, session):
        """Move the prism with the stylus. The exact boolean waits until the pen lifts.

        A first extrusion only stretches its cached display mesh. A later extrude
        or a cut keeps the previous solid and shows the moving profile, so the
        main thread is not blocked by a boolean on every sample.
        """
        doc = session['preview']
        feature = model.find(doc, 'features', session['feature_id'])
        sketch, entity = model.profile(doc, feature['profile_id'])
        cut = feature['type'] == 'CUT'
        signed = -feature['depth'] if cut else feature['depth']
        vertices, faces = extrusion_operand(session['extrusion_cache'], sketch, entity, feature)
        scale = max(float(bpy.context.scene.unit_settings.scale_length), 1e-12)
        vertices = [tuple(c / scale for c in v) for v in vertices]
        previous = None
        for node in model.history(doc):
            if node['id'] == feature['id']:
                break
            if node.get('kind') == 'FEATURE' and node.get('enabled') and node.get('body_id') == feature['body_id']:
                previous = node['id']
        body = next((o for o in self.objects(doc) if o.get(BODY_KEY) == feature['body_id']), None)
        if previous is None and not cut:
            if body is None:
                raise CommandError('No hay sólido que estirar', code='cad_dependency')
            self.drop_prisms()
            self._paint(body, vertices, faces)
            return
        if not session.get('fast'):
            solid = self._solids.get(previous) if previous else None
            if previous and (solid is None or body is None):
                raise CommandError('No hay sólido anterior para la preview', code='cad_dependency')
            if previous:
                pred_vertices, pred_faces = solid[1]
                self._paint(body, [tuple(c / scale for c in v) for v in pred_vertices], pred_faces)
            session['fast'] = True
        if cut:
            # The removed volume is drawn as the translucent cut ghost, never as an
            # opaque object hiding the solid it cuts.
            return
        sign = -1 if signed < 0 else 1
        prism = next((o for o in bpy.data.objects if o.get(PRISM_KEY)), None)
        if prism is not None and session.get('fast_sign') != sign:
            mesh = prism.data
            bpy.data.objects.remove(prism, do_unlink=True)
            if mesh is not None and mesh.users == 0:
                bpy.data.meshes.remove(mesh)
            prism = None
        prism = self._paint(prism, vertices, faces)
        prism[PRISM_KEY] = True
        prism[DOC_KEY] = doc['id']
        prism.hide_viewport = False
        prism.hide_render = False
        prism.hide_set(False)
        session['fast_sign'] = sign

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
        from .worker import worker
        if worker.pending:
            worker.stop()
        self._epoch += 1
        self.drop_prisms()
        if self.session:
            session=self.session
            original = session['baseline']
            self.session = None
            if restore and self._scene == bpy.context.scene.as_pointer():
                if not session.get('annotation_id') and session['operation']!='PLANE' and (session['operation']!='DRAG' or session.get('preview')): self.rebuild(original, limit=self.bar(original))
            self.selection = copy.deepcopy(session.get('selection_before')) if session['operation']=='DRAG' and restore else None
        self._baseline_evaluation = {}
        self._evaluations = self._current_evaluation.copy()

    def begin(self, payload, operation):
        self.require_workspace()
        if self.session:
            self.require(payload)
            self.cancel()
        from ..commands.sessions import cancel_transform, cancel_tool
        cancel_transform()
        cancel_tool()
        baseline = self.doc()
        from .evaluation import geometry_key
        scale = max(float(bpy.context.scene.unit_settings.scale_length), 1e-12)
        key = geometry_key(baseline, self.bar(baseline), scale)
        cached = self._evaluations.get(key)
        if cached is None:
            # On the first session after loading, restoring the published solid
            # must not synchronously reevaluate its entire operation history.
            display, tips = {}, {}
            for obj in self.objects(baseline):
                body = obj.get(BODY_KEY)
                if body and not obj.hide_viewport:
                    display[body] = (model.uid('baseline'), (
                        [tuple(v.co) for v in obj.data.vertices],
                        [tuple(p.vertices) for p in obj.data.polygons]))
                    tips[body] = obj[FEATURE_KEY]
            cached = dict(display=display, tips=tips, solids={}, profiles={})
        self._baseline_evaluation = {key: cached}
        self._evaluations[key] = cached
        self.session = dict(id=model.uid('session'), owner=payload.get('_client_id'),
                            operation=operation, baseline=baseline, candidate=None)
        return self.session

    def commit(self, doc, label, *, geometry=True):
        return blocking(self.commit_steps(doc, label, geometry=geometry))

    def commit_steps(self, doc, label, *, geometry=True):
        if geometry: yield from self.rebuild_steps(doc, limit=self.bar(doc))
        self.persist(doc, advance=True)
        with self.saving():
            undo_push(label)

    def transaction(self, payload, change, label, *, geometry=True):
        return blocking(self.transaction_steps(payload, change, label, geometry=geometry))

    def transaction_steps(self, payload, change, label, *, geometry=True):
        self.require_workspace()
        if self.session:
            raise CommandError('Confirma o cancela la preview primero', code='session_active')
        doc = self.doc()
        change(doc)
        yield from self.commit_steps(doc,label,geometry=geometry)
        return self.status()

    def point(self, payload, plane, offset=None):
        found = find_view3d()
        if found is None:
            raise CommandError('Se necesita un viewport para dibujar', code='no_viewport')
        u,v = model.number(payload.get('u')),model.number(payload.get('v'))
        if not (0 <= u <= 1 and 0 <= v <= 1):
            raise BadPayload('El punto debe estar dentro del viewport')
        rv3d = found[3]
        camera.sync_from_region(rv3d)
        origin, direction = camera.ray(u,v,rv3d)
        active = next((s for s in self.doc()['sketches'] if s['id']==self.active_sketch_id),{})
        sketch=plane if isinstance(plane,dict) else dict(plane=plane,offset=active.get('offset',0) if offset is None else offset)
        basis=model.frame(sketch)
        normal = Vector(basis['normal'])
        denom = direction.dot(normal)
        if abs(denom) < 1e-7:
            raise CommandError('El plano está de canto; vuelve a la vista del sketch', code='cad_plane_parallel')
        plane_origin=Vector(basis['origin']) / max(bpy.context.scene.unit_settings.scale_length,1e-12)
        distance = (plane_origin-origin).dot(normal)/denom
        if distance < 0:
            raise CommandError('El plano queda detrás de la cámara', code='cad_plane_parallel')
        p = (origin + direction*distance) * bpy.context.scene.unit_settings.scale_length
        local=p-Vector(basis['origin'])
        return local.dot(Vector(basis['x'])),local.dot(Vector(basis['y']))

    def enter_sketch(self, sketch):
        found=find_view3d()
        if found: camera.sync_from_region(found[3])
        if self.active_sketch_id is None: self._solid_view=camera.as_dict()
        self.active_sketch_id=sketch['id']; self.active_body_id=sketch.get('body_id')
        self.selection=None; self.surface.mode='PROFILE'; self.surface.clear()
        self.focus(sketch)

    def solid_view(self, *, frame=True):
        """End plane editing and return to an orbitable view of the visible result."""
        found=find_view3d()
        if found: camera.sync_from_region(found[3])
        previous=self._solid_view
        was_editing=self.active_sketch_id is not None
        self.active_sketch_id=None; self._solid_view=None
        self.surface.mode='PROFILE'; self.surface.clear()
        if previous: camera.apply(**{k:previous[k] for k in ('location','rotation','distance','perspective')})
        elif was_editing:
            from mathutils import Euler
            camera.apply(rotation=Euler((math.radians(60),0,math.radians(45))).to_quaternion(),perspective='PERSP')
        # A stored plane-aligned view is still flat: provide an oblique overview.
        direction=camera.rotation@Vector((0,0,1))
        if max(abs(v) for v in direction)>.999:
            from mathutils import Euler
            camera.apply(rotation=Euler((math.radians(60),0,math.radians(45))).to_quaternion())
        if frame:
            doc=self.doc()
            targets=[o for o in self.objects(doc) if o.visible_get()]
            body_features={f['id'] for f in doc['features'] if f.get('body_id')==self.active_body_id}
            body_targets=[o for o in targets if o.get(FEATURE_KEY) in body_features]
            if targets and found:
                from ..commands.view import _bounds
                center,corners=_bounds(body_targets or targets); camera.look_at(center,corners,found[3])
            elif found:
                sketches=[s for s in model.history(doc) if s['kind']=='SKETCH' and (not self.active_body_id or s.get('body_id')==self.active_body_id)]
                if sketches:
                    sketch=sketches[-1]; scale=max(float(bpy.context.scene.unit_settings.scale_length),1e-12)
                    corners=[Vector(world(sketch,*p))/scale for e in sketch['entities'] for p in model.outline(e)]
                    if corners:
                        low=Vector(tuple(min(p[i] for p in corners) for i in range(3)))
                        high=Vector(tuple(max(p[i] for p in corners) for i in range(3)))
                        camera.look_at((low+high)*.5,corners,found[3])

    def focus(self, sketch):
        found = find_view3d()
        if found:
            camera.sync_from_region(found[3])
        basis = model.frame(sketch)
        normal = Vector(basis['normal']).normalized()
        # Face-on with the sketch's own Y up: its X/Y axes are the screen's, so
        # rectangles are drawn square to the view even on a rotated face plane.
        # Standard planes and new face sketches already have world-upright axes.
        up = Vector(basis['y'])
        up = (up - normal * up.dot(normal)).normalized()
        from mathutils import Matrix
        right = up.cross(normal)
        camera.rotation = Matrix((right,up,normal)).transposed().to_quaternion()
        bounds = [p for e in sketch['entities'] for p in model.outline(e)]
        scale = max(float(bpy.context.scene.unit_settings.scale_length),1e-12)
        if bounds:
            lo = [min(p[i] for p in bounds) for i in (0,1)]
            hi = [max(p[i] for p in bounds) for i in (0,1)]
            camera.location = Vector(world(sketch,(lo[0]+hi[0])/2,(lo[1]+hi[1])/2))/scale
            camera.distance = max(.15, max(hi[i]-lo[i] for i in (0,1))*2)/scale
        else:
            camera.location = Vector(world(sketch,0,0))/scale
            camera.distance = .2/scale
        camera.perspective = self.sketch_projection
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
        bar = self.bar(doc)
        sequence = [n['id'] for n in model.history(doc)] if bar else None
        for sketch in doc['sketches']:
            if self.active_sketch_id and sketch['id'] != self.active_sketch_id:
                continue
            whole_sketch=(self.selection or {}).get('kind')=='SKETCH' and self.selection['id']==sketch['id']
            selected_profile=whole_sketch or ((self.selection or {}).get('kind')=='PROFILE' and any(p['id']==self.selection['id'] for p in model.profiles(sketch)))
            if not model.sketch_visible(doc,sketch) and sketch['id']!=self.active_sketch_id and not selected_profile: continue
            # The bar hides future sketches; the active one (inserted at the bar) still draws.
            if sequence and sketch['id']!=self.active_sketch_id and not selected_profile and \
               sketch['id'] in sequence and sequence.index(sketch['id']) > sequence.index(bar): continue
            entries = sketch['entities'] if self.active_sketch_id else model.closed_entities(sketch)
            if self.active_sketch_id:
                origin=camera.project(Vector(world(sketch,0,0))/scale,found[3])
                if origin is not None:
                    refs=(self.selection or {}).get('items',[])
                    selected=any(r['id']=='ORIGIN' for r in refs)
                    result.append(dict(id='ORIGIN',points=[],closed=False,selected=selected,
                        handles=[dict(part='POINT',point=origin,selected=selected)],label='0,0',label_point=origin))
            def project(p):
                return camera.project(Vector(world(sketch,*p))/scale,found[3])
            for e in entries:
                points = [project(p) for p in model.outline(e)]
                if any(p is None for p in points):
                    continue
                refs = (self.selection or {}).get('items', [self.selection] if self.selection else [])
                selected = whole_sketch or any(ref['id'] in (e['id'],'profile_'+e['id']) for ref in refs)
                handle_points = []
                if self.active_sketch_id:
                    for role,p in sketch_geometry.handles(e).items():
                        projected=project(p)
                        if projected is not None:
                            handle_points.append(dict(part=role,point=projected,
                                intent='ANGLE' if selected and e['type']=='ARC' and role=='END' and sketch_geometry.fillet_sides(sketch,e) is None else 'POINT',
                                selected=any(ref['id']==e['id'] and ref.get('part')==role for ref in refs)))
                selected_parts=[r.get('part','BODY') for r in refs if r['id']==e['id']]
                result.append(dict(id=e['id'],points=points,closed=e['type'] not in ('LINE','ARC','POINT'),
                                   selected=selected,handles=handle_points,selected_parts=selected_parts,construction=e.get('construction',False)))
            if sketch['id']==self.active_sketch_id:
                from . import annotations
                result.extend(annotations.overlay(sketch,project,self.selection,
                    bpy.context.scene.unit_settings.length_unit,found[2].width/max(found[2].height,1)))
        return result

    def cut_ghost(self):
        """World-space volume of the active cut, drawn translucent only in GPUOffScreen.

        The solid keeps its normal shading; only the removed material is see-through.
        Reuses the session tessellation and recomputes only when depth/extent,
        sketch, units or the body transform change.
        """
        session=self.session
        if not (self.workspace and session and session['operation']=='CUT' and session.get('preview')):
            return None
        doc=session['preview']
        try:
            feature=model.find(doc,'features',session['feature_id'])
            sketch,entity=model.profile(doc,feature['profile_id'])
        except CommandError:
            return None
        body=next((o for o in self.objects(doc) if o.get(BODY_KEY)==feature['body_id']),None)
        matrix=body.matrix_world.copy() if body is not None else None
        scale=max(float(bpy.context.scene.unit_settings.scale_length),1e-12)
        extent=feature.get('extent','ONE')
        key=(model.dumps(sketch),feature['profile_id'],feature['depth'],extent,model.dumps(feature.get('to_face')),model.dumps(feature.get('mirror')),scale,
             tuple(tuple(row) for row in matrix) if matrix is not None else None)
        cached=session.get('ghost')
        if cached and cached['key']==key:
            return cached
        from mathutils.geometry import tessellate_polygon
        vertices,faces=extrusion_operand(session['extrusion_cache'],sketch,entity,feature)
        if feature.get('mirror'):
            from . import mirror
            vertices,faces=mirror.solid((vertices,faces),feature['mirror'])
        points=[Vector(v)/scale for v in vertices]
        if matrix is not None:
            points=[matrix@p for p in points]
        triangles,normals,edges=[],[],{}
        for index,face in enumerate(faces):
            corners=[points[i] for i in face]
            triangles.extend(tuple(corners[i]) for tri in tessellate_polygon([corners]) for i in tri)
            normals.append((corners[1]-corners[0]).cross(corners[-1]-corners[0]).normalized())
            for a,b in zip(face,face[1:]+face[:1]):
                edges.setdefault((min(a,b),max(a,b)),[]).append(index)
        # Outline only design creases, not the fan/cap tessellation or dense arc walls.
        segments=[p for (a,b),owners in edges.items()
                  if len(owners)!=2 or normals[owners[0]].dot(normals[owners[1]])<.87
                  for p in (tuple(points[a]),tuple(points[b]))]
        session['ghost']=dict(key=key,triangles=triangles,segments=segments)
        return session['ghost']

    def status(self):
        try:
            doc = self.doc()
            self.isolate()
            session = self.session
            if self.active_sketch_id and not any(s['id']==self.active_sketch_id for s in doc['sketches']):
                self.active_sketch_id = None
            if session and session.get('preview') and session['operation']!='PLANE':
                doc = session['preview']  # A plane preview only draws; the tree stays as saved.
            if (self.selection or {}).get('kind')=='CONSTRAINT':
                active=next((s for s in doc['sketches'] if s['id']==self.active_sketch_id),None)
                if active is None or not any(c['id']==self.selection['id'] for c in active['constraints']): self.selection=None
            if not any(b['id']==self.active_body_id for b in doc['bodies']): self.active_body_id=doc['bodies'][0]['id']
            from . import dimensions
            from ..commands.cad import _plane_public
            sketch=next((s for s in doc['sketches'] if s['id']==self.active_sketch_id),None)
            self.sync_section(sketch)
            refs=(self.selection or {}).get('items',[])
            numeric=dimensions.offers(sketch,[r for r in refs if r.get('kind')=='ENTITY']) if sketch else {}
            labels = None
            if session and session.get('operation') == 'EXTRUDE' and session.get('preview') and session.get('feature_id'):
                try:
                    sketch, _ = model.profile(session['preview'], model.find(session['preview'], 'features', session['feature_id'])['profile_id'])
                    from ..commands.cad import direction_labels
                    labels = direction_labels(model.frame(sketch)['normal'])
                except CommandError:
                    labels = None
            return dict(version=1,workspace=self.workspace,isolated=bool(self.workspace and not self.show_scene),document=model.public(doc),
                        dimension_options=numeric,surface=self.surface.status(),
                        rollback_id=self.bar(doc),
                        active_sketch_id=self.active_sketch_id,selection=self.selection,step=self.step,increment=self.increment,construction=self.construction,active_body_id=self.active_body_id or doc['bodies'][0]['id'],show_scene=self.show_scene,section=self.section,
                        session=dict(active=bool(session),id=session['id'] if session else None,
                                     operation=session['operation'] if session else None,
                                     depth=session.get('depth') if session else None,
                                     width=session.get('width') if session else None,
                                     segments=session.get('segments') if session else None,
                                       extent=session.get('extent','ONE') if session and session.get('operation') in ('CUT','EXTRUDE') else None,
                                      positive_label=labels[0] if labels else None,
                                      negative_label=labels[1] if labels else None,
                                      transparent=bool(session and session['operation']=='CUT'),
                                      plane=_plane_public(session) if session and session['operation']=='PLANE' else None,
                                     can_confirm=bool(session and session.get('candidate')),
                                     can_close=bool(session and session.get('can_close'))),
                        overlay=self.overlay(doc),error=None)
        except CommandError as exc:
            return dict(version=1,workspace=self.workspace,isolated=bool(self.workspace),document=None,active_sketch_id=None,
                        rollback_id=None,
                        selection=None,session=dict(active=False,id=None,operation=None),overlay=[],error=exc.message)


runtime = CadRuntime()
