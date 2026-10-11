"""Main-thread material workspace; temporary presentation never enters .blend."""
from contextlib import contextmanager
import copy
import math
import bpy
from bpy.app.handlers import persistent
import numpy as np
from ..errors import BadPayload, CommandError
from ..bpy_utils import undo_push
from . import recipes, painting, layers

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
        self.light_rotation = 0.
        # Blender solo gira el studio light en acimut: no hay elevación en su API.
        # El eje vertical del gesto cambia cuánta luz hay, que es lo que se persigue
        # al intentar «subir» la luz para ver mejor un acabado.
        self.light_energy = 1.
        self.light_gesture = None
        self.preset = 'plastic'
        # Sin tinte, el material se ve con su propio color: elegir Oro da oro.
        # El tinte es una decisión explícita y reversible, no el estado de partida.
        self.tint = None
        self.radius = .06
        self.strength = 1.
        self.erase = False
        self.paint_kind = 'COLOR'
        self.active_layer = None
        self.fresh_layer = False
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
        layer_state=self.layer_status(objects)
        return dict(available=True, active=self.active, targets=[o.name for o in self.objects()],
            objects=[dict(id=o.name,label=o.name) for o in bpy.context.view_layer.objects
                     if o.type=='MESH' and o.visible_get()],
            paint_kind=self.paint_kind,active_layer=self.active_layer,
            layers=layer_state,layers_editable=len(objects)==1,
            interaction=self.interaction,isolate=self.isolate,brush=self.brush,scope=self.scope,
            regions=[dict(id='ALL',label='Objeto completo'),dict(id='SELECTED',label='Caras seleccionadas en Edit')]+
                    [dict(id='GROUP:'+g,label=g) for g in sorted(groups)],
            brushes=[dict(id='ROUND',label='Redondo'),dict(id='AIRBRUSH',label='Aerógrafo'),dict(id='SPRAY',label='Salpicado')],
            paint_limit=painting.MAX_BASE_FACES,
            paint_blocked=any(len(o.data.polygons)>painting.MAX_BASE_FACES for o in objects),
            preset=self.preset,color=self.effective_color(base),tinted=self.tint is not None,
            radius=self.radius,strength=self.strength,environment=self.environment,light_rotation=self.light_rotation,light_energy=self.light_energy,
            erase=self.erase,finish=self.finish,custom=bool(self.surface),
            surface=self.effective_surface(base),surface_controls=recipes.SURFACE_CONTROLS,
            grain=self.grain,grain_scale=self.grain_scale,grain_amount=self.grain_amount,grain_relief=self.grain_relief,
            grains=[dict(id=g['id'],label=g['label'],hint=g['hint']) for g in recipes.GRAINS],
            finishes=[dict(id=f['id'],label=f['label'],hint=f['hint']) for f in recipes.FINISHES],
            presets=[dict(id=r['id'],label=r['label'],color=r['color'],category='detail' if r['id'] in recipes.DETAIL_IDS else 'base') for r in catalog],
            environments=[dict(id=e['id'],label=e['label']) for e in ENVIRONMENTS],
            paint_ready=bool(self.objects()) and all(len(o.data.materials)==1 and o.data.materials[0] and o.data.materials[0].get(recipes.KEY) for o in self.objects()))

    def layer_status(self, objects):
        if len(objects)!=1 or len(objects[0].data.materials)!=1: return []
        material=objects[0].data.materials[0]
        entries=layers.entries(material)
        if self.active_layer and not any(e['id']==self.active_layer for e in entries): self.active_layer=None
        return [{k:e[k] for k in ('id','label','kind','color','visible','opacity')} for e in entries]

    def edit_layer(self, payload):
        self.cancel()
        objects=self.objects()
        if len(objects)!=1 or len(objects[0].data.materials)!=1:
            raise CommandError('Elige un solo objeto para editar sus capas', code='material_selection')
        obj=objects[0]; old=obj.data; source=old.materials[0]
        stack=layers.entries(source); action=payload.get('action'); ident=payload.get('layer_id')
        if action=='new':
            self.active_layer=None; self.fresh_layer=True; self.erase=False; self.interaction='PAINT'
            return
        entry=next((e for e in stack if e['id']==ident),None)
        if entry is None: raise CommandError('La capa ya no existe; elige otra', code='paint_layer_missing')
        if action=='select':
            self.active_layer=ident; self.fresh_layer=False; self.paint_kind=entry['kind']
            self.interaction='PAINT'; self.erase=False
            return
        if action not in {'set','delete'}: raise BadPayload('Acción de capa desconocida')
        original=copy.deepcopy(stack)
        if action=='delete': stack.remove(entry)
        else:
            if 'visible' in payload:
                if not isinstance(payload['visible'],bool): raise BadPayload('visible requiere true o false')
                entry['visible']=payload['visible']
            if 'opacity' in payload: entry['opacity']=recipes.number(payload['opacity'],0,1,'opacity')
            if 'label' in payload:
                label=payload['label']
                if not isinstance(label,str) or not 1<=len(label.strip())<=48: raise BadPayload('Nombre de capa inválido')
                entry['label']=label.strip()
        if stack==original: return
        templates=layers.sources(source,original)
        material=layers.build(source,stack,templates); new=old.copy()
        try:
            new.materials[0]=material; obj.data=new
            undo_push('Eliminar capa' if action=='delete' else 'Ajustar capa')
        except Exception:
            obj.data=old; bpy.data.meshes.remove(new); layers.dispose(material); raise
        if action=='delete' and self.active_layer==ident: self.active_layer=None

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
        self.active_layer=None; self.fresh_layer=False
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
        self.active_layer = None
        self.fresh_layer = False
        self.paint_kind = 'COLOR'
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
                shading.studiolight_intensity=min(10.,max(.05,env['intensity']*self.light_energy))
                shading.studiolight_rotate_z=(env['rotation']+math.radians(self.light_rotation)+math.pi) % math.tau-math.pi
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
            self.active_layer=None
            self.begin({'stroke_id':'fill-region'}, fill=True)
            try:
                for record in self.stroke['objects']:
                    ids=record['indexes']; pixels=record['pixels']
                    before=pixels[ids*4].copy()
                    for channel in range(3): pixels[ids*4+channel]=1
                    self.stroke['changed'] |= bool(np.any(before!=pixels[ids*4]))
                    painting.publish_mask(record['image'],pixels,record['padding_indexes'])
                self.end()
            except Exception:
                self.cancel(); raise
            return
        self.active_layer=None; self.fresh_layer=False
        material = recipes.compile_material(self.selected_recipe(), self.tint)
        previous = []
        try:
            for obj in self.objects():
                old = obj.data; new = old.copy(); previous.append((obj,old,new))
                obj.data=new; new.materials.clear(); new.materials.append(material)
                paint_uv=new.uv_layers.get(painting.UV_NAME)
                if paint_uv: new.uv_layers.remove(paint_uv)
                for poly in new.polygons: poly.material_index=0
            undo_push('Aplicar material')
        except Exception:
            for obj,old,new in previous:
                obj.data=old
                if new.users==0: bpy.data.meshes.remove(new)
            raise

    def begin(self, payload, fill=False):
        self.cancel()
        self.layer_status(self.objects())
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
                padding_indexes,_=painting.atlas(obj,self.surface_cache)
                indexes,positions=painting.atlas(obj,self.surface_cache,scope=self.scope)
                material,image,pixels=painting.make_layer(obj,self.selected_recipe(),self.tint,erase=self.erase and not fill,
                    kind='MATERIAL' if fill else self.paint_kind,active=None if fill else self.active_layer,
                    fresh=fill or self.fresh_layer)
                record.update(material=material,image=image,pixels=pixels,indexes=indexes,padding_indexes=padding_indexes)
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
                painting.publish_mask(record['image'],record['pixels'],record['padding_indexes'])
                self.stroke['changed']=True

    def end(self):
        if not self.stroke: return
        if not self.stroke['changed']:
            self.cancel(); return
        for record in self.stroke['objects']: record['image'].pack()
        if len(self.stroke['objects'])==1:
            self.active_layer=self.stroke['objects'][0]['material'].get('tablet_active_layer')
        self.fresh_layer=False
        self.stroke=None; self.last_point=None
        undo_push('Pintar material')

    def cancel_lighting(self):
        if self.light_gesture is not None:
            self.light_rotation = self.light_gesture['baseline']
            self.light_energy = self.light_gesture['energy']
            self.light_gesture = None

    def lighting(self, payload):
        """Presentation-only lighting; each drag rebuilds from its committed values."""
        self.require(payload.get('_client_id'), targets=False)
        phase = payload.get('phase')
        if phase == 'reset':
            self.cancel_lighting()
            self.light_rotation = 0.
            self.light_energy = 1.
            return
        if phase not in {'begin', 'update', 'end', 'cancel'}:
            raise BadPayload('Fase de luces desconocida')
        gesture_id = payload.get('gesture_id')
        if not isinstance(gesture_id, str) or not 1 <= len(gesture_id) <= 80:
            raise BadPayload('gesture_id de luces inválido')
        if phase == 'begin':
            if self.interaction != 'LIGHTS':
                raise CommandError('Activa el cursor de luces', code='wrong_mode')
            if self.light_gesture and self.light_gesture['id'] == gesture_id:
                return
            self.cancel()
            self.light_gesture = dict(id=gesture_id, baseline=self.light_rotation, energy=self.light_energy)
        elif self.light_gesture and self.light_gesture['id'] == gesture_id:
            if phase == 'update':
                angle = recipes.number(payload.get('rotation'), -360000., 360000., 'rotation')
                self.light_rotation = (self.light_gesture['baseline'] + angle + 180.) % 360. - 180.
                # Proporcional, no aditiva: media pantalla arriba multiplica la luz
                # por lo mismo que media pantalla abajo la divide.
                travel = recipes.number(payload.get('energy', 0.), -8., 8., 'energy')
                self.light_energy = min(3., max(.2, self.light_gesture['energy'] * math.exp(1.1 * travel)))
            elif phase == 'end':
                self.light_gesture = None
            else:
                self.cancel_lighting()

    def cancel(self):
        self.cancel_lighting()
        stroke,self.stroke=self.stroke,None
        self.last_point=None
        if not stroke: return
        for r in stroke['objects']:
            obj=bpy.data.objects.get(r['name'])
            try:
                if obj and obj.data==r['new']: obj.data=r['old']
                if r['new'].users==0: bpy.data.meshes.remove(r['new'])
                if r['material'] and r['material'].users==0:
                    layers.dispose(r['material'])
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
