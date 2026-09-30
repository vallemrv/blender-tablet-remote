"""Sketch-space dimension annotations; placement never changes solved geometry."""
import math
from . import document as model, sketch as geometry

LABELS={'COINCIDENT':'●','POINT_ON_LINE':'P∈L','HORIZONTAL':'H','VERTICAL':'V','PARALLEL':'∥',
        'COLLINEAR':'Col','PERPENDICULAR':'⊥','TANGENT':'T','EQUAL':'=','EQUAL_ANGLE':'=∠',
        'FIX':'Fijo','MIDPOINT':'½','SYMMETRIC':'Sim','SYMMETRIC_LINE':'Sim⟋','OFFSET':'Grosor'}


def add(a,b): return (a[0]+b[0],a[1]+b[1])
def sub(a,b): return (a[0]-b[0],a[1]-b[1])
def mul(a,s): return (a[0]*s,a[1]*s)
def unit(a): return mul(a,1/max(math.hypot(*a),1e-15))
def midpoint(a,b): return mul(add(a,b),.5)
def dot(a,b): return a[0]*b[0]+a[1]*b[1]


def anchors(sketch, constraint):
    points=[]
    for ref in constraint['refs']:
        e=geometry.get_entity(sketch,ref)
        if ref.get('part') in geometry.handles(e): points.append(tuple(geometry.point(sketch,ref)))
        elif e['type']=='LINE' or (e['type'] in ('RECTANGLE','NGON') and ref.get('part','').startswith('EDGE')) or (e['type']=='SLOT' and ref.get('part')=='AXIS'):
            points.extend(tuple(p) for p in geometry.line(sketch,ref))
        elif e['type']=='RECTANGLE': points.extend(model.outline(e))
        else: points.append((e['x'],e['y']))
    return points


def spacing(sketch):
    points=[p for e in sketch['entities'] for p in geometry.handles(e).values()]
    if not points: return .001
    span=max(max(p[i] for p in points)-min(p[i] for p in points) for i in (0,1))
    return max(span*.07,1e-7)


def radius_anchor(entity, label):
    center=(entity['x'],entity['y'])
    if entity['type']=='SLOT':
        center=min(geometry.slot_centers(entity),key=lambda p:math.dist(p,label))
    direction=unit(sub(label,center))
    if direction==(0.,0.): direction=(1.,0.)
    if entity['type']=='ARC':
        start=math.radians(entity['start']); sweep=math.radians(entity['sweep'])
        angle=math.atan2(direction[1],direction[0])
        progress=((angle-start) if sweep>=0 else (start-angle))%math.tau
        if progress>abs(sweep):
            choices=[start,start+sweep]
            angle=min(choices,key=lambda a:abs(math.atan2(math.sin(a-angle),math.cos(a-angle))))
        direction=(math.cos(angle),math.sin(angle))
    elif entity['type']=='SLOT':
        axis=(math.cos(math.radians(entity['angle'])),math.sin(math.radians(entity['angle'])))
        outward=mul(axis,1 if dot(sub(center,(entity['x'],entity['y'])),axis)>=0 else -1)
        if dot(direction,outward)<0:
            normal=(-axis[1],axis[0]); direction=mul(normal,1 if dot(direction,normal)>=0 else -1)
    elif entity['type']=='NGON':
        directions=[(math.cos(math.radians(entity['angle'])+(i+.5)*math.tau/entity['sides']),
                     math.sin(math.radians(entity['angle'])+(i+.5)*math.tau/entity['sides'])) for i in range(entity['sides'])]
        direction=max(directions,key=lambda d:dot(d,direction))
    return center,direction


def layout(sketch, constraint, index=0, *, base_gap=None):
    """2D SI geometry: label centre, witness/dimension segments and arrow tips."""
    typ=constraint['type']; refs=constraint['refs']
    gap=(spacing(sketch) if base_gap is None else base_gap)*(1+(index%3)*.5)
    points=anchors(sketch,constraint)
    anchor=tuple(sum(p[i] for p in points)/max(1,len(points)) for i in (0,1))
    label=tuple(constraint.get('label_position',add(anchor,(gap,gap))))
    lines=[];arrows=[]
    if typ in ('DISTANCE','DISTANCE_X','DISTANCE_Y'):
        a,b=geometry.measure_line(sketch,refs[0]) if len(refs)==1 else [geometry.point(sketch,r) for r in refs]
        a,b=tuple(a),tuple(b);mid=midpoint(a,b)
        normal=unit((-(b[1]-a[1]),b[0]-a[0]))
        if normal==(0.,0.):normal=(0.,1.)
        default=add(mid,(0,gap) if typ=='DISTANCE_X' else (gap,0) if typ=='DISTANCE_Y' else mul(normal,gap))
        label=tuple(constraint.get('label_position',default))
        if typ=='DISTANCE_X':p,q=(a[0],label[1]),(b[0],label[1])
        elif typ=='DISTANCE_Y':p,q=(label[0],a[1]),(label[0],b[1])
        else:
            offset=mul(normal,dot(sub(label,mid),normal));p,q=add(a,offset),add(b,offset)
        lines=[(a,p),(b,q),(p,q)];arrows=[(p,q),(q,p)]
    elif typ=='RADIUS':
        e=geometry.get_entity(sketch,refs[0]);radius=geometry.radius(sketch,refs[0])
        angle=math.radians(e.get('start',0)+e.get('sweep',90)/2) if e['type']=='ARC' else math.pi/4
        center=(e['x'],e['y'])
        if e['type']=='SLOT':center=geometry.slot_centers(e)[1]
        default=add(center,mul((math.cos(angle),math.sin(angle)),radius+gap))
        label=tuple(constraint.get('label_position',default))
        center,direction=radius_anchor(e,label);rim=add(center,mul(direction,radius))
        lines=[(center,rim),(rim,label)];arrows=[(rim,center)]
    elif typ=='ANGLE' and len(refs)==2:
        vertex,ua,ub,degrees=geometry.line_angle(sketch,refs);vertex=tuple(vertex)
        start=math.atan2(ua[1],ua[0]);sweep=math.radians(degrees)
        if (ua[0]*ub[1]-ua[1]*ub[0])<0: sweep=-sweep
        reach=min(max(math.dist(vertex,tuple(p)) for p in geometry.line(sketch,r)) for r in refs)
        default=add(vertex,mul((math.cos(start+sweep/2),math.sin(start+sweep/2)),max(reach*.5,gap*2)))
        label=tuple(constraint.get('label_position',default));radius=max(math.dist(label,vertex),gap*.5)
        arc=[add(vertex,mul((math.cos(start+sweep*i/32),math.sin(start+sweep*i/32)),radius)) for i in range(33)]
        lines=list(zip(arc,arc[1:]));arrows=[(arc[0],arc[1]),(arc[-1],arc[-2])]
        # Witness lines extend each segment to the arc when it ends short of it.
        for direction,r in ((ua,refs[0]),(ub,refs[1])):
            end=max((tuple(p) for p in geometry.line(sketch,r)),key=lambda p:math.dist(p,vertex))
            if math.dist(end,vertex)<radius: lines.append((end,add(vertex,mul(tuple(direction),radius))))
    elif typ=='ANGLE' and len(refs)==1:
        e=geometry.get_entity(sketch,refs[0]);center=(e['x'],e['y'])
        start=math.radians(e['start']);sweep=math.radians(e['sweep'])
        default=add(center,mul((math.cos(start+sweep/2),math.sin(start+sweep/2)),e['radius']+gap))
        label=tuple(constraint.get('label_position',default));radius=max(math.dist(label,center),e['radius']*.2)
        arc=[add(center,mul((math.cos(start+sweep*i/32),math.sin(start+sweep*i/32)),radius)) for i in range(33)]
        ends=[add(center,mul((math.cos(a),math.sin(a)),e['radius'])) for a in (start,start+sweep)]
        lines=list(zip(arc,arc[1:]))+[(ends[0],arc[0]),(ends[1],arc[-1])];arrows=[(arc[0],arc[1]),(arc[-1],arc[-2])]
    elif typ=='OFFSET':
        source,target=[geometry.get_entity(sketch,r) for r in refs]
        def side(e):
            if e['type']=='RECTANGLE':return (e['x']+e['width'],e['y']+e['height']/2)
            if e['type']=='CIRCLE':return (e['x']+e['diameter']/2,e['y'])
            a=math.radians(e['angle']);return (e['x']-math.sin(a)*e['width']/2,e['y']+math.cos(a)*e['width']/2)
        a,b=side(source),side(target);label=tuple(constraint.get('label_position',add(b,(gap,gap))))
        lines=[(a,b),(b,label)];arrows=[(a,b),(b,a)]
    return dict(label=label,segments=lines,arrows=arrows)


def overlay(sketch, project, selection, unit_name, aspect):
    """Dimensions are the only interactive annotations: value, witness lines, arrows.

    Rules without a value (H, V, ⊥, =…) are small read-only marks shown only next
    to the selected geometry, so the drawing stays uncluttered.
    """
    from .dimensions import visible_constraints
    factor,suffix={'MILLIMETERS':(1000,'mm'),'CENTIMETERS':(100,'cm')}.get(unit_name,(1,'m'))
    result=[];gap=spacing(sketch)
    selected_ids={item['id'] for item in (selection or {}).get('items',[]) if item.get('kind','ENTITY')=='ENTITY'}
    def segments(items):
        projected=[(project(a),project(b)) for a,b in items]
        return [[a,b] for a,b in projected if a is not None and b is not None]
    marks={}
    for index,c in enumerate(visible_constraints(sketch)):
        if c.get('value') is None:
            if not selected_ids.intersection(r['id'] for r in c['refs']): continue
            points=anchors(sketch,c)
            anchor=tuple(sum(p[i] for p in points)/max(1,len(points)) for i in (0,1))
            label_point=project(anchor)
            if label_point is None: continue
            # Several marks on the same spot stack instead of overlapping.
            key=(round(label_point[0],2),round(label_point[1],2)); stack=marks.get(key,0); marks[key]=stack+1
            result.append(dict(id=c['id'],kind='CONSTRAINT',points=[],closed=False,selected=False,
                label=LABELS.get(c['type'],c['type']),label_point=label_point,label_offset=10+stack*13))
            continue
        drawing=layout(sketch,c,index,base_gap=gap);label_point=project(drawing['label'])
        if label_point is None:continue
        if c['type']=='ANGLE':label=format(c['value'],'.6g')+'°'
        else:label={'RADIUS':'R','DISTANCE_X':'↔ ','DISTANCE_Y':'↕ '}.get(c['type'],'')+format(c['value']*factor,'.6g')+' '+suffix
        # Touch target: larger than the drawn label so a fingertip hits it easily.
        half_height=.028;half_width=max(.035,len(label)*.008)/max(aspect,1e-6)
        u,v=label_point
        result.append(dict(id=c['id'],kind='DIMENSION',
            points=[],closed=False,selected=(selection or {}).get('kind')=='CONSTRAINT' and selection['id']==c['id'],
            label=label,label_point=label_point,label_offset=0,
            label_box=[u-half_width,v-half_height,u+half_width,v+half_height],
            dimension_lines=segments(drawing['segments']),arrows=segments(drawing['arrows'])))
    return sorted(result,key=lambda item:(item['kind']=='DIMENSION',item['selected']))
