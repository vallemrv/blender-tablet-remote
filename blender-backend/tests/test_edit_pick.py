"""Toque en Edit: blender --background --factory-startup --python-exit-code 1 --python este_archivo."""
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import bpy
import bmesh
from mathutils import Matrix, Quaternion, Vector

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from blender_tablet_remote.commands import selection
from blender_tablet_remote.camera import camera


class EditPickTests(unittest.TestCase):
    def setUp(self):
        if bpy.context.object and bpy.context.object.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')
        bpy.ops.object.select_all(action='SELECT')
        bpy.ops.object.delete(use_global=False)
        # Un objeto de fondo, detrás del cubo editado, no debe contar como impacto.
        bpy.ops.mesh.primitive_plane_add(size=1, location=(0, 0, -.05))
        bpy.ops.mesh.primitive_cube_add(size=.02)
        self.obj = bpy.context.object
        bpy.context.scene.tool_settings.mesh_select_mode = (True, False, False)
        bpy.ops.object.mode_set(mode='EDIT')
        self.bm = bmesh.from_edit_mesh(self.obj.data)
        self.bm.verts.ensure_lookup_table()
        selection.sel_elements(dict(mode='SET'))
        camera.reset()
        camera._synced = True
        camera.location = Vector()
        camera.rotation = Quaternion((1, 0, 0, 0))
        camera.distance = .1
        camera.perspective = 'PERSP'
        camera.set_clipping(.0001, 10)
        self.rv3d = SimpleNamespace(window_matrix=Matrix(((1,0,0,0),(0,2,0,0),(0,0,-1,-.02),(0,0,-1,0))))
        region = SimpleNamespace(width=1000, height=500)
        self.patches = [patch.object(selection, 'find_view3d', return_value=(None, None, region, self.rv3d)),
                        patch.object(selection.state, 'snapshot', return_value={})]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in reversed(self.patches):
            p.stop()

    def top_vertex(self, sx, sy):
        return next(v for v in self.bm.verts if v.co.z > 0 and v.co.x * sx > 0 and v.co.y * sy > 0)

    def tap(self, vert, mode='TOGGLE'):
        point = vert.co * .98
        u, v = camera.project(point, self.rv3d)
        return selection.pick(dict(u=u, v=v, mode=mode, threshold=.05))

    def selected(self):
        return {v.index for v in self.bm.verts if v.select}

    def test_toggle_accumulates_and_removes(self):
        a, b = self.top_vertex(1, 1), self.top_vertex(-1, 1)
        self.assertTrue(self.tap(a)['hit'])
        self.tap(b)
        self.assertEqual(self.selected(), {a.index, b.index})
        self.tap(a)
        self.assertEqual(self.selected(), {b.index})

    def test_empty_tap_deselects_even_over_background_object(self):
        self.tap(self.top_vertex(1, 1))
        self.assertTrue(self.selected())
        result = selection.pick(dict(u=.05, v=.05, mode='TOGGLE'))
        self.assertFalse(result['hit'])
        self.assertEqual(self.selected(), set())

    def test_remove_miss_keeps_selection(self):
        a = self.top_vertex(1, 1)
        self.tap(a)
        selection.pick(dict(u=.05, v=.05, mode='REMOVE'))
        self.assertEqual(self.selected(), {a.index})

    def double_tap(self, point):
        """Lo que envía Android en el segundo toque: ADD sobre lo tocado y su loop."""
        u, v = camera.project(point, self.rv3d)
        selection.pick(dict(u=u, v=v, mode='TOGGLE', threshold=.05))
        selection.pick(dict(u=u, v=v, mode='ADD', threshold=.05))
        selection.loop_select(dict(mode='ADD'))

    def test_double_tap_on_edge_selects_its_loop(self):
        bpy.context.scene.tool_settings.mesh_select_mode = (False, True, False)
        # Un cubo simple no tiene loops (vértices de valencia 3); subdividido, el
        # loop que pasa por el centro de la tapa rodea el cubo en ocho aristas.
        bmesh.ops.subdivide_edges(self.bm, edges=self.bm.edges[:], cuts=1, use_grid_fill=True)
        bmesh.update_edit_mesh(self.obj.data)
        self.double_tap(Vector((.005, 0, .01)) * .98)
        self.assertEqual(sum(e.select for e in self.bm.edges), 8)

    def test_double_tap_on_face_selects_its_strip(self):
        bpy.context.scene.tool_settings.mesh_select_mode = (False, False, True)
        near_edge = Vector((.009, 0, .01))
        self.double_tap(near_edge)
        self.assertEqual(sum(f.select for f in self.bm.faces), 4)


if __name__ == '__main__':
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(EditPickTests)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    if not result.wasSuccessful(): raise SystemExit(1)
