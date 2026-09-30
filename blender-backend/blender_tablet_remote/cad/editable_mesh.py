"""Compact editable CAD copies; preserve design boundaries instead of adding a grid."""
import bmesh

from ..errors import CommandError


def clean_mesh(mesh):
    """Clean only the owned copy, in its local units, preserving mesh attributes.

    Boolean seams can contain coincident vertices even in a closed manifold.
    Welding those seams before dissolving nearly coplanar divisions avoids
    multiplying zero-length edges into degenerate quads during export.
    Curved contours, holes, material boundaries and marked seams stay intact.
    """
    bm = bmesh.new()
    try:
        bm.from_mesh(mesh)
        if not bm.faces:
            raise CommandError('El cuerpo no tiene caras para crear una copia', code='cad_mesh_invalid')
        extent = max(max(v.co[i] for v in bm.verts) - min(v.co[i] for v in bm.verts) for i in range(3))
        tolerance = extent * 1e-7
        volume = abs(bm.calc_volume())
        bmesh.ops.remove_doubles(bm, verts=list(bm.verts), dist=tolerance)
        bmesh.ops.dissolve_degenerate(bm, edges=list(bm.edges), dist=tolerance)
        bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))
        bm.normal_update()
        bmesh.ops.dissolve_limit(
            bm, angle_limit=.001, verts=list(bm.verts), edges=list(bm.edges),
            use_dissolve_boundaries=False, delimit={'MATERIAL', 'SEAM', 'SHARP', 'UV'},
        )
        # Collapsed boolean slivers may survive dissolution as wires. They have
        # no surface or volume; remove only these leftovers, never boundary edges.
        wires=[e for e in bm.edges if not e.link_faces]
        if wires: bmesh.ops.delete(bm,geom=wires,context='EDGES')
        loose=[v for v in bm.verts if not v.link_edges]
        if loose: bmesh.ops.delete(bm,geom=loose,context='VERTS')
        bm.normal_update()
        if (not bm.faces or any(not e.is_manifold for e in bm.edges)
                or any(e.calc_length() <= tolerance * .01 for e in bm.edges)
                or any(f.calc_area() <= tolerance * tolerance for f in bm.faces)
                or abs(abs(bm.calc_volume()) - volume) > max(volume * 1e-6, extent**3 * 1e-10)):
            raise CommandError('No se pudo crear una copia limpia conservando el sólido', code='cad_mesh_invalid')
        bm.to_mesh(mesh)
        mesh.update()
    finally:
        bm.free()
