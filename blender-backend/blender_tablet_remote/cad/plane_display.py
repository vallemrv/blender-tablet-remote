"""Geometría visual de planos CAD, compartida por vídeo, encuadre y picking."""
from mathutils import Vector
from ..camera import camera


def plane_gizmo(session, rv3d=None):
    """Sheet and drag handles of the plane being placed, in Blender units.

    `X`/`Y` follow the real in-plane shift directions (they stay true under tilt)
    and `N` the normal along which Separación moves. Shared by the capture and
    by the pen hit-test, so what is drawn is exactly what can be grabbed.
    """
    from ..cad.runtime import runtime
    import bpy
    from ..commands.units import current_scale
    frame=session['plane_frame']
    scale=max(float(bpy.context.scene.unit_settings.scale_length),1e-12)
    origin=Vector(frame['origin'])/scale; x=Vector(frame['x']); y=Vector(frame['y']); n=Vector(frame['normal'])
    corners=[c for o in runtime.objects(runtime.doc()) if o.visible_get() for c in (o.matrix_world@Vector(b) for b in o.bound_box)]
    preset_half=current_scale()['primitive_size']*.5/scale
    if corners:
        half=max(max((c-origin).dot(x) for c in corners)-min((c-origin).dot(x) for c in corners),
                 max((c-origin).dot(y) for c in corners)-min((c-origin).dot(y) for c in corners))*.5
        center=origin+x*sum((c-origin).dot(x) for c in corners)/len(corners)+y*sum((c-origin).dot(y) for c in corners)/len(corners)
    else:
        half=preset_half; center=origin
    half=max(half*1.2,preset_half)
    if rv3d is not None:
        # Keep a useful screen footprint even when the scene is much larger than
        # its preset. Perspective uses the plane's depth, not the orbit pivot's.
        projection=camera.projection_matrix(rv3d)
        span_x,span_y=camera.screen_span(projection)
        if camera.perspective=='PERSP':
            depth=-(camera.view_matrix()@center).z
            ratio=max(depth,0.)/max(camera.distance,1e-12)
            span_x*=ratio; span_y*=ratio
        half=max(half,min(span_x,span_y)*.15)
    quad=[center+x*a*half+y*b*half for a,b in ((-1,-1),(1,-1),(1,1),(-1,1))]
    shift=session.get('shift_axes') or (list(frame['x']),list(frame['y']))
    length=half*.45
    handles={'X':(Vector(shift[0]).normalized(),length,y),'Y':(Vector(shift[1]).normalized(),length,x),'N':(n,length*.8,x)}
    return dict(origin=origin,quad=quad,handles={k:(origin,origin+d*l,d,side) for k,(d,l,side) in handles.items()})

