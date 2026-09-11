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
        # Sin tinte, el material se ve con su propio color: elegir Oro da oro.
        # El tinte es una decisión explícita y reversible, no el estado de partida.
        self.tint = None
        self.radius = .06
        self.strength = 1.
        self.erase = False
        self.finish = 'natural'
        self.surface = {}
        self.grain = 'none'
        self.grain_scale = 20.
        self.grain_amount = .5
        self.grain_relief = .35
        self.interaction = 'PAINT'
        self.isolate = False
        self.brush = 'ROUND'
        self.scope = 'ALL'
        self.stroke = None
        self.frame = None
        self.last_point = None
        self.surface_cache = {}
        self.depth_signature = None

    def objects(self):
        return [bpy.context.view_layer.objects[n] for n in self.targets
                if n in bpy.context.view_layer.objects and bpy.context.view_layer.objects[n].type == 'MESH']

    def require(self, owner=None, targets=True):
        if not self.active or (targets and not self.objects()):
            raise CommandError('Selecciona una o varias mallas y entra en Materiales',code='wrong_mode')
        if self.owner is not None and owner != self.owner:
            raise CommandError('Materiales está en uso por otra conexión',code='session_owned')
        if any(o.mode != 'OBJECT' for o in self.objects()):
            self.leave()
            raise CommandError('Vuelve a entrar en Materiales después de cambiar de modo en Blender',code='wrong_mode')

    def status(self):
        objects = self.objects()
        groups = set.intersection(*(set(g.name for g in o.vertex_groups) for o in objects)) if objects else set()
        # Un catálogo por snapshot, y sin preset seleccionado el estado sigue viajando:
        # que el archivo abierto ya no traiga esa receta no puede romper la escena.
        catalog = recipes.catalog()
        base = next((r for r in catalog if r['id']==self.preset), recipes.FALLBACK)
        return dict(available=True, active=self.active, targets=[o.name for o in self.objects()],
            objects=[dict(id=o.name,label=o.name) for o in bpy.context.view_layer.objects
                     if o.type=='MESH' and o.visible_get()],
            interaction=self.interaction,isolate=self.isolate,brush=self.brush,scope=self.scope,
            regions=[dict(id='ALL',label='Objeto completo'),dict(id='SELECTED',label='Caras seleccionadas en Edit')]+
                    [dict(id='GROUP:'+g,label=g) for g in sorted(groups)],
            brushes=[dict(id='ROUND',label='Redondo'),dict(id='AIRBRUSH',label='Aerógrafo'),dict(id='SPRAY',label='Salpicado')],
            paint_limit=painting.MAX_BASE_FACES,
            paint_blocked=any(len(o.data.polygons)>painting.MAX_BASE_FACES for o in objects),
            preset=self.preset,color=self.effective_color(base),tinted=self.tint is not None,
            radius=self.radius,strength=self.strength,environment=self.environment,
            erase=self.erase,finish=self.finish,custom=bool(self.surface),
            surface=self.effective_surface(base),surface_controls=recipes.SURFACE_CONTROLS,
            grain=self.grain,grain_scale=self.grain_scale,grain_amount=self.grain_amount,grain_relief=self.grain_relief,
            grains=[dict(id=g['id'],label=g['label'],hint=g['hint']) for g in recipes.GRAINS],
            finishes=[dict(id=f['id'],label=f['label'],hint=f['hint']) for f in recipes.FINISHES],
            presets=[dict(id=r['id'],label=r['label'],color=r['color'],category='detail' if r['id'] in recipes.DETAIL_IDS else 'base') for r in catalog],
            environments=[dict(id=e['id'],label=e['label']) for e in ENVIRONMENTS],
            paint_ready=bool(self.objects()) and all(len(o.data.materials)==1 and o.data.materials[0] and o.data.materials[0].get(recipes.KEY) for o in self.objects()))

    def validate_selection(self, objects=None):
        from ..cad.runtime import FEATURE_KEY
        if objects is None: objects = [o for o in bpy.context.selected_objects if o.type == 'MESH']
        if not objects or len(objects)>16:
            raise CommandError('Selecciona entre 1 y 16 objetos de malla',code='material_selection')
        if any(o.get(FEATURE_KEY) for o in objects):
            raise CommandError('Convierte las piezas CAD a malla antes de texturizarlas',code='cad_mesh_protected')
        if any(o.library is not None or o.data.library is not None for o in objects):
            raise CommandError('Usa objetos locales para editar sus materiales',code='material_linked_library')
        return objects

    def select(self, names):
        if not isinstance(names,list) or any(not isinstance(n,str) for n in names):
            raise BadPayload('objects requiere una lista de nombres')
        names=list(dict.fromkeys(names))
        objects=[bpy.context.view_layer.objects.get(n) for n in names]
        if any(o is None or o.type!='MESH' or not o.visible_get() for o in objects):
            raise BadPayload('Selecciona mallas visibles de esta escena')
        if objects: self.validate_selection(objects)
        self.cancel()
        for obj in bpy.context.selected_objects: obj.select_set(False)
        for obj in objects: obj.select_set(True)
        bpy.context.view_layer.objects.active=objects[-1] if objects else None
        self.targets=names; self.scope='ALL'; self.frame=None; self.depth_signature=None

    def enter(self, owner):
        if self.active:
            self.require(owner,targets=False)
            return
        objects = self.validate_selection()
        self.targets = [o.name for o in objects]
        self.owner = owner
        self.active = True
        self.frame = None
        self.scope = 'ALL'
        self.isolate = False
        self.interaction = 'PAINT'

    def leave(self):
        self.cancel()
        self.active = False
        self.targets = []
        self.owner = None
        self.frame = None
        self.surface_cache.clear()
        self.depth_signature = None

    def base_recipe(self, catalog=None):
        match = next((r for r in catalog or recipes.catalog() if r['id']==self.preset),None)
        if match is None: raise BadPayload('Este preset ya no existe; selecciona otro')
        import copy
        return copy.deepcopy(match)

    def effective_color(self, base=None):
        return self.tint or (base if base is not None else self.base_recipe())['color']

    def effective_surface(self, base=None):
        """Receta, después acabado, después lo que el usuario haya ajustado a mano."""
        surface = dict((base if base is not None else self.base_recipe())['surface'])
        surface.update(recipes.finish_surface(self.finish))
        surface.update(self.surface)
        return surface

    def selected_recipe(self):
        match = self.base_recipe()
        match['surface'] = self.effective_surface()
        grain = recipes.grain_pattern(self.grain, self.grain_scale, self.grain_amount,
                                      self.grain_relief, self.effective_color())
        if grain: match['patterns'] = (match['patterns'] + [grain])[:8]
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
        eevee = bpy.context.scene.eevee
        raytracing = eevee.use_raytracing
        overlays, gizmos = space.overlay.show_overlays, space.show_gizmo
        try:
            if self.active:
                for obj in bpy.context.view_layer.objects:
                    if self.isolate and obj.name not in self.targets and not obj.hide_get():
                        hidden.append(obj); obj.hide_set(True)
                env = next(e for e in ENVIRONMENTS if e['id']==self.environment)
                shading.type='MATERIAL'; shading.use_scene_lights=False; shading.use_scene_world=False
                eevee.use_raytracing=True
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
            eevee.use_raytracing=raytracing
            space.overlay.show_overlays=overlays; space.show_gizmo=gizmos
            if hidden: bpy.context.view_layer.update()

    def needs_depth(self, matrix, width, height):
        if not self.active or self.stroke is not None: return False
        signature=(width,height,np.asarray(matrix,dtype=np.float32).tobytes(),
                   tuple((obj.name,painting.surface_key(obj)) for obj in bpy.context.view_layer.objects
                         if obj.type=='MESH' and obj.visible_get()))
        self._next_depth_signature=signature
        return self.frame is None or self.depth_signature!=signature

    def capture_depth(self, fb, matrix, width, height):
        if self.active:
            depth = np.array(fb.read_depth(0,0,width,height),dtype=np.float32).reshape(height,width)
            self.frame = (depth,np.array(matrix),width,height)
            self.depth_signature = getattr(self,"_next_depth_signature",None)

    def apply(self):
        self.cancel()
        if self.scope != 'ALL':
            self.begin({'stroke_id':'fill-region'}, fill=True)
            try:
                for record in self.stroke['objects']:
                    ids=record['indexes']; pixels=record['pixels']
                    before=pixels[ids*4].copy()
                    for channel in range(3): pixels[ids*4+channel]=1
                    self.stroke['changed'] |= bool(np.any(before!=pixels[ids*4]))
                    record['image'].pixels.foreach_set(pixels); record['image'].update()
                self.end()
            except Exception:
                self.cancel(); raise
            return
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

    def begin(self, payload, fill=False):
        self.cancel()
        for obj in self.objects():
            if len(obj.data.materials) != 1 or not obj.data.materials[0] or not obj.data.materials[0].get(recipes.KEY):
                raise CommandError('Aplica primero una base al objeto completo para pintar por zonas', code='paint_needs_base')
            painting.check_size(obj)
        if not fill and self.frame is None: raise CommandError('Espera a que aparezca la vista de materiales',code='paint_no_frame')
        self.stroke = dict(id=payload['stroke_id'], owner=payload.get('_client_id'), objects=[], changed=False, frame=self.frame)
        self.last_point = None
        try:
            for obj in self.objects():
                if self.erase and not fill and not obj.data.materials[0].get('tablet_top_mask'): continue
                old=obj.data; new=old.copy(); obj.data=new
                record=dict(name=obj.name,old=old,new=new,material=None,image=None)
                self.stroke['objects'].append(record)
                indexes,positions=painting.atlas(obj,self.surface_cache,scope=self.scope)
                material,image,pixels=painting.make_layer(obj,self.selected_recipe(),self.tint,erase=self.erase and not fill)
                record.update(material=material,image=image,pixels=pixels,indexes=indexes)
                record['projection']=None if fill else painting.project_surface(indexes,positions,self.stroke['frame'])
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
            if painting.paint_projected(record['projection'],record['pixels'],samples,self.radius,self.strength,erase=self.erase,brush=self.brush):
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
