"""Transient solid selection and SI measurements; evaluated IDs never enter the CAD document."""
import hashlib
import math
import bpy
import numpy as np
from mathutils import Vector
from ..errors import BadPayload, CommandError


def stamp(obj):
    mesh=obj.evaluated_get(bpy.context.evaluated_depsgraph_get()).data
    coords=np.empty(len(mesh.vertices)*3,dtype=np.float32); mesh.vertices.foreach_get('co',coords)
    loops=np.empty(len(mesh.loops),dtype=np.int32); mesh.loops.foreach_get('vertex_index',loops)
    digest=hashlib.blake2b(digest_size=16)
    digest.update(coords.tobytes()); digest.update(loops.tobytes())
    digest.update(np.asarray(obj.matrix_world,dtype=np.float32).tobytes())
    digest.update(str(bpy.context.scene.unit_settings.scale_length).encode())
    return obj.as_pointer(),obj.data.as_pointer(),digest.digest()


def point_segment(p,a,b):
    d=b-a; t=max(0.,min(1.,(p-a).dot(d)/max(d.length_squared,1e-30)))
    return (p-(a+d*t)).length


def segment_distance(a,b,c,d):
    u,v,w=b-a,d-c,a-c
    aa,bb,cc,dd,ee=u.dot(u),u.dot(v),v.dot(v),u.dot(w),v.dot(w)
    denom=aa*cc-bb*bb
    values=[point_segment(a,c,d),point_segment(b,c,d),point_segment(c,a,b),point_segment(d,a,b)]
    if denom>1e-14*max(aa*cc,1e-30):
        s=(bb*ee-cc*dd)/denom; t=(aa*ee-bb*dd)/denom
        if 0<=s<=1 and 0<=t<=1: values.append((a+s*u-c-t*v).length)
    return min(values)


def measurements(items, scale):
    result=[]
    def add(label,value,unit): result.append(dict(label=label,value=float(value),unit=unit))
    for i,item in enumerate(items):
        suffix=' '+str(i+1) if len(items)>1 else ''
        segments=[(Vector(a),Vector(b)) for a,b in item['segments']]
        if item['kind']=='EDGE': add('Longitud'+suffix,sum((b-a).length for a,b in segments)*scale,'LENGTH')
        elif item['kind']=='FACE':
            area=sum((Vector(b)-Vector(a)).cross(Vector(c)-Vector(a)).length*.5 for a,b,c in item['triangles'])
            add('Área'+suffix,area*scale*scale,'AREA')
            add('Perímetro'+suffix,sum((b-a).length for a,b in segments)*scale,'LENGTH')
    if len(items)!=2: return result
    a,b=items
    if a['kind']=='FACE' or b['kind']=='FACE':
        face,other=(a,b) if a['kind']=='FACE' else (b,a)
        if not face['planar']: return result
        normal=Vector(face['normal']); origin=Vector(face['center'])
        if other['kind']=='FACE':
            if not other['planar']: return result
            cosine=max(-1.,min(1.,normal.dot(Vector(other['normal']))))
            add('Ángulo entre caras',math.degrees(math.acos(abs(cosine))),'ANGLE')
            if abs(cosine)>1-1e-6: add('Separación entre planos',abs((Vector(other['center'])-origin).dot(normal))*scale,'LENGTH')
        else:
            distances=[(Vector(p)-origin).dot(normal) for p in other['points']]
            value=0. if min(distances)<=0<=max(distances) else min(abs(v) for v in distances)
            add('Distancia al plano',value*scale,'LENGTH')
    elif a['kind']=='VERTEX' and b['kind']=='VERTEX': add('Distancia',(Vector(a['points'][0])-Vector(b['points'][0])).length*scale,'LENGTH')
    elif a['kind']=='EDGE' and b['kind']=='EDGE':
        first=[tuple(Vector(p) for p in edge) for edge in a['segments']]
        second=[tuple(Vector(p) for p in edge) for edge in b['segments']]
        add('Distancia entre aristas',min(segment_distance(*s,*t) for s in first for t in second)*scale,'LENGTH')
        u=(first[0][1]-first[0][0]).normalized(); v=(second[0][1]-second[0][0]).normalized()
        add('Ángulo entre aristas',math.degrees(math.acos(min(1.,abs(u.dot(v))))),'ANGLE')
    else:
        point,edge=(a,b) if a['kind']=='VERTEX' else (b,a)
        p=Vector(point['points'][0])
        add('Distancia a arista',min(point_segment(p,Vector(x),Vector(y)) for x,y in edge['segments'])*scale,'LENGTH')
    return result


class SurfaceSelection:
    def __init__(self):
        self.mode='PROFILE'
        self.items=[]
        self._stamps={}

    def clear(self):
        self.items=[]; self._stamps={}

    def validate(self):
        valid=[]
        for item in self.items:
            obj=bpy.data.objects.get(item['object'])
            try:
                if obj and obj.type=='MESH' and obj.visible_get() and stamp(obj)==self._stamps.get(item['object']): valid.append(item)
            except (ReferenceError,RuntimeError): pass
        self.items=valid
        names={item['object'] for item in valid}
        self._stamps={name:value for name,value in self._stamps.items() if name in names}

    def select(self, payload):
        from ..commands.snap import query_cad_surface
        self.validate()
        item=query_cad_surface(payload,self.mode)
        if item is None: self.clear(); return
        old=next((i for i in self.items if i['id']==item['id']),None)
        if old: self.items.remove(old); return
        # Two references are enough for a measurement; a third starts a fresh pair.
        if len(self.items)>=2: self.clear()
        self.items.append(item)
        self._stamps[item['object']]=stamp(bpy.data.objects[item['object']])

    def face_frame(self):
        self.validate()
        if len(self.items)!=1 or self.items[0]['kind']!='FACE' or not self.items[0]['planar']:
            raise BadPayload('Selecciona una única cara plana resaltada')
        face=self.items[0]; normal=Vector(face['normal'])
        if not face['segments']: raise BadPayload('La cara no tiene un contorno utilizable')
        a,b=map(Vector,max(face['segments'],key=lambda edge:(Vector(edge[1])-Vector(edge[0])).length))
        x=(b-a).normalized(); y=normal.cross(x).normalized(); x=y.cross(normal).normalized()
        scale=bpy.context.scene.unit_settings.scale_length
        return dict(origin=list(Vector(face['center'])*scale),x=list(x),y=list(y),normal=list(normal))

    def status(self):
        self.validate()
        return dict(mode=self.mode,selection=[{k:item[k] for k in ('id','kind','object','feature_id','planar')} for item in self.items],
                    measurements=measurements(self.items,bpy.context.scene.unit_settings.scale_length),
                    can_sketch=len(self.items)==1 and self.items[0]['kind']=='FACE' and self.items[0]['planar'])
