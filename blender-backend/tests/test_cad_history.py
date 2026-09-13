"""CAD operation stack: rollback bar, insertion at the bar and guards."""
import math
import sys
import unittest
from pathlib import Path
import bpy
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
sys.path.insert(0,str(Path(__file__).resolve().parent))
from test_cad import CadTests, OWNER, volume
from blender_tablet_remote.cad import document as model
from blender_tablet_remote.cad.runtime import runtime, FEATURE_KEY
from blender_tablet_remote.commands import cad, history
from blender_tablet_remote.errors import CommandError


class HistoryTests(CadTests):
    def stack(self):
        return [n['id'] for n in model.history(runtime.doc())]

    def visible_volume(self):
        return sum(volume(o) for o in runtime.objects(runtime.doc()) if o.visible_get())

    def test_rollback_hides_later_features_and_final_restores_them(self):
        s1=runtime.active_sketch_id
        first=self.rect(); f1=self.extrude(first)
        cad.sketch_create(dict(plane='XY',**OWNER)); second=runtime.active_sketch_id
        f2=self.extrude(self.draw('CIRCLE',(.02,.02),(.025,.02)))
        bar=self.stack()[1]  # Extrusión 1
        status=cad.history_rollback(dict(node_id=bar,**OWNER))
        self.assertEqual(status['rollback_id'],bar)
        shown=[o[FEATURE_KEY] for o in runtime.objects(runtime.doc()) if o.visible_get()]
        self.assertEqual(shown,[f1])
        with self.assertRaises(CommandError): cad.feature_set(dict(feature_id=f2,depth=.03,**OWNER))
        with self.assertRaises(CommandError): cad.sketch_activate(dict(sketch_id=second,**OWNER))
        status=cad.history_rollback(OWNER)
        self.assertIsNone(status['rollback_id'])
        shown={o[FEATURE_KEY] for o in runtime.objects(runtime.doc()) if o.visible_get()}
        self.assertEqual(shown,{f1,f2})

    def test_tap_node_shows_object_at_that_moment(self):
        first=self.rect(); self.extrude(first,.02)
        cad.sketch_create(dict(support_id=self.stack()[1],**OWNER))
        f2=self.extrude(self.draw('CIRCLE',(.02,.02),(.025,.02)),.03)
        full=self.visible_volume()
        bar=self.stack()[1]
        cad.history_rollback(dict(node_id=bar,**OWNER))
        cut=self.visible_volume()
        self.assertLess(cut,full)
        self.assertAlmostEqual(cut,.08*.045*.02,places=9)

    def test_new_nodes_insert_after_the_bar_and_advance_the_view_on_confirm(self):
        s1=runtime.active_sketch_id
        first=self.rect(); f1=self.extrude(first)
        cad.sketch_create(dict(plane='XY',**OWNER))
        f2=self.extrude(self.draw('CIRCLE',(.02,.02),(.025,.02)))
        bar=self.stack()[1]
        cad.history_rollback(dict(node_id=bar,**OWNER))
        cad.sketch_create(dict(plane='XZ',**OWNER))
        sequence=self.stack()
        self.assertEqual(sequence.index(runtime.active_sketch_id),sequence.index(bar)+1)
        # Roll back the sketch view: the inserted sketch is future history again.
        cad.sketch_activate(dict(sketch_id=s1,**OWNER))
        status=cad.extrude_begin(dict(profile_id='profile_'+first,depth=.01,operation='EXTRUDE',**OWNER))
        new=status['selection']['id']
        cad.confirm(OWNER)
        sequence=self.stack()
        self.assertEqual(sequence.index(new),sequence.index(bar)+1)
        self.assertEqual(runtime.status()['rollback_id'],new)
        cad.history_rollback(OWNER)
        shown={o[FEATURE_KEY] for o in runtime.objects(runtime.doc()) if o.visible_get()}
        self.assertEqual(shown,{f1,f2,new})

    def test_transactions_while_rolled_back_keep_the_view(self):
        s1=runtime.active_sketch_id
        first=self.rect(); f1=self.extrude(first)
        cad.sketch_create(dict(support_id=f1,**OWNER))
        circle=self.draw('CIRCLE',(.02,.02),(.025,.02))
        self.extrude(circle)
        bar=self.stack()[1]
        cad.history_rollback(dict(node_id=bar,**OWNER))
        cad.sketch_activate(dict(sketch_id=s1,**OWNER))
        entity=runtime.doc()['sketches'][0]['entities'][0]
        cad.entity_set(dict(entity_id=entity['id'],values=dict(width=.04),**OWNER))
        self.assertAlmostEqual(self.visible_volume(),.04*.045*.02,places=9)
        cad.history_rollback(OWNER)
        self.assertAlmostEqual(self.visible_volume(),.04*.045*.02+math.pi*.005**2*.02,delta=2e-9)

    def test_rollback_navigation_never_creates_undo_steps(self):
        self.rect(); self.extrude(self.draw('CIRCLE',(.02,.02),(.025,.02)))
        before=model.dumps(runtime.doc())
        cad.history_rollback(dict(node_id=self.stack()[0],**OWNER))
        cad.history_rollback(OWNER)
        self.assertEqual(model.dumps(runtime.doc()),before)
        self.assertTrue(bpy.context.scene.get(model.KEY))

    def test_rollback_while_editing_a_future_sketch_leaves_the_sketch_view(self):
        first=self.rect(); f1=self.extrude(first)
        cad.sketch_create(dict(plane='XY',**OWNER)); future=runtime.active_sketch_id
        bar=self.stack()[1]
        cad.sketch_activate(dict(sketch_id=future,**OWNER))
        status=cad.history_rollback(dict(node_id=bar,**OWNER))
        self.assertIsNone(status['active_sketch_id'])

    def test_overlay_draws_sketch_inserted_at_the_bar_while_editing(self):
        first=self.rect(); f1=self.extrude(first)
        bar=self.stack()[1]
        cad.history_rollback(dict(node_id=bar,**OWNER))
        cad.sketch_create(dict(plane='XZ',**OWNER))
        entity=self.draw('LINE',(-.01,0),(0,.01))
        self.assertIn(entity,[item['id'] for item in cad.state(OWNER)['overlay']])
        cad.sketch_finish(OWNER)
        self.assertNotIn(entity,[item['id'] for item in cad.state(OWNER)['overlay']])

    def test_unknown_rollback_node_is_rejected(self):
        self.rect()
        with self.assertRaises(CommandError):
            cad.history_rollback(dict(node_id='feature_missing',**OWNER))

    @unittest.skipIf(bpy.app.background,'GUI undo stack required')
    def test_undo_after_insertion_at_bar_restores_previous_document(self):
        from blender_tablet_remote.commands import history
        self.rect(); self.extrude(self.rect())
        bar=self.stack()[1]
        cad.history_rollback(dict(node_id=bar,**OWNER))
        cad.sketch_create(dict(plane='XZ',**OWNER))
        circle=self.draw('CIRCLE',(.01,.01),(.02,.01))
        self.extrude('profile_'+circle)
        self.assertEqual(runtime.status()['rollback_id'],self.stack()[-1])
        history.undo({})
        self.assertEqual(len(runtime.doc()['features']),1)
        self.assertEqual(len(runtime.doc()['sketches']),2)
        self.assertIsNone(runtime.status()['rollback_id'])
        history.redo({})
        self.assertEqual(runtime.status()['rollback_id'],self.stack()[-1])


def run():
    result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(HistoryTests))
    if not result.wasSuccessful():
        import os
        os._exit(1)
    if not bpy.app.background: bpy.ops.wm.quit_blender()

if __name__=='__main__':
    if bpy.app.background: run()
    else: bpy.app.timers.register(run,first_interval=1.)
