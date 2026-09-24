"""Main-thread CAD transactions and Blender materialization."""
import copy
from contextlib import contextmanager
import math
import bpy
from mathutils import Vector
from . import document as model
from .kernel import kernel, world, tidy_mesh, ExtrusionPreviewCache
from . import sketch as sketch_geometry
from ..errors import BadPayload, CommandError
from ..bpy_utils import find_view3d, undo_push
from ..camera import camera

FEATURE_KEY = 'btr_cad_feature_id'
DOC_KEY = 'btr_cad_document_id'
BODY_KEY = 'btr_cad_body_id'
COPY_SOURCE_KEY = 'btr_cad_copy_source'


def mesh_copy(obj):
    """Independent native mesh and modifier stack, without CAD ownership."""
    copy=obj.copy()
    try:
        copy.data=obj.data.copy()
        copy.name=obj.name+' · malla'
        for key in (FEATURE_KEY,DOC_KEY,BODY_KEY,COPY_SOURCE_KEY):
            if key in copy: del copy[key]
        copy.hide_viewport=False;copy.hide_render=False
        return copy
    except Exception:
        bpy.data.objects.remove(copy)
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
        self._solid_view = None
        self.rollback_id = None
        self._extrusion_cache = ExtrusionPreviewCache()
        self._solids = {}
        self._body_meshes = {}
        self._materialized = {}
        from .surface import SurfaceSelection
        self.surface = SurfaceSelection()

    def reset(self):
        self.__init__()

    def doc(self):
        scene = bpy.context.scene
        identity = scene.as_pointer()
        if self._scene != identity:
            # Undo replaces RNA addresses. Keep the workspace, but never hold an
            # old scene preview; explicit file loads call reset_session().
            workspace, active = self.workspace, self.active_sketch_id
            settings={k:getattr(self,k) for k in ("active_body_id","step","increment","construction","show_scene","_solid_view","rollback_id")}
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
        """Evaluate a body's chronological operations, then publish one mesh per body.

        Cached operands are plain geometry, never RNA. Unchanged predecessors and
        unchanged display meshes survive transactions, including sketch editing.
        Failed evaluation leaves every published body at its previous valid state.
        """
        import hashlib
        from .surface import stamp
        scale = max(float(bpy.context.scene.unit_settings.scale_length), 1e-12)
        model.resolve_supports(doc)
        sequence = model.history(doc)
        if limit:
            end=next((i for i,node in enumerate(sequence) if node['id']==limit),None)
            if end is not None: sequence=sequence[:end+1]
        extrusion_cache=extrusion_cache or self._extrusion_cache
        tips={}; solids={}; keys={}; direct={}
        for feature in sequence:
            if feature['kind']!='FEATURE' or not feature['enabled']: continue
            identifier=feature['id']; body=feature['body_id']
            previous=tips.get(body)
            sketch,entity=model.profile(doc,feature['profile_id'])
            depth=model.number(feature['depth'],positive=True)
            cut=feature['type']=='CUT'
            extent=feature.get('extent','ONE') if cut else 'ONE'
            if extent not in ('ONE','BOTH'): extent='ONE'
            if cut and feature.get('target_id') not in solids:
                raise CommandError('Activa el sólido destino antes del vaciado',code='cad_dependency')
            signature=(doc['id'],feature['profile_id'],feature['type'],depth,extent,
                       model.dumps(dict(frame=model.frame(sketch),entities=sketch['entities'])),
                       keys.get(previous))
            cached=self._solids.get(identifier)
            if cached is None or cached[0]!=signature:
                operand=extrusion_cache.extrude(sketch,entity,depth,display=False,symmetric=True) if extent=='BOTH' else extrusion_cache.extrude(sketch,entity,-depth if cut else depth,display=False)
                if previous:
                    operand=kernel.cut(solids[previous],operand) if cut else kernel.union(solids[previous],operand)
                elif cut:
                    raise CommandError('El cuerpo no tiene un sólido para vaciar',code='cad_dependency')
                cached=(signature,operand)
                self._solids[identifier]=cached
            solids[identifier]=cached[1]
            keys[identifier]=hashlib.blake2b(repr(signature).encode(),digest_size=16).digest()
            tips[body]=identifier
            direct[body]=(sketch,entity,depth) if previous is None and not cut else None
        # Form every display mesh before touching existing Blender objects.
        display={}
        for body,identifier in tips.items():
            signature=(keys[identifier],scale)
            cached=self._body_meshes.get(body)
            if cached is None or cached[0]!=signature:
                vertices,faces=(extrusion_cache.extrude(*direct[body],display=True) if direct[body] else tidy_mesh(*solids[identifier]))
                cached=(signature,([tuple(c/scale for c in v) for v in vertices],faces))
                self._body_meshes[body]=cached
            display[body]=cached
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
                mesh=bpy.data.meshes.new(body['name'])
                mesh.from_pydata(vertices,[],faces);mesh.update()
                if obj is None:
                    obj=bpy.data.objects.new(body['name'],mesh)
                    bpy.context.scene.collection.objects.link(obj)
                else:
                    old=obj.data;obj.data=mesh
                    if old.users==0:bpy.data.meshes.remove(old)
                self._materialized[identifier]=(obj.as_pointer(),obj.data.as_pointer(),signature,stamp(obj))
            obj.name=body['name']
            obj[FEATURE_KEY]=tips[identifier];obj[DOC_KEY]=doc['id'];obj[BODY_KEY]=identifier
            obj.hide_viewport=False;obj.hide_render=bool(obj.get(COPY_SOURCE_KEY))
            retained.add(obj.as_pointer())
        for obj in existing:
            if obj.as_pointer() not in retained:
                old=obj.data;bpy.data.objects.remove(obj,do_unlink=True)
                if old.users==0:bpy.data.meshes.remove(old)
        feature_ids={f['id'] for f in doc['features']}
        self._solids={k:v for k,v in self._solids.items() if k in feature_ids}
        body_ids={b['id'] for b in doc['bodies']}
        self._body_meshes={k:v for k,v in self._body_meshes.items() if k in body_ids}
        self._materialized={k:v for k,v in self._materialized.items() if k in body_ids}
        profile_ids={f['profile_id'].removeprefix('profile_') for f in doc['features']}
        self._extrusion_cache.entries={k:v for k,v in self._extrusion_cache.entries.items() if k in profile_ids}
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
            session=self.session
            original = session['baseline']
            self.session = None
            if restore and self._scene == bpy.context.scene.as_pointer():
                if session['operation']!='DRAG' or session.get('preview'): self.rebuild(original, limit=self.bar(original))
            self.selection = copy.deepcopy(session.get('selection_before')) if session['operation']=='DRAG' and restore else None

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

    def commit(self, doc, label, *, geometry=True):
        if geometry: self.rebuild(doc, limit=self.bar(doc))
        self.persist(doc, advance=True)
        with self.saving():
            undo_push(label)

    def transaction(self, payload, change, label, *, geometry=True):
        self.require_workspace()
        if self.session:
            raise CommandError('Confirma o cancela la preview primero', code='session_active')
        doc = self.doc()
        change(doc)
        self.commit(doc,label,geometry=geometry)
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
        normal = Vector(model.frame(sketch)['normal'])
        up = Vector(model.frame(sketch)['y'])
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
            for e in entries:
                def project(p):
                    return camera.project(Vector(world(sketch,*p))/scale,found[3])
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
                result.append(dict(id=e['id'],points=points,closed=e['type'] not in ('LINE','ARC'),
                                   selected=selected,handles=handle_points,selected_parts=selected_parts,construction=e.get('construction',False)))
            if sketch['id']==self.active_sketch_id:
                labels={'COINCIDENT':'●','HORIZONTAL':'H','VERTICAL':'V','PARALLEL':'∥',
                        'PERPENDICULAR':'⊥','TANGENT':'T','EQUAL':'=','FIX':'Fijo','MIDPOINT':'½',
                        'SYMMETRIC':'Sim','SYMMETRIC_LINE':'Sim⟋'}
                unit=bpy.context.scene.unit_settings.length_unit
                factor,suffix={'MILLIMETERS':(1000,'mm'),'CENTIMETERS':(100,'cm')}.get(unit,(1,'m'))
                for index,c in enumerate(sketch.get('constraints',[])):
                    anchors=[]
                    for ref in c['refs']:
                        entity=sketch_geometry.get_entity(sketch,ref)
                        if ref.get('part') in sketch_geometry.handles(entity): anchors.append(tuple(sketch_geometry.point(sketch,ref)))
                        elif entity['type'] in ('LINE','RECTANGLE'):
                            if entity['type']=='RECTANGLE' and ref.get('part','BODY')=='BODY': anchors.extend(model.outline(entity))
                            else: anchors.extend(tuple(p) for p in sketch_geometry.line(sketch,ref))
                        else: anchors.append((entity['x'],entity['y']))
                    if not anchors: continue
                    anchor=tuple(sum(p[i] for p in anchors)/len(anchors) for i in (0,1))
                    projected=project(anchor)
                    if projected is None: continue
                    label=labels.get(c['type'],c['type'])
                    if c.get('value') is not None:
                        label={'RADIUS':'R ', 'DISTANCE_X':'H ', 'DISTANCE_Y':'V '}.get(c['type'],'')+format(c['value']*factor,'.6g')+' '+suffix
                    result.append(dict(id=c['id'],kind='DIMENSION',points=[],closed=False,selected=False,
                        label=label,label_point=projected,label_offset=14+(index%4)*15))
        return result

    @contextmanager
    def preview_shading(self, space):
        shading=space.shading
        if not (self.workspace and self.session and self.session['operation']=='CUT'):
            yield
            return
        old=(shading.type,shading.show_xray,shading.xray_alpha)
        try:
            shading.type='SOLID'; shading.show_xray=True; shading.xray_alpha=.35
            yield
        finally:
            shading.type,shading.show_xray,shading.xray_alpha=old

    def status(self):
        try:
            doc = self.doc()
            self.isolate()
            session = self.session
            if self.active_sketch_id and not any(s['id']==self.active_sketch_id for s in doc['sketches']):
                self.active_sketch_id = None
            if session and session.get('preview'):
                doc = session['preview']
            if not any(b['id']==self.active_body_id for b in doc['bodies']): self.active_body_id=doc['bodies'][0]['id']
            from . import dimensions
            sketch=next((s for s in doc['sketches'] if s['id']==self.active_sketch_id),None)
            refs=(self.selection or {}).get('items',[])
            numeric=dimensions.offers(sketch,[r for r in refs if r.get('kind')=='ENTITY']) if sketch else {}
            return dict(version=1,workspace=self.workspace,isolated=bool(self.workspace and not self.show_scene),document=model.public(doc),
                        dimension_options=numeric,surface=self.surface.status(),
                        rollback_id=self.bar(doc),
                        active_sketch_id=self.active_sketch_id,selection=self.selection,step=self.step,increment=self.increment,construction=self.construction,active_body_id=self.active_body_id or doc['bodies'][0]['id'],show_scene=self.show_scene,
                        session=dict(active=bool(session),id=session['id'] if session else None,
                                     operation=session['operation'] if session else None,
                                     depth=session.get('depth') if session else None,
                                      extent=session.get('extent','ONE') if session and session.get('operation')=='CUT' else None,
                                      transparent=bool(session and session['operation']=='CUT'),
                                     can_confirm=bool(session and session.get('candidate')),
                                     can_close=bool(session and session.get('can_close'))),
                        overlay=self.overlay(doc),error=None)
        except CommandError as exc:
            return dict(version=1,workspace=self.workspace,isolated=bool(self.workspace),document=None,active_sketch_id=None,
                        rollback_id=None,
                        selection=None,session=dict(active=False,id=None,operation=None),overlay=[],error=exc.message)


runtime = CadRuntime()
