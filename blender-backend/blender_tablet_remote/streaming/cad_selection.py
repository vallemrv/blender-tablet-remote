"""Solid selection reuses world-space GPU batches with the capture camera."""
import gpu
from gpu_extras.batch import batch_for_shader
from mathutils import Matrix, Vector
from ..camera import camera


def draw_cad_selection(rv3d, width, height):
    from ..cad.runtime import runtime
    if not runtime.workspace: return
    surface=runtime.surface
    surface.validate()
    if not surface.items:
        surface.draw_cache=None
        return
    # Items are immutable snapshots. Validation removes them if geometry changes.
    # Keep references in the cache so Python cannot recycle an old item's id.
    items=tuple(surface.items)
    cache=surface.draw_cache
    if cache is None or len(cache['items'])!=len(items) or any(a is not b for a,b in zip(cache['items'],items)):
        fill=gpu.shader.from_builtin('UNIFORM_COLOR')
        line=gpu.shader.from_builtin('POLYLINE_UNIFORM_COLOR')
        batches=[]
        for selected in items:
            item=selected.get('display',selected)
            triangles=[p for tri in item['triangles'] for p in tri]
            segments=[p for edge in item['segments'] for p in edge]
            batches.append((batch_for_shader(fill,'TRIS',{'pos':triangles}) if triangles else None,
                            batch_for_shader(line,'LINES',{'pos':segments}) if segments else None))
        cache=dict(items=items,fill=fill,line=line,batches=batches)
        surface.draw_cache=cache
    fill,line=cache['fill'],cache['line']
    projection=camera.perspective_matrix(rv3d).copy()
    # Same depth bias as the old NDC overlay, applied once to the GPU matrix.
    for i in range(4): projection[2][i]-=1e-5*projection[3][i]
    saved=(gpu.state.blend_get(),gpu.state.depth_test_get(),gpu.state.depth_mask_get(),gpu.state.viewport_get())
    try:
        gpu.state.viewport_set(0,0,width,height)
        gpu.state.blend_set('ALPHA'); gpu.state.depth_mask_set(False); gpu.state.depth_test_set('LESS_EQUAL')
        with gpu.matrix.push_pop(),gpu.matrix.push_pop_projection():
            gpu.matrix.load_identity(); gpu.matrix.load_projection_matrix(projection)
            for index,(item,(triangles,segments)) in enumerate(zip(items,cache['batches'])):
                color=(.2,.85,1.) if index==0 else (1.,.65,.15)
                if triangles:
                    fill.bind(); fill.uniform_float('color',(*color,.25)); triangles.draw(fill)
                if item['kind']=='VERTEX':
                    p=projection@Vector((*item.get('display',item)['points'][0],1.))
                    if p.w<=1e-9: continue
                    x,y,z=p.x/p.w,p.y/p.w,p.z/p.w; dx=8/width; dy=8/height
                    segments=batch_for_shader(line,'LINES',{'pos':[(x-dx,y,z),(x+dx,y,z),(x,y-dy,z),(x,y+dy,z)]})
                    gpu.matrix.load_projection_matrix(Matrix.Identity(4))
                if segments:
                    line.bind(); line.uniform_float('viewportSize',(width,height))
                    for size,c in ((5.,(.01,.02,.03,1.)),(2.5,(*color,1.))):
                        line.uniform_float('lineWidth',size); line.uniform_float('color',c); segments.draw(line)
                gpu.matrix.load_projection_matrix(projection)
    finally:
        gpu.state.blend_set(saved[0]); gpu.state.depth_test_set(saved[1]); gpu.state.depth_mask_set(saved[2]); gpu.state.viewport_set(*saved[3])


_cut_batches = {}


def draw_cad_cut(rv3d, width, height):
    """Translucent removed volume of the active cut, visible through the solid."""
    from ..cad.runtime import runtime
    ghost=runtime.cut_ghost()
    if not ghost or not ghost['triangles']:
        _cut_batches.clear()
        return
    fill=gpu.shader.from_builtin('UNIFORM_COLOR')
    line=gpu.shader.from_builtin('POLYLINE_UNIFORM_COLOR')
    if _cut_batches.get('ghost') is not ghost:
        _cut_batches.clear()
        _cut_batches.update(ghost=ghost, fill=batch_for_shader(fill,'TRIS',{'pos':ghost['triangles']}),
                            line=batch_for_shader(line,'LINES',{'pos':ghost['segments']}) if ghost['segments'] else None)
    saved=(gpu.state.blend_get(),gpu.state.depth_test_get(),gpu.state.depth_mask_get(),gpu.state.viewport_get())
    try:
        gpu.state.viewport_set(0,0,width,height)
        gpu.state.blend_set('ALPHA'); gpu.state.depth_mask_set(False); gpu.state.depth_test_set('NONE')
        with gpu.matrix.push_pop(),gpu.matrix.push_pop_projection():
            gpu.matrix.load_identity(); gpu.matrix.load_projection_matrix(camera.perspective_matrix(rv3d))
            fill.bind(); fill.uniform_float('color',(1.,.35,.2,.22)); _cut_batches['fill'].draw(fill)
            if _cut_batches['line']:
                line.bind(); line.uniform_float('viewportSize',(width,height))
                line.uniform_float('lineWidth',2.); line.uniform_float('color',(1.,.45,.3,.9)); _cut_batches['line'].draw(line)
    finally:
        gpu.state.blend_set(saved[0]); gpu.state.depth_test_set(saved[1]); gpu.state.depth_mask_set(saved[2]); gpu.state.viewport_set(*saved[3])
