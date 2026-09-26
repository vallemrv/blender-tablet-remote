"""blender -b --factory-startup --python tools/benchmark_cad.py [-- --backend PATH].

Deterministic four-hole plate: counts and median evaluation/gesture milliseconds.
Use a second checkout with --backend to compare identical work on both versions.
The benchmark runs direct commands to measure geometry cost independently of IPC.
"""
import argparse
import json
from pathlib import Path
import statistics
import sys
import time

args = argparse.ArgumentParser()
args.add_argument('--backend', type=Path, default=Path(__file__).resolve().parents[1])
options = args.parse_args(sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else [])
sys.path[:0] = [str(options.backend), str(options.backend / 'tests')]
from test_cad import CadTests, OWNER, volume
from blender_tablet_remote.commands import cad, snap
from blender_tablet_remote.cad.runtime import runtime

case = CadTests()
case.setUp()
try:
    outer = case.draw('RECTANGLE', (0, 0), (.27, .15))
    for x, y in ((.04, .03), (.04, .12), (.23, .03), (.23, .12)):
        case.draw('CIRCLE', (x, y), (x+.01, y))
    start = time.perf_counter()
    case.extrude(outer, .02, confirm=False)
    first = (time.perf_counter()-start)*1000
    obj = case.obj()
    counts = dict(vertices=len(obj.data.vertices), faces=len(obj.data.polygons))
    depth_times, pen_times = [], []
    for i in range(12):
        start = time.perf_counter()
        cad.extrude_update(dict(depth=.025+i*.001, **OWNER))
        depth_times.append((time.perf_counter()-start)*1000)
    for i in range(12):
        start = time.perf_counter()
        cad.extrude_update(dict(gesture_u=0., gesture_v=-.04-i*.01, baseline_depth=.03, **OWNER))
        pen_times.append((time.perf_counter()-start)*1000)
    cad.confirm(OWNER)
    runtime.surface.graphs.clear()
    start = time.perf_counter()
    snap._cad_mesh(obj)
    selection_cold = (time.perf_counter()-start)*1000
    start = time.perf_counter()
    snap._cad_mesh(obj)
    selection_warm = (time.perf_counter()-start)*1000
    print('CAD_BENCHMARK '+json.dumps(dict(**counts, begin_ms=first,
          depth_median_ms=statistics.median(depth_times), pen_median_ms=statistics.median(pen_times),
          selection_cold_ms=selection_cold, selection_warm_ms=selection_warm,
          volume_m3=volume(obj))), flush=True)
finally:
    case.tearDown()
