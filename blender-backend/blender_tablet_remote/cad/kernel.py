"""CadKernel V1: deterministic native mesh extrusion, no binary dependencies.

Constrained triangulation keeps holes; analytic sketch source remains exact while
circles are tessellated only for evaluation/display. No BREP/STEP claim.
"""
from abc import ABC, abstractmethod
from mathutils import Vector
from mathutils.geometry import delaunay_2d_cdt
from .document import outline, contains, closed_entities
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
    if any(_intersects(a,b,c,d) for i,(a,b) in enumerate(zip(outer,outer[1:]+outer[:1]))
           for j,(c,d) in enumerate(zip(outer,outer[1:]+outer[:1]))
           if j>i+1 and not(i==0 and j==len(outer)-1)):
        raise CommandError('El contorno se cruza consigo mismo',code='cad_profile_invalid')
    rings = [outer]
    others = [outline(e) for e in closed_entities(sketch) if e['id'] != source['id']]
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


    @abstractmethod
    def cut(self, base, cutter):
        """Subtract two evaluated meshes, returning a validated solid in metres."""


class BlenderNativeKernel(CadKernel):
    name = 'BLENDER_NATIVE_MESH'

    def cut(self, base, cutter):
        return cut_mesh(base, cutter)

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
        vertices = [world(sketch['plane'], p.x,p.y,z+sketch.get('offset',0)) for z in (0,depth) for p in verts]
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
        if depth < 0:
            polygons = [tuple(reversed(f)) for f in polygons]
        return vertices, polygons


kernel = BlenderNativeKernel()


def cut_mesh(base, cutter):
    """Exact Blender boolean on temporary objects; no operators or scene residue."""
    import bpy
    import bmesh
    meshes, objects = [], []
    try:
        for label,(vertices,faces) in zip(('CAD target','CAD cutter'),(base,cutter)):
            mesh=bpy.data.meshes.new(label); meshes.append(mesh)
            mesh.from_pydata(vertices,[],faces); mesh.update()
            obj=bpy.data.objects.new(label,mesh); objects.append(obj)
            bpy.context.scene.collection.objects.link(obj)
        modifier=objects[0].modifiers.new('CAD difference','BOOLEAN')
        modifier.operation='DIFFERENCE'; modifier.solver='EXACT'; modifier.object=objects[1]
        bpy.context.view_layer.update()
        evaluated=objects[0].evaluated_get(bpy.context.evaluated_depsgraph_get())
        mesh=evaluated.to_mesh()
        try:
            result=([tuple(v.co) for v in mesh.vertices],[tuple(f.vertices) for f in mesh.polygons])
            bm=bmesh.new()
            try:
                bm.from_mesh(mesh)
                valid=bool(bm.faces) and all(e.is_manifold for e in bm.edges) and bm.calc_volume()>1e-18
            finally: bm.free()
            if not valid:
                raise CommandError('El vaciado elimina todo el sólido o produce geometría inválida',code='cad_cut_invalid')
            def volume(data):
                bm=bmesh.new()
                m=bpy.data.meshes.new('CAD volume')
                try:
                    m.from_pydata(data[0],[],data[1]); bm.from_mesh(m)
                    return abs(bm.calc_volume())
                finally:
                    bm.free(); bpy.data.meshes.remove(m)
            base_volume=volume(base)
            if base_volume-volume(result) <= max(base_volume*1e-7,1e-18):
                raise CommandError('El perfil no quita material del sólido destino',code='cad_cut_miss')
            return result
        finally: evaluated.to_mesh_clear()
    finally:
        for obj in objects: bpy.data.objects.remove(obj,do_unlink=True)
        for mesh in meshes:
            if mesh.users==0: bpy.data.meshes.remove(mesh)
