"""Solid selection is drawn in the video, with the exact capture camera."""
import gpu
from gpu_extras.batch import batch_for_shader
from mathutils import Matrix, Vector
from ..camera import camera


def draw_cad_selection(rv3d, width, height):
    from ..cad.runtime import runtime
    if not runtime.workspace: return
    runtime.surface.validate()
    if not runtime.surface.items: return
    matrix=camera.perspective_matrix(rv3d)
    def clip(p):
        p=matrix@Vector((*p,1.))
        return (p.x/p.w,p.y/p.w,p.z/p.w-1e-5) if p.w>1e-9 else None
    fill=gpu.shader.from_builtin('UNIFORM_COLOR')
    line=gpu.shader.from_builtin('POLYLINE_UNIFORM_COLOR')
    saved=(gpu.state.blend_get(),gpu.state.depth_test_get(),gpu.state.depth_mask_get(),gpu.state.viewport_get())
    try:
        gpu.state.viewport_set(0,0,width,height)
        gpu.state.blend_set('ALPHA'); gpu.state.depth_mask_set(False); gpu.state.depth_test_set('LESS_EQUAL')
        with gpu.matrix.push_pop(),gpu.matrix.push_pop_projection():
            gpu.matrix.load_identity(); gpu.matrix.load_projection_matrix(Matrix.Identity(4))
            for index,item in enumerate(runtime.surface.items):
                color=(.2,.85,1.) if index==0 else (1.,.65,.15)
                triangles=[]
                for tri in item['triangles']:
                    points=[clip(p) for p in tri]
                    if all(p is not None for p in points): triangles.extend(points)
                if triangles:
                    fill.bind(); fill.uniform_float('color',(*color,.25))
                    batch_for_shader(fill,'TRIS',{'pos':triangles}).draw(fill)
                lines=[]
                for segment in item['segments']:
                    points=[clip(p) for p in segment]
                    if all(p is not None for p in points): lines.extend(points)
                if item['kind']=='VERTEX':
                    p=clip(item['points'][0])
                    if p:
                        x,y,z=p; dx=8/width; dy=8/height
                        lines=[(x-dx,y,z),(x+dx,y,z),(x,y-dy,z),(x,y+dy,z)]
                if lines:
                    line.bind(); line.uniform_float('viewportSize',(width,height))
                    for size,c in ((5.,(.01,.02,.03,1.)),(2.5,(*color,1.))):
                        line.uniform_float('lineWidth',size); line.uniform_float('color',c)
                        batch_for_shader(line,'LINES',{'pos':lines}).draw(line)
    finally:
        gpu.state.blend_set(saved[0]); gpu.state.depth_test_set(saved[1]); gpu.state.depth_mask_set(saved[2]); gpu.state.viewport_set(*saved[3])
