"""python blender-backend/tests/test_sculpt_samples.py"""
import importlib.util
from pathlib import Path
import unittest

spec=importlib.util.spec_from_file_location('samples',Path(__file__).resolve().parents[1]/'blender_tablet_remote/sculpt_samples.py')
samples=importlib.util.module_from_spec(spec);spec.loader.exec_module(samples)

def point(x,pressure=1,time=0,y=.5):return dict(u=x,v=y,pressure=pressure,time=time)

class BrushSampleTests(unittest.TestCase):
    def test_dense_history_and_network_chunking_have_same_daubs(self):
        dense=[point(i/1000,.25+i/800,i/400) for i in range(401)]
        whole=samples.BrushSamples(.1,1)
        a,tail=whole.feed(dense)
        chunked=samples.BrushSamples(.1,1)
        b=[]
        for p in dense:
            part,last=chunked.feed([p]);b.extend(part)
        sparse=samples.BrushSamples(.1,1)
        c,_=sparse.feed([dense[0],dense[-1]])
        self.assertEqual(len(a),5)
        self.assertEqual(len(a),len(b));self.assertEqual(len(a),len(c))
        for actual,expected in zip(b+c,a+a):
            for key in ('u','v','pressure','time'):self.assertAlmostEqual(actual[key],expected[key],places=9)
        self.assertIsNone(tail);self.assertIsNone(last)

    def test_endpoint_preview_does_not_accumulate_packet_daubs(self):
        sampler=samples.BrushSamples(.1,1)
        self.assertEqual(len(sampler.feed([point(0)])[0]),1)
        for x in (.02,.04,.06):
            daubs,tail=sampler.feed([point(x)])
            self.assertEqual(daubs,[]);self.assertEqual(tail['u'],x)
        daubs,tail=sampler.feed([point(.1)])
        self.assertEqual(len(daubs),1);self.assertIsNone(tail)

    def test_aspect_and_pressure_size_control_spacing(self):
        self.assertEqual(len(samples.BrushSamples(.1,2).feed([point(0),point(.2)])[0]),5)
        self.assertEqual(len(samples.BrushSamples(.1,1,True).feed([point(0,.5),point(.2,.5)])[0]),5)

    def test_zero_pressure_is_not_replaced_and_expansion_is_bounded(self):
        sampler=samples.BrushSamples(.1,1)
        daubs,tail=sampler.feed([point(0,0),point(.2,0)])
        self.assertEqual(daubs,[]);self.assertIsNone(tail)
        daubs,tail=sampler.feed([point(.2,.7)])
        self.assertEqual(len(daubs),1);self.assertEqual(daubs[0]['pressure'],.7)
        with self.assertRaises(OverflowError):samples.BrushSamples(.00001,1).feed([point(0),point(1)],limit=10)

if __name__=='__main__':unittest.main()
