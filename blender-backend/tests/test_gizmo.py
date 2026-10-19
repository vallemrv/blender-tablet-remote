"""Manipulador: blender --background --factory-startup --python-exit-code 1 --python este_archivo."""
import math
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import bpy
from mathutils import Matrix, Quaternion, Vector

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from blender_tablet_remote.commands import gizmo, modal, sessions
from blender_tablet_remote.camera import camera


class GizmoTests(unittest.TestCase):
    def setUp(self):
        sessions.cancel_all()
        if bpy.context.object and bpy.context.object.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')
        bpy.ops.object.select_all(action='SELECT')
        bpy.ops.object.delete(use_global=False)
        bpy.ops.mesh.primitive_cube_add(size=.02)
        self.obj = bpy.context.object
        camera.reset()
        camera._synced = True
        camera.location = Vector()
        camera.rotation = Quaternion((1, 0, 0, 0))  # mira hacia -Z: X a la derecha, Y arriba
        camera.distance = .1
        camera.perspective = 'PERSP'
        camera.set_clipping(.0001, 10)
        self.rv3d = SimpleNamespace(window_matrix=Matrix(((1,0,0,0),(0,2,0,0),(0,0,-1,-.02),(0,0,-1,0))))
        region = SimpleNamespace(width=1000, height=500)
        self.aspect = 2.0
        self.patches = [patch.object(gizmo, 'find_view3d', return_value=(None, None, region, self.rv3d)),
                        patch.object(modal, 'require_rv3d', return_value=self.rv3d),
                        patch.object(modal.state, 'snapshot', return_value={}),
                        patch.object(modal, 'undo_push')]
        for p in self.patches:
            started = p.start()
        self.undo = started
        gizmo.set_enabled({'enabled': True})

    def tearDown(self):
        gizmo._drag = None
        gizmo.set_enabled({'enabled': False})
        sessions.cancel_all()
        for p in reversed(self.patches):
            p.stop()

    def layout(self):
        return gizmo.layout(self.rv3d, self.aspect)

    def uv(self, point):
        return dict(u=point.x / self.aspect, v=point.y)

    def axis(self, name):
        return next(a for a in self.layout()['axes'] if a['name'] == name)

    def drag(self, start, end):
        begin = gizmo.drag(dict(phase='BEGIN', _client_id='tablet', **self.uv(start)))
        gizmo.drag(dict(phase='UPDATE', _client_id='tablet', dx=0, dy=0, **self.uv(end)))
        return begin, gizmo.drag(dict(phase='END', _client_id='tablet', **self.uv(end)))

    def test_axes_facing_the_camera_have_no_arrow(self):
        visible = {a['name']: a['visible'] for a in self.layout()['axes']}
        self.assertEqual(visible, {'X': True, 'Y': True, 'Z': False})
        x, y = self.axis('X')['direction'], self.axis('Y')['direction']
        self.assertAlmostEqual(x.x, 1.0, places=5)
        self.assertAlmostEqual(y.y, -1.0, places=5)  # pantalla con y hacia abajo

    def test_rings_seen_edge_on_are_hidden(self):
        rings = {a['name']: bool(a['ring']) for a in self.layout()['axes']}
        self.assertEqual(rings, {'X': False, 'Y': False, 'Z': True})

    def test_planar_views_hide_normal_axis_for_every_handle_and_hit_test(self):
        for view, normal in [('TOP','Z'),('BOTTOM','Z'),('FRONT','Y'),('BACK','Y'),('LEFT','X'),('RIGHT','X')]:
            with self.subTest(view=view):
                camera.set_axis_view(view)
                layout=self.layout()
                axis=next(a for a in layout['axes'] if a['name']==normal)
                self.assertFalse(axis['visible']);self.assertEqual(axis['ring'],[])
                for step in range(64):
                    angle=step*math.tau/64
                    hit=gizmo.hit(layout,layout['origin']+Vector((math.cos(angle),math.sin(angle)))*gizmo.RING)
                    self.assertFalse(hit and hit[1] and hit[1]['name']==normal)
        camera.orbit(.2,.2,1.0)
        self.assertIsNone(camera.axis_view)
        self.assertTrue(any(a['ring'] for a in self.layout()['axes']))

    def test_hit_priorities(self):
        layout = self.layout()
        origin, x = layout['origin'], self.axis('X')
        self.assertEqual(gizmo.hit(layout, origin), ('MOVE', None))
        mode, axis = gizmo.hit(layout, origin + x['direction'] * gizmo.ARROW * .8)
        self.assertEqual((mode, axis['name']), ('MOVE', 'X'))
        mode, axis = gizmo.hit(layout, origin + x['direction'] * gizmo.SCALE_BOX)
        self.assertEqual((mode, axis['name']), ('SCALE', 'X'))
        mode, axis = gizmo.hit(layout, origin + Vector((0.7071, 0.7071)) * gizmo.RING)
        self.assertEqual((mode, axis['name']), ('ROTATE', 'Z'))
        self.assertEqual(gizmo.hit(layout, origin + Vector((0.7071, 0.7071)) * gizmo.UNIFORM), ('SCALE', None))
        self.assertIsNone(gizmo.hit(layout, origin + Vector((0.4, 0.4))))

    def test_move_along_axis_follows_the_finger_with_one_undo(self):
        layout, x = self.layout(), self.axis('X')
        start = layout['origin'] + x['direction'] * gizmo.ARROW * .8
        end = start + Vector((0.03, 0.02))
        begin, result = self.drag(start, end)
        self.assertTrue(begin['hit'])
        self.assertTrue(result['moved'])
        self.assertAlmostEqual(self.obj.location.x, 0.03 / x['scale'], places=6)
        self.assertAlmostEqual(self.obj.location.y, 0.0, places=9)
        self.assertEqual(self.undo.call_count, 1)
        self.assertEqual(result['gizmo_finished'], begin['session_id'])
        self.assertFalse(modal.session.active)

    def test_rotate_around_z_follows_the_finger(self):
        origin = self.layout()['origin']
        start = origin + Vector((1, 0)) * gizmo.RING
        end = origin + Vector((0, -1)) * gizmo.RING  # cuarto de vuelta antihorario en pantalla
        steps = [origin + Vector((math.cos(a), -math.sin(a))) * gizmo.RING for a in (0.4, 0.8, 1.2)]
        gizmo.drag(dict(phase='BEGIN', _client_id='tablet', **self.uv(start)))
        for point in steps + [end]:
            gizmo.drag(dict(phase='UPDATE', _client_id='tablet', **self.uv(point)))
        gizmo.drag(dict(phase='END', _client_id='tablet', **self.uv(end)))
        self.assertAlmostEqual(self.obj.rotation_euler.z, math.pi / 2, places=4)

    def test_scale_axis_and_uniform(self):
        layout, x = self.layout(), self.axis('X')
        start = layout['origin'] + x['direction'] * gizmo.SCALE_BOX
        self.drag(start, layout['origin'] + x['direction'] * gizmo.SCALE_BOX * 2)
        self.assertAlmostEqual(self.obj.scale.x, 2.0, places=5)
        self.assertAlmostEqual(self.obj.scale.y, 1.0, places=6)
        origin = self.layout()['origin']
        self.drag(origin + Vector((0, -1)) * gizmo.UNIFORM, origin + Vector((0, -1)) * gizmo.UNIFORM * .5)
        self.assertAlmostEqual(self.obj.scale.y, 0.5, places=5)
        self.assertEqual(self.undo.call_count, 2)

    def test_increment_snaps_the_axis_value(self):
        layout, x = self.layout(), self.axis('X')
        start = layout['origin'] + x['direction'] * gizmo.ARROW * .8
        gizmo.drag(dict(phase='BEGIN', _client_id='tablet', snap_type='INCREMENT',
                        steps={'MOVE': .01}, **self.uv(start)))
        end = start + Vector((0.013 * x['scale'], 0))
        gizmo.drag(dict(phase='UPDATE', _client_id='tablet', **self.uv(end)))
        gizmo.drag(dict(phase='END', _client_id='tablet', **self.uv(end)))
        self.assertAlmostEqual(self.obj.location.x, 0.01, places=6)

    def test_miss_orbits_and_tap_without_motion_creates_no_undo(self):
        with patch('blender_tablet_remote.commands.view.orbit_delta') as orbit:
            begin = gizmo.drag(dict(phase='BEGIN', _client_id='tablet', u=.05, v=.05))
            self.assertFalse(begin['hit'])
            gizmo.drag(dict(phase='UPDATE', _client_id='tablet', dx=.1, dy=0, u=.15, v=.05))
            gizmo.drag(dict(phase='END', _client_id='tablet', u=.15, v=.05))
            orbit.assert_called_once()
        origin = self.layout()['origin']
        _begin, result = self.drag(origin, origin)
        self.assertFalse(result['moved'])
        self.undo.assert_not_called()

    def test_edit_moves_selected_vertices_from_their_center(self):
        import bmesh
        bpy.ops.object.mode_set(mode='EDIT')
        bm = bmesh.from_edit_mesh(self.obj.data)
        for vert in bm.verts:
            vert.select = vert.co.x > 0
        bm.select_flush(True)
        bmesh.update_edit_mesh(self.obj.data)
        layout = self.layout()
        self.assertAlmostEqual(layout['center'].x, .01, places=6)
        x = self.axis('X')
        start = layout['origin'] + x['direction'] * gizmo.ARROW * .8
        self.drag(start, start + Vector((0.02, 0)))
        bm = bmesh.from_edit_mesh(self.obj.data)
        moved = sorted(round(v.co.x, 6) for v in bm.verts)
        self.assertEqual(moved[:4], [-.01] * 4)
        self.assertAlmostEqual(moved[-1], .01 + .02 / x['scale'], places=5)
        bpy.ops.object.mode_set(mode='OBJECT')

    def test_draw_paths_cover_handles_and_guide(self):
        from blender_tablet_remote.streaming.markers import gizmo_paths
        layout = self.layout()
        paths = gizmo_paths(layout, 500)
        # Anillo Z, aro uniforme, flecha+punta+caja de X e Y, y centro.
        self.assertEqual(len(paths), 1 + 1 + 3 * 2 + 1)
        guide = gizmo_paths(layout, 500, {'mode': 'ROTATE', 'axis': self.axis('Z')})
        self.assertEqual(len(guide), 1)

    def test_hidden_while_another_session_is_open(self):
        modal.session.begin('MOVE', [], False, None, owner_id='tablet')
        self.assertFalse(gizmo.visible())
        modal.session.restore(); modal.session.reset()
        gizmo.set_enabled({'enabled': False})
        self.assertFalse(gizmo.visible())


if __name__ == '__main__':
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(GizmoTests)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    if not result.wasSuccessful(): raise SystemExit(1)
