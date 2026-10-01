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
            # Every selected reference shares one colour: a multi-edge pick reads as one set.
            color=(.2,.85,1.)
            for item,(triangles,segments) in zip(items,cache['batches']):
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


def draw_cad_plane(rv3d, width, height):
    """Preview of the plane being placed: translucent sheet, border, axes and normal.

    The sheet covers the visible CAD result so its position against the part is
    readable; it is faint behind the solid and stronger in front of it.
    """
    from ..cad.runtime import runtime
    import bpy
    session=runtime.session
    if not (runtime.workspace and session and session['operation']=='PLANE' and session.get('plane_frame')):
        return
    frame=session['plane_frame']
    scale=max(float(bpy.context.scene.unit_settings.scale_length),1e-12)
    origin=Vector(frame['origin'])/scale; x=Vector(frame['x']); y=Vector(frame['y']); n=Vector(frame['normal'])
    corners=[c for o in runtime.objects(runtime.doc()) if o.visible_get() for c in (o.matrix_world@Vector(b) for b in o.bound_box)]
    if corners:
        half=max(max((c-origin).dot(x) for c in corners)-min((c-origin).dot(x) for c in corners),
                 max((c-origin).dot(y) for c in corners)-min((c-origin).dot(y) for c in corners))*.5
        center=origin+x*sum((c-origin).dot(x) for c in corners)/len(corners)+y*sum((c-origin).dot(y) for c in corners)/len(corners)
    else:
        half=.05/scale; center=origin
    half=max(half*1.2,.01/scale)
    quad=[center+x*a*half+y*b*half for a,b in ((-1,-1),(1,-1),(1,1),(-1,1))]
    fill=gpu.shader.from_builtin('UNIFORM_COLOR'); line=gpu.shader.from_builtin('POLYLINE_UNIFORM_COLOR')
    sheet=batch_for_shader(fill,'TRIS',{'pos':[quad[0],quad[1],quad[2],quad[0],quad[2],quad[3]]})
    border=batch_for_shader(line,'LINES',{'pos':[p for i in range(4) for p in (quad[i],quad[(i+1)%4])]})
    axis=half*.45
    axes=[(batch_for_shader(line,'LINES',{'pos':[origin,origin+x*axis]}),(1.,.33,.33,1.)),
          (batch_for_shader(line,'LINES',{'pos':[origin,origin+y*axis]}),(.55,.86,.24,1.)),
          (batch_for_shader(line,'LINES',{'pos':[origin,origin+n*axis*.8]}),(.3,.55,1.,1.))]
    saved=(gpu.state.blend_get(),gpu.state.depth_test_get(),gpu.state.depth_mask_get(),gpu.state.viewport_get())
    try:
        gpu.state.viewport_set(0,0,width,height)
        gpu.state.blend_set('ALPHA'); gpu.state.depth_mask_set(False)
        with gpu.matrix.push_pop(),gpu.matrix.push_pop_projection():
            gpu.matrix.load_identity(); gpu.matrix.load_projection_matrix(camera.perspective_matrix(rv3d))
            for test,alpha in (('NONE',.07),('LESS_EQUAL',.16)):
                gpu.state.depth_test_set(test)
                fill.bind(); fill.uniform_float('color',(.35,.62,1.,alpha)); sheet.draw(fill)
            gpu.state.depth_test_set('NONE')
            line.bind(); line.uniform_float('viewportSize',(width,height))
            line.uniform_float('lineWidth',2.); line.uniform_float('color',(.55,.78,1.,.95)); border.draw(line)
            line.uniform_float('lineWidth',3.)
            for batch,color in axes:
                line.uniform_float('color',color); batch.draw(line)
    finally:
        gpu.state.blend_set(saved[0]); gpu.state.depth_test_set(saved[1]); gpu.state.depth_mask_set(saved[2]); gpu.state.viewport_set(*saved[3])
