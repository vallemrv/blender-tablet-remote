"""Selección y baselines de puntos/tiradores de curvas nativas en Edit."""
import bpy
from mathutils import Vector
from ..camera import camera
from ..errors import CommandError


def controls(obj):
    for si, spline in enumerate(obj.data.splines):
        if spline.type == 'BEZIER':
            for pi, point in enumerate(spline.bezier_points):
                if point.hide: continue
                for part, co, selected in (('POINT', point.co, point.select_control_point),
                                           ('LEFT', point.handle_left, point.select_left_handle),
                                           ('RIGHT', point.handle_right, point.select_right_handle)):
                    yield (si, pi, part), co.copy(), bool(selected)
        else:
            for pi, point in enumerate(spline.points):
                if not point.hide: yield (si, pi, 'POINT'), Vector(point.co[:3]), bool(point.select)


def selected(obj):
    return {key for key, _, on in controls(obj) if on}


def set_selection(obj, keys):
    for si, spline in enumerate(obj.data.splines):
        if spline.type == 'BEZIER':
            for pi, p in enumerate(spline.bezier_points):
                p.select_control_point = (si, pi, 'POINT') in keys and not p.hide
                p.select_left_handle = (si, pi, 'LEFT') in keys and not p.hide
                p.select_right_handle = (si, pi, 'RIGHT') in keys and not p.hide
        else:
            for pi, p in enumerate(spline.points): p.select = (si, pi, 'POINT') in keys and not p.hide
    obj.data.update_tag(); bpy.context.view_layer.update()


def pick(obj, u, v, mode, threshold, rv3d, region, viewport):
    from .snap import _visible
    aspect = max(1, region.width) / max(1, region.height)
    depsgraph = bpy.context.evaluated_depsgraph_get()
    candidates = []
    for key, local, _ in controls(obj):
        position = obj.matrix_world @ local
        screen = camera.project(position, rv3d)
        if screen is None: continue
        clip=camera.perspective_matrix(rv3d)@Vector((*position,1.))
        if not -clip.w<=clip.z<=clip.w:continue
        if key[2]!='POINT' and viewport is not None:
            display=getattr(viewport.overlay,'display_handle','ALL')
            if display=='NONE':continue
            if display=='SELECTED':
                p=obj.data.splines[key[0]].bezier_points[key[1]]
                if not (p.select_control_point or p.select_left_handle or p.select_right_handle):continue
        distance = Vector((screen[0]-u, (screen[1]-v)/aspect)).length
        if distance <= threshold: candidates.append((distance, key, position, screen))
    for _, key, position, screen in sorted(candidates, key=lambda c:c[0]):
        if not obj.show_in_front and not _visible(position,screen,depsgraph,rv3d,{obj.name},viewport): continue
        result = dict(hit=True, object=obj.name, element='curve', control=list(key), location=list(position))
        if mode != 'PROBE':
            current = selected(obj)
            target = {key}
            desired = target if mode == 'SET' else current | target if mode == 'ADD' else current-target if mode == 'REMOVE' else current^target
            set_selection(obj, desired)
        return result
    if mode in {'SET','TOGGLE'}: set_selection(obj,set())
    return dict(hit=False)


def topology(obj):
    return tuple((s.type,len(s.bezier_points),len(s.points)) for s in obj.data.splines)


class Snapshot:
    def __init__(self, obj):
        self.obj = obj
        self.mesh = obj.data
        self.topology = topology(obj)
        self.selection = selected(obj)
        if not self.selection: raise CommandError('Selecciona puntos o tiradores de la curva',code='empty_selection')
        self.world = obj.matrix_world.copy(); self.inverse = self.world.inverted_safe()
        self.coordinates = {key:co for key,co,_ in controls(obj)}
        self.points = [self.world@co for key,co,_ in controls(obj) if key in self.selection and
                       (key[2]=='POINT' or (key[0],key[1],'POINT') not in self.selection)]
        self.baseline = []
        for spline in obj.data.splines:
            if spline.type=='BEZIER':
                self.baseline.append([(p.co.copy(),p.handle_left.copy(),p.handle_right.copy(),p.handle_left_type,p.handle_right_type)
                                      for p in spline.bezier_points])
            else:self.baseline.append([p.co.copy() for p in spline.points])

    def valid(self):
        try:return self.obj.name in bpy.data.objects and self.obj.mode=='EDIT' and self.obj.data==self.mesh and topology(self.obj)==self.topology and selected(self.obj)==self.selection
        except ReferenceError:return False

    def restore(self):
        if self.obj.mode!='EDIT' or self.obj.data!=self.mesh or topology(self.obj)!=self.topology:return
        for spline, baseline in zip(self.obj.data.splines,self.baseline):
            if spline.type=='BEZIER':
                for p,old in zip(spline.bezier_points,baseline):
                    p.handle_left_type,p.handle_right_type=old[3],old[4]
                    p.co,p.handle_left,p.handle_right=old[:3]
            else:
                for p,old in zip(spline.points,baseline):p.co=old
        self.obj.data.update_tag();bpy.context.view_layer.update()

    def apply(self, transform):
        self.restore()
        for si,spline in enumerate(self.obj.data.splines):
            if spline.type=='BEZIER':
                for pi,p in enumerate(spline.bezier_points):
                    key=(si,pi,'POINT');old=self.baseline[si][pi]
                    if key in self.selection:
                        p.co=self.inverse@transform(self.world@old[0])
                        p.handle_left=self.inverse@transform(self.world@old[1])
                        p.handle_right=self.inverse@transform(self.world@old[2])
                    else:
                        for part,attr,index in (('LEFT','handle_left',1),('RIGHT','handle_right',2)):
                            if (si,pi,part) not in self.selection:continue
                            value=self.inverse@transform(self.world@old[index])
                            if (value-old[index]).length_squared<1e-20:continue
                            setattr(p,attr+'_type','FREE')
                            setattr(p,attr,value)
            else:
                for pi,p in enumerate(spline.points):
                    if (si,pi,'POINT') in self.selection:
                        old=self.baseline[si][pi]
                        co=self.inverse@transform(self.world@Vector(old[:3]))
                        p.co=(*co,old.w)
        self.obj.data.update_tag();bpy.context.view_layer.update()

    def changed(self):
        return any((co-self.coordinates[key]).length_squared>1e-20 for key,co,_ in controls(self.obj) if key in self.coordinates)


def execute(action, **kwargs):
    from ..bpy_utils import view3d_override, undo_push
    op = getattr(bpy.ops.curve, action)
    with view3d_override():
        result = op('EXEC_DEFAULT', False, **kwargs)
    if 'FINISHED' not in result:
        raise CommandError('La operación de curva no se pudo completar',code='curve_edit_failed')
    undo_push('Remote curve ' + action)
    from .. import state
    return state.snapshot(include_view=False)
