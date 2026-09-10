"""Main-thread material workspace; temporary presentation never enters .blend."""
from contextlib import contextmanager
import bpy
from bpy.app.handlers import persistent
import numpy as np
from ..errors import BadPayload, CommandError
from ..bpy_utils import undo_push
from . import recipes, painting

ENVIRONMENTS = [dict(id='studio',label='Estudio',light='studio.exr',intensity=1.,rotation=0.,background=.15),
    dict(id='day',label='Exterior',light='forest.exr',intensity=1.,rotation=.7,background=.35),
    dict(id='warm',label='Atardecer',light='sunset.exr',intensity=1.1,rotation=2.,background=.3),
    dict(id='soft',label='Luz suave',light='interior.exr',intensity=.8,rotation=1.,background=.15)]


class Runtime:
    def __init__(self):
        self.active = False
        self.owner = None
        self.targets = []
        self.environment = 'studio'
        self.preset = 'plastic'
        self.tint = '#E85D38'
        self.radius = .06
        self.strength = 1.
        self.erase = False
        self.finish = 'natural'
        self.stroke = None
        self.frame = None
        self.last_point = None
        self.surface_cache = {}
        self.depth_signature = None

    def objects(self):
        return [bpy.data.objects[n] for n in self.targets if n in bpy.data.objects and bpy.data.objects[n].type == 'MESH']

    def require(self, owner=None):
        if not self.active or not self.objects():
            raise CommandError('Selecciona una o varias mallas y entra en Materiales',code='wrong_mode')
        if self.owner is not None and owner != self.owner:
            raise CommandError('Materiales está en uso por otra conexión',code='session_owned')
        if any(o.mode != 'OBJECT' for o in self.objects()):
            self.leave()
            raise CommandError('Vuelve a entrar en Materiales después de cambiar de modo en Blender',code='wrong_mode')

    def status(self):
        return dict(available=True, active=self.active, targets=[o.name for o in self.objects()],
            preset=self.preset,color=self.tint,radius=self.radius,strength=self.strength,environment=self.environment,
            erase=self.erase,finish=self.finish,
            finishes=[dict(id=k,label=v) for k,v in [('natural','Natural'),('polished','Pulido'),('worn','Gastado')]],
            presets=[dict(id=r['id'],label=r['label'],color=r['color'],category='detail' if r['id'] in recipes.DETAIL_IDS else 'base') for r in recipes.catalog()],
            environments=[dict(id=e['id'],label=e['label']) for e in ENVIRONMENTS],
            paint_ready=bool(self.objects()) and all(len(o.data.materials)==1 and o.data.materials[0] and o.data.materials[0].get(recipes.KEY) for o in self.objects()))

    def validate_selection(self):
        from ..cad.runtime import FEATURE_KEY
        objects = [o for o in bpy.context.selected_objects if o.type == 'MESH']
        if not objects or len(objects)>16:
            raise CommandError('Selecciona entre 1 y 16 objetos de malla',code='material_selection')
        if any(o.get(FEATURE_KEY) for o in objects):
            raise CommandError('Convierte las piezas CAD a malla antes de texturizarlas',code='cad_mesh_protected')
        if any(o.library is not None or o.data.library is not None for o in objects):
            raise CommandError('Usa objetos locales para editar sus materiales',code='material_linked_library')
        return objects

    def enter(self, owner):
        if self.active:
            self.require(owner)
            return
        objects = self.validate_selection()
        self.targets = [o.name for o in objects]
        self.owner = owner
        self.active = True
        self.frame = None

    def leave(self):
        self.cancel()
        self.active = False
        self.targets = []
        self.owner = None
        self.frame = None
        self.surface_cache.clear()
        self.depth_signature = None

    def selected_recipe(self):
        match = next((r for r in recipes.catalog() if r['id']==self.preset),None)
        if match is None: raise BadPayload('Este preset ya no existe; selecciona otro')
        import copy
        match=copy.deepcopy(match)
        if self.finish=='polished': match['surface']['roughness']=.12
        elif self.finish=='worn': match['surface']['roughness']=.8
        return match

    @contextmanager
    def presentation(self, space, clean=False):
        hidden = []
        shading = space.shading
        # Wireframe is unavailable in painting. Normalize it before taking the
        # restoration snapshot, including changes made directly on the desktop.
        if self.active and shading.type == 'WIREFRAME':
            shading.type = 'SOLID'
        props = ('type','use_scene_lights','use_scene_world','studio_light','studiolight_intensity',
                 'studiolight_rotate_z','studiolight_background_alpha','studiolight_background_blur')
        saved = {p:getattr(shading,p) for p in props} if self.active else {}
        overlays, gizmos = space.overlay.show_overlays, space.show_gizmo
        try:
            if self.active:
                for obj in bpy.context.view_layer.objects:
                    if obj.name not in self.targets and not obj.hide_get():
                        hidden.append(obj); obj.hide_set(True)
                env = next(e for e in ENVIRONMENTS if e['id']==self.environment)
                shading.type='MATERIAL'; shading.use_scene_lights=False; shading.use_scene_world=False
                available = {s.name for s in bpy.context.preferences.studio_lights if s.type=='WORLD'}
                if env['light'] in available: shading.studio_light=env['light']
                shading.studiolight_intensity=env['intensity']; shading.studiolight_rotate_z=env['rotation']
                shading.studiolight_background_alpha=env['background']; shading.studiolight_background_blur=1.
                bpy.context.evaluated_depsgraph_get()
            if self.active or clean:
                space.overlay.show_overlays=False; space.show_gizmo=False
            yield
        finally:
            for obj in hidden:
                try: obj.hide_set(False)
                except ReferenceError: pass
            for p,v in saved.items(): setattr(shading,p,v)
            space.overlay.show_overlays=overlays; space.show_gizmo=gizmos
            if hidden: bpy.context.view_layer.update()

    def needs_depth(self, matrix, width, height):
        if not self.active or self.stroke is not None: return False
        signature=(width,height,np.asarray(matrix,dtype=np.float32).tobytes(),
                   tuple((obj.name,painting.surface_key(obj)) for obj in self.objects()))
        self._next_depth_signature=signature
        return self.frame is None or self.depth_signature!=signature

    def capture_depth(self, fb, matrix, width, height):
        if self.active:
            depth = np.array(fb.read_depth(0,0,width,height),dtype=np.float32).reshape(height,width)
            self.frame = (depth,np.array(matrix),width,height)
            self.depth_signature = getattr(self,"_next_depth_signature",None)

    def apply(self):
        self.cancel()
        material = recipes.compile_material(self.selected_recipe(), self.tint)
        previous = []
        try:
            for obj in self.objects():
                old = obj.data; new = old.copy(); previous.append((obj,old,new))
                obj.data=new; new.materials.clear(); new.materials.append(material)
                for poly in new.polygons: poly.material_index=0
            undo_push('Aplicar material')
        except Exception:
            for obj,old,new in previous:
                obj.data=old
                if new.users==0: bpy.data.meshes.remove(new)
            raise

    def begin(self, payload):
        self.cancel()
        for obj in self.objects():
            if len(obj.data.materials) != 1 or not obj.data.materials[0] or not obj.data.materials[0].get(recipes.KEY):
                raise CommandError('Pulsa «Aplicar a todo» antes de pintar', code='paint_needs_base')
            if len(obj.data.polygons)>20000:
                raise CommandError('Pintura: usa una malla de hasta 20 000 caras', code='paint_mesh_limit')
        if self.frame is None: raise CommandError('Espera a que aparezca la vista de materiales',code='paint_no_frame')
        self.stroke = dict(id=payload['stroke_id'], owner=payload.get('_client_id'), objects=[], changed=False, frame=self.frame)
        self.last_point = None
        try:
            for obj in self.objects():
                if self.erase and not obj.data.materials[0].get('tablet_top_mask'): continue
                old=obj.data; new=old.copy(); obj.data=new
                record=dict(name=obj.name,old=old,new=new,material=None,image=None)
                self.stroke['objects'].append(record)
                indexes,positions=painting.atlas(obj,self.surface_cache)
                material,image,pixels=painting.make_layer(obj,self.selected_recipe(),self.tint,erase=self.erase)
                projection=painting.project_surface(indexes,positions,self.stroke['frame'])
                record.update(material=material,image=image,pixels=pixels,projection=projection)
        except Exception:
            self.cancel(); raise

    def update(self, points):
        if not self.stroke: return
        samples=[]
        for p in points:
            prev=self.last_point
            if prev:
                aspect=self.stroke['frame'][2]/self.stroke['frame'][3]
                distance=((p['u']-prev['u'])**2*aspect**2+(p['v']-prev['v'])**2)**.5
                count=min(128,max(1,int(distance/(self.radius*.2))))
                for i in range(1,count+1):
                    t=i/count
                    samples.append({k:prev[k]+(p[k]-prev[k])*t for k in ('u','v','pressure')})
            else: samples.append(p)
            self.last_point=p
        for record in self.stroke['objects']:
            if painting.paint_projected(record['projection'],record['pixels'],samples,self.radius,self.strength,erase=self.erase):
                record['image'].pixels.foreach_set(record['pixels']); record['image'].update()
                self.stroke['changed']=True

    def end(self):
        if not self.stroke: return
        if not self.stroke['changed']:
            self.cancel(); return
        for record in self.stroke['objects']: record['image'].pack()
        self.stroke=None; self.last_point=None
        undo_push('Pintar material')

    def cancel(self):
        stroke,self.stroke=self.stroke,None
        self.last_point=None
        if not stroke: return
        for r in stroke['objects']:
            obj=bpy.data.objects.get(r['name'])
            try:
                if obj and obj.data==r['new']: obj.data=r['old']
                if r['new'].users==0: bpy.data.meshes.remove(r['new'])
                if r['material'] and r['material'].users==0:
                    groups=[n.node_tree for n in r['material'].node_tree.nodes if n.type=='GROUP']
                    bpy.data.materials.remove(r['material'])
                    for g in groups:
                        if g.users==0: bpy.data.node_groups.remove(g)
                if r['image'] and r['image'].users==0: bpy.data.images.remove(r['image'])
            except ReferenceError: pass


runtime=Runtime()

@persistent
def cancel_preview(*_): runtime.cancel()

@persistent
def leave_workspace(*_): runtime.leave()


def register_handlers():
    for key,callback in [('save_pre',cancel_preview),('load_pre',leave_workspace),('undo_pre',cancel_preview),('redo_pre',cancel_preview)]:
        handlers=getattr(bpy.app.handlers,key)
        if callback not in handlers: handlers.append(callback)


def unregister_handlers():
    runtime.leave()
    for key,callback in [('save_pre',cancel_preview),('load_pre',leave_workspace),('undo_pre',cancel_preview),('redo_pre',cancel_preview)]:
        handlers=getattr(bpy.app.handlers,key)
        if callback in handlers: handlers.remove(callback)
