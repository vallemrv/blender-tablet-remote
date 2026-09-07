"""CadKernel V1: deterministic native mesh extrusion, no binary dependencies.

Constrained triangulation keeps holes; analytic sketch source remains exact while
circles are tessellated only for evaluation/display. No BREP/STEP claim.
"""
from abc import ABC, abstractmethod
from mathutils import Vector
from mathutils.geometry import delaunay_2d_cdt
from .document import outline, contains
from ..errors import CommandError


def world(plane, x, y, z=0):
    return {'XY': (x,y,z), 'XZ': (x,-z,y), 'YZ': (z,x,y)}[plane]


def _intersects(a,b,c,d):
    def cross(p,q,r):
        return (q[0]-p[0])*(r[1]-p[1])-(q[1]-p[1])*(r[0]-p[0])
    def on(p,q,r):
        return min(p[0],q[0])-1e-10 <= r[0] <= max(p[0],q[0])+1e-10 and min(p[1],q[1])-1e-10 <= r[1] <= max(p[1],q[1])+1e-10
    s,t,u,v = cross(a,b,c),cross(a,b,d),cross(c,d,a),cross(c,d,b)
    if s*t < 0 and u*v < 0:
        return True
    return any(abs(k)<1e-12 and on(p,q,r) for k,p,q,r in ((s,a,b,c),(t,a,b,d),(u,c,d,a),(v,c,d,b)))


def region(sketch, source):
    outer = outline(source)
    rings = [outer]
    others = [outline(e) for e in sketch['entities'] if e['id'] != source['id'] and e['type'] != 'LINE']
    for other in others:
        if any(_intersects(a,b,c,d) for a,b in zip(outer,outer[1:]+outer[:1])
               for c,d in zip(other,other[1:]+other[:1])):
            raise CommandError('Los contornos se cruzan o se tocan; sepáralos antes de extruir', code='cad_profile_invalid')
        if contains(outer, other[0]):
            rings.append(list(reversed(other)))
    for i, a in enumerate(rings[1:]):
        for b in rings[i+2:]:
            if contains(a,b[0]) or contains(b,a[0]) or any(
                    _intersects(p,q,r,s) for p,q in zip(a,a[1:]+a[:1]) for r,s in zip(b,b[1:]+b[:1])):
                raise CommandError('Los huecos anidados o solapados no están admitidos en V1', code='cad_profile_invalid')
    return rings


class CadKernel(ABC):
    @abstractmethod
    def extrude(self, sketch, source, depth):
        """Return vertices and polygon indices in metres."""


class BlenderNativeKernel(CadKernel):
    name = 'BLENDER_NATIVE_MESH'

    def extrude(self, sketch, source, depth):
        rings = region(sketch, source)
        points, edges = [], []
        for ring in rings:
            start = len(points)
            points.extend(Vector(p) for p in ring)
            edges.extend((start+i, start+(i+1)%len(ring)) for i in range(len(ring)))
        # CDT may reorder vertices; use its returned coordinates for caps and use
        # coordinate lookup for walls. No evaluated index is persisted as identity.
        verts, _, faces, _, _, _ = delaunay_2d_cdt(points, edges, [], 0, 1e-9)
        n = len(verts)
        vertices = [world(sketch['plane'], p.x,p.y,z) for z in (0,depth) for p in verts]
        polygons = []
        for face in faces:
            center = tuple(sum(verts[i][axis] for i in face)/len(face) for axis in (0,1))
            if contains(rings[0],center) and not any(contains(r,center) for r in rings[1:]):
                polygons.append(tuple(reversed(face)))
                polygons.append(tuple(i+n for i in face))
        for ring in rings:
            ids = [min(range(n),key=lambda i:(verts[i]-Vector(p)).length_squared) for p in ring]
            for a,b in zip(ids, ids[1:]+ids[:1]):
                polygons.append((a,b,b+n,a+n))
        if not polygons:
            raise CommandError('El perfil no genera un sólido', code='cad_profile_invalid')
        return vertices, polygons


kernel = BlenderNativeKernel()
