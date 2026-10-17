"""Native vertex groups of the active mesh; Edit weights live in BMesh."""
import bpy
import bmesh
from . import command
from ..errors import BadPayload,CommandError
from ..bpy_utils import active_object,undo_push


def available(obj):
    from ..cad.runtime import FEATURE_KEY,runtime
    from ..materials.runtime import runtime as materials
    return bool(obj and obj.type=='MESH' and obj.mode in ('OBJECT','EDIT')
                and not obj.get(FEATURE_KEY) and not runtime.workspace and not materials.active)


def describe(obj):
    return [dict(name=g.name,locked=bool(g.lock_weight)) for g in obj.vertex_groups] if obj.type=='MESH' else []


def _target(payload):
    obj=active_object()
    if payload.get('object') and payload['object']!=obj.name:
        raise BadPayload('El objeto activo ha cambiado; vuelve a elegir el grupo')
    if not available(obj):raise BadPayload('Los grupos requieren una malla editable en Object o Edit; convierte antes una pieza CAD')
    from .modal import session
    from .tools import tool_session
    from ..cad.runtime import runtime
    if session.active or tool_session.active or runtime.session:
        raise CommandError('Confirma o cancela la herramienta antes de editar grupos',code='session_active')
    return obj


def _group(obj,payload):
    group=obj.vertex_groups.get(str(payload.get('name','')))
    if group is None:raise BadPayload('El grupo de vértices ya no existe')
    return group


def _name(obj,value,current=None):
    if not isinstance(value,str) or not value.strip() or len(value.strip().encode('utf8'))>63:
        raise BadPayload('Escribe un nombre de grupo entre 1 y 63 bytes')
    name=value.strip()
    if obj.vertex_groups.get(name) and name!=current:raise BadPayload('Ya existe un grupo con ese nombre')
    return name


def _selected_ids(obj):
    if obj.mode=='EDIT':
        bm=bmesh.from_edit_mesh(obj.data);bm.verts.index_update()
        return [v.index for v in bm.verts if v.select and not v.hide]
    return [v.index for v in obj.data.vertices if v.select and not v.hide]


def save_selection(objects,name,weight=1.):
    """One shared create-and-assign operation for Edit and painting zones."""
    from .modifiers import _bounded_float
    weight=_bounded_float(weight,'weight',0.,1.)
    objects=list(objects)
    if not objects:raise BadPayload('Selecciona una malla primero')
    selections=[]
    for obj in objects:
        if obj.type!='MESH' or obj.mode not in ('OBJECT','EDIT'):raise BadPayload('La selección debe pertenecer a una malla')
        name=_name(obj,name)
        ids=_selected_ids(obj)
        if not ids:raise BadPayload('Selecciona vértices o caras en Edit antes de guardar el grupo')
        selections.append((obj,ids))
    created=[]
    try:
        for obj,ids in selections:
            old=obj.data;active=obj.vertex_groups.active_index
            # Object-mode saved selections may belong to linked meshes. Painting
            # and modifiers must both leave unselected linked objects untouched.
            if obj.mode=='OBJECT':obj.data=old.copy()
            created.append((obj,old,active,None))
            group=obj.vertex_groups.new(name=name);created[-1]=(obj,old,active,group)
            obj.vertex_groups.active_index=group.index
            if obj.mode=='EDIT':
                bm=bmesh.from_edit_mesh(obj.data);layer=bm.verts.layers.deform.verify()
                bm.verts.ensure_lookup_table()
                for index in ids:bm.verts[index][layer][group.index]=weight
                bmesh.update_edit_mesh(obj.data,loop_triangles=False,destructive=False)
            else:group.add(ids,weight,'REPLACE')
            obj.update_tag(refresh={'DATA'})
    except Exception:
        for obj,old,active,group in reversed(created):
            if group:obj.vertex_groups.remove(group)
            if obj.data!=old:
                copied=obj.data;obj.data=old
                if copied.users==0:bpy.data.meshes.remove(copied)
            obj.vertex_groups.active_index=active
        raise
    return name


def _modifier_references(obj,name):
    # Group-name RNA assignments do not retarget modifier strings automatically.
    return [(mod,p.identifier) for mod in obj.modifiers for p in mod.bl_rna.properties
            if p.type=='STRING' and not p.is_readonly and 'vertex_group' in p.identifier
            and getattr(mod,p.identifier)==name]


def _result(label):
    from .. import state
    undo_push(label)
    return state.snapshot()


@command('vertex_group.create',mutating=True)
def create(payload):
    obj=_target(payload)
    if payload.get('assign_selection'):
        save_selection([obj],payload.get('name','Grupo'),payload.get('weight',1.))
        return _result('Guardar selección como grupo')
    name=_name(obj,payload.get('name','Grupo'))
    group=obj.vertex_groups.new(name=name);obj.vertex_groups.active_index=group.index
    return _result('Remote crear grupo de vértices')


@command('vertex_group.rename',mutating=True)
def rename(payload):
    obj=_target(payload);group=_group(obj,payload)
    name=_name(obj,payload.get('new_name'),current=group.name)
    references=_modifier_references(obj,group.name)
    group.name=name
    for mod,key in references:setattr(mod,key,group.name)
    return _result('Remote renombrar grupo de vértices')


@command('vertex_group.delete',mutating=True)
def delete(payload):
    obj=_target(payload);group=_group(obj,payload)
    references=_modifier_references(obj,group.name)
    obj.vertex_groups.remove(group)
    for mod,key in references:setattr(mod,key,'')
    return _result('Remote borrar grupo de vértices')


@command('vertex_group.edit',mutating=True)
def edit(payload):
    obj=_target(payload);group=_group(obj,payload)
    if obj.mode!='EDIT':raise BadPayload('Entra en Edit para asignar o seleccionar vértices')
    action=payload.get('action')
    if action not in ('ASSIGN','REMOVE','SELECT','DESELECT'):raise BadPayload('Acción de grupo no válida')
    bm=bmesh.from_edit_mesh(obj.data)
    selected=[v for v in bm.verts if v.select and not v.hide]
    if action in ('ASSIGN','REMOVE'):
        if group.lock_weight:raise BadPayload('El grupo está bloqueado en Blender')
        if not selected:raise BadPayload('Selecciona primero los vértices')
    weight=None
    if action=='ASSIGN':
        from .modifiers import _bounded_float
        weight=_bounded_float(payload.get('weight',1.),'weight',0.,1.)
    layer=bm.verts.layers.deform.active
    if action=='ASSIGN' and layer is None:
        layer=bm.verts.layers.deform.verify()
        # Adding a custom-data layer reallocates BMesh vertices.
        selected=[v for v in bm.verts if v.select and not v.hide]
    index=group.index
    if action in ('SELECT','DESELECT'):
        # A group is a vertex selection, also when invoked from Edge/Face mode.
        bpy.context.scene.tool_settings.mesh_select_mode=(True,False,False)
        bm.select_mode={'VERT'}
        if action=='SELECT':
            for face in bm.faces:face.select_set(False)
            for edge in bm.edges:edge.select_set(False)
            for vertex in bm.verts:vertex.select_set(False)
        for vertex in bm.verts:
            if not vertex.hide and layer is not None and index in vertex[layer]:vertex.select_set(action=='SELECT')
        bm.select_flush_mode();bm.select_history.clear()
    else:
        for vertex in selected:
            if action=='ASSIGN':vertex[layer][index]=weight
            elif layer is not None and index in vertex[layer]:del vertex[layer][index]
    obj.vertex_groups.active_index=index
    bmesh.update_edit_mesh(obj.data,loop_triangles=False,destructive=False)
    obj.update_tag(refresh={'DATA'})
    return _result('Remote grupo '+action.lower())
