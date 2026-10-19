"""Adaptadores de selección común para Materiales y CAD 3D."""
import copy
import bpy
from mathutils import Vector
from ..bpy_utils import find_view3d
from ..camera import camera
from .. import state


def scope():
    from ..materials.runtime import runtime as materials
    from ..cad.runtime import runtime as cad
    return 'MATERIAL' if materials.active else 'CAD' if cad.workspace else None


def snapshot():
    if scope()=='MATERIAL':
        from ..materials.runtime import runtime
        return dict(targets=list(runtime.targets),active_layer=runtime.active_layer,fresh_layer=runtime.fresh_layer,scope=runtime.scope)
    from ..cad.runtime import runtime
    return copy.deepcopy((runtime.selection,runtime.surface.items,runtime.surface._stamps,runtime.active_body_id))


def restore(saved):
    if scope()=='MATERIAL':
        from ..materials.runtime import runtime
        runtime.select(saved['targets'])
        runtime.active_layer=saved['active_layer'];runtime.fresh_layer=saved['fresh_layer'];runtime.scope=saved['scope']
    else:
        from ..cad.runtime import runtime
        runtime.selection,runtime.surface.items,runtime.surface._stamps,runtime.active_body_id=copy.deepcopy(saved)


def key(hit):
    return hit if isinstance(hit,str) else (hit.get('kind'),hit.get('id'))


def hit(u,v,rv3d,region,area,graph,radius=.035):
    if scope()=='MATERIAL':
        from ..materials.runtime import runtime
        from .selection import _object_hit
        with runtime.presentation(area.spaces.active) if area else _nothing():
            origin,direction=camera.ray(u,v,rv3d)
            result=_object_hit(u,v,origin,direction,rv3d,region,area,graph,radius)
        return result[0].name if result and result[0] in runtime.selectable_objects() else None
    from ..cad.runtime import runtime
    if runtime.surface.mode=='PROFILE':
        from .cad import _pick
        result=_pick(dict(u=u,v=v))
        return result if result and result.get('kind') in {'PROFILE','SKETCH','FEATURE'} else None
    from .snap import query_cad_surface
    return query_cad_surface(dict(u=u,v=v),runtime.surface.mode)


from contextlib import nullcontext as _nothing


def apply(hits,mode):
    unique={key(h):h for h in hits if h is not None}
    if scope()=='MATERIAL':
        from ..materials.runtime import runtime
        names=list(runtime.targets) if mode!='SET' else []
        for name in unique.values():
            if name in names:
                if mode in {'TOGGLE','REMOVE'}:names.remove(name)
            elif mode!='REMOVE':names.append(name)
        runtime.select(names)
    else:
        from ..cad.runtime import runtime
        if runtime.surface.mode=='PROFILE':
            from .cad import _refs,_set_selection,_toggle_refs
            refs=copy.deepcopy(_refs()) if mode!='SET' else []
            for item in unique.values():
                present=any(r['id']==item['id'] for r in refs)
                if mode=='REMOVE':refs=[r for r in refs if r['id']!=item['id']]
                elif mode=='TOGGLE' or not present:refs=_toggle_refs(refs,item)
            _set_selection(refs)
        else:
            from ..cad.surface import stamp
            items=copy.deepcopy(runtime.surface.items) if mode!='SET' else []
            for item in unique.values():
                existing=next((r for r in items if r['id']==item['id']),None)
                if existing:
                    if mode in {'TOGGLE','REMOVE'}:items.remove(existing)
                elif mode!='REMOVE':items.append(item)
            runtime.surface.items=items
            runtime.surface._stamps={r['object']:stamp(bpy.data.objects[r['object']]) for r in items}
            last=items[-1] if items else None
            runtime.selection=dict(kind='SURFACE',id=last['id'],feature_id=last['feature_id']) if last else None
    return state.snapshot(include_view=False)


def shape(payload,contains):
    from .selection import _selection_op
    found=find_view3d()
    if not found:return state.snapshot(include_view=False)
    _,area,region,rv3d=found;camera.sync_from_region(rv3d)
    hits=[]
    if scope()=='MATERIAL':
        from ..materials.runtime import runtime
        for obj in runtime.selectable_objects():
            p=camera.project(obj.matrix_world.translation,rv3d)
            if p and contains(*p):hits.append(obj.name)
    else:
        from ..cad.runtime import runtime
        if runtime.surface.mode=='PROFILE':
            for item in runtime.overlay(runtime.doc()):
                points=item.get('points',[])
                if not item.get('closed') or not points or item.get('kind') in {'CONSTRAINT','DIMENSION'}:continue
                p=[sum(q[i] for q in points)/len(points) for i in (0,1)]
                if contains(*p):hits.append(dict(kind='PROFILE',id='profile_'+item['id']))
        else:
            # Sondeo visible sobre la región: la geometría y la oclusión pertenecen
            # al mismo selector CAD que usa el toque, sin seleccionar caras traseras.
            if 'radius' in payload:
                r=float(payload['radius']);u=float(payload['u']);v=float(payload['v'])
                left,right,top,bottom=u-r,u+r,v-r,v+r
            else:
                left,right=sorted((float(payload.get('u0',0)),float(payload.get('u1',1))))
                top,bottom=sorted((float(payload.get('v0',0)),float(payload.get('v1',1))))
            graph=bpy.context.evaluated_depsgraph_get()
            for ix in range(25):
                u=max(0,min(1,left+(right-left)*ix/24))
                for iy in range(25):
                    v=max(0,min(1,top+(bottom-top)*iy/24))
                    if contains(u,v):
                        item=hit(u,v,rv3d,region,area,graph)
                        if item:hits.append(item)
    return apply(hits,_selection_op(payload))
