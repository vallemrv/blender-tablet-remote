"""Cross-body booleans, radial print clearance and temporal dependencies."""
import sys,unittest
from pathlib import Path
from unittest.mock import patch
import bpy
sys.path[:0]=[str(Path(__file__).resolve().parents[1]),str(Path(__file__).resolve().parent)]
from test_cad import CadTests, OWNER, volume
from blender_tablet_remote.cad import document as model,occt
from blender_tablet_remote.cad.runtime import runtime,BODY_KEY
from blender_tablet_remote.commands import cad,cad_operations as ops
from blender_tablet_remote.errors import CommandError

class CombineTests(CadTests):
    def parts(self):
        a=self.draw('RECTANGLE',(0,0),(.04,.04));first=self.extrude(a,.04)
        target=runtime.doc()['features'][-1]['body_id']
        cad.body_create(OWNER);cad.sketch_create(dict(plane='XY',offset=.015,**OWNER))
        source=self.draw('RECTANGLE',(.015,.015),(.025,.025));self.extrude(source,.01)
        return target,runtime.doc()['features'][-1]['body_id'],source,first
    def shapes(self,body):
        result=occt.evaluator.evaluate(runtime.doc())
        tip=result['tips'][body]
        return occt.evaluator._shapes[tip][1]
    def bounds(self,shape):
        from OCP.Bnd import Bnd_Box
        from OCP.BRepBndLib import BRepBndLib
        box=Bnd_Box();BRepBndLib.Add_s(shape,box);a,b=box.CornerMin(),box.CornerMax()
        return [(a.X()/1000,b.X()/1000),(a.Y()/1000,b.Y()/1000),(a.Z()/1000,b.Z()/1000)]
    def test_02mm_clearance_expands_cavity_04mm_per_axis_and_follows_tool(self):
        body,tool,source,first=self.parts();base=self.shapes(body)
        state=ops.combine_begin(dict(body_id=body,tool_body_id=tool,**OWNER))
        self.assertTrue(state['session']['can_confirm'])
        with patch.object(cad,'undo_push') as undo:cad.confirm(OWNER);undo.assert_called_once()
        cavity=occt._boolean('CUT',base,self.shapes(body))
        for low,high in self.bounds(cavity):self.assertAlmostEqual(high-low,.0104,places=6)
        cad.entity_set(dict(entity_id=source,values={'x':.018},**OWNER))
        moved=occt._boolean('CUT',base,self.shapes(body))
        self.assertAlmostEqual(self.bounds(moved)[0][0],.0178,places=6)
        self.assertAlmostEqual(occt._volume(moved),occt._volume(cavity),places=4)
        model.loads(model.dumps(runtime.doc()))
    def test_keep_tool_and_modes_are_reversible(self):
        body,tool,_,_=self.parts();before=bpy.context.scene[model.KEY]
        ops.combine_begin(dict(body_id=body,tool_body_id=tool,clearance=0,keep_tool=False,**OWNER))
        toolobj=next(o for o in runtime.objects(runtime.doc()) if o.get(BODY_KEY)==tool)
        self.assertTrue(toolobj.hide_viewport)
        cad.cancel(OWNER);self.assertEqual(before,bpy.context.scene[model.KEY]);self.assertFalse(toolobj.hide_viewport)
        ops.combine_begin(dict(body_id=body,tool_body_id=tool,operation='INTERSECT',clearance=0,**OWNER));cad.confirm(OWNER)
        f=runtime.doc()['features'][-1]
        self.assertAlmostEqual(occt._volume(self.shapes(body))/1e9,.01**3,places=11)
        cad.feature_set(dict(feature_id=f['id'],operation='UNION',**OWNER))
        self.assertAlmostEqual(occt._volume(self.shapes(body))/1e9,.04**3,places=11)
    def test_cycles_and_tool_deletion_rejected_without_changes(self):
        body,tool,_,_=self.parts()
        ops.combine_begin(dict(body_id=body,tool_body_id=tool,clearance=0,**OWNER));cad.confirm(OWNER)
        before=bpy.context.scene[model.KEY]
        with self.assertRaises(CommandError):ops.combine_begin(dict(body_id=tool,tool_body_id=body,clearance=0,**OWNER))
        with self.assertRaises(CommandError):cad._require_no_dependents(runtime.doc(),tool)
        self.assertEqual(before,bpy.context.scene[model.KEY]);self.assertIsNone(runtime.session)
    def test_rollback_does_not_use_future_tool_geometry(self):
        body,tool,_,first=self.parts();cad.history_rollback(dict(node_id=first,**OWNER))
        before=bpy.context.scene[model.KEY]
        state=ops.combine_begin(dict(body_id=body,tool_body_id=tool,clearance=0,**OWNER))
        self.assertFalse(state['session']['can_confirm']);self.assertTrue(state['error'])
        cad.cancel(OWNER);self.assertEqual(before,bpy.context.scene[model.KEY])

    def test_tool_placement_includes_translation_and_nonuniform_scale(self):
        body,tool,_,_=self.parts()
        obj=next(o for o in runtime.objects(runtime.doc()) if o.get(BODY_KEY)==tool)
        obj.scale=(2,1,1);obj.location.x=-.015;bpy.context.view_layer.update()
        state=ops.combine_begin(dict(body_id=body,tool_body_id=tool,clearance=0,**OWNER))
        self.assertTrue(state['session']['can_confirm'],state['error']);cad.confirm(OWNER)
        self.assertAlmostEqual(occt._volume(self.shapes(body))/1e9,.04**3-.02*.01*.01,places=10)

if __name__=='__main__':
    suite=unittest.TestSuite(CombineTests(n) for n in CombineTests.__dict__ if n.startswith('test_'))
    if not unittest.TextTestRunner(verbosity=2).run(suite).wasSuccessful():raise SystemExit(1)
