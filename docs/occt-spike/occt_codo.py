"""Reconstruye un documento CAD de Blender Tablet Remote con OpenCascade (build123d).

Uso: python occt_codo.py doc.json salida/ [tolerancia_booleana_mm]
Lee el JSON guardado en scene['btr_cad_document'] y evalúa EXTRUDE, SWEEP y FILLET
del historial en orden. Trabaja en milímetros (el documento guarda metros).
Ensayo descrito en docs/cad-kernel-evaluation.md; no forma parte del add-on.
"""
import json, math, sys, time
from pathlib import Path
from OCP.BRepTools import BRepTools
from build123d import (Axis, Edge, Face, GeomType, Location, Plane, Transition, Vector, Wire,
                       chamfer, export_step, export_stl, extrude, fillet, revolve, sweep)

MM = 1000.0
FUZZY = float(sys.argv[3]) if len(sys.argv) > 3 else None  # mm; absorbe ruido de captura




def fuse(a, b):
    return a.fuse(b, tol=FUZZY).clean() if FUZZY else a + b


doc = json.load(open(sys.argv[1]))
out = Path(sys.argv[2]); out.mkdir(exist_ok=True)
sketches = {s['id']: s for s in doc['sketches']}


def plane_of(sketch):
    f = sketch['frame']
    return Plane(origin=Vector(*f['origin']) * MM, x_dir=Vector(*f['x']), z_dir=Vector(*f['normal']))


def edges_of(sketch):
    """Entidades no constructivas → aristas exactas en mundo (mm)."""
    pl = plane_of(sketch); result = []
    for e in sketch['entities']:
        if e.get('construction'):
            continue
        t = e['type']
        if t == 'LINE':
            result.append((e, Edge.make_line(pl.from_local_coords((e['x']*MM, e['y']*MM)),
                                             pl.from_local_coords((e['x2']*MM, e['y2']*MM)))))
        elif t == 'CIRCLE':
            p = Plane(origin=pl.from_local_coords((e['x']*MM, e['y']*MM)), x_dir=pl.x_dir, z_dir=pl.z_dir)
            result.append((e, Edge.make_circle(e['diameter']/2*MM, p)))
        elif t == 'ARC':
            p = Plane(origin=pl.from_local_coords((e['x']*MM, e['y']*MM)), x_dir=pl.x_dir, z_dir=pl.z_dir)
            a0 = e['start']; a1 = a0 + e['sweep']
            result.append((e, Edge.make_circle(e['radius']*MM, p, start_angle=a0, end_angle=a1)))
        else:
            raise NotImplementedError(t)
    return result


def region(sketch, profile_id):
    """Contornos cerrados → caras con huecos por paridad de inclusión."""
    pairs = edges_of(sketch)
    wires = Wire.combine([e for _, e in pairs], tol=1e-4)
    faces = [Face(w) for w in wires if w.is_closed]
    if profile_id.startswith('profile_entity_'):
        entity = profile_id[len('profile_'):]
        target = next(Face(Wire([edge])) for e, edge in pairs if e['id'] == entity)
        faces = [target] + [f for f in faces if f.area < target.area - 1e-6 and inside(f, target)]
    def depth(f): return sum(1 for g in faces if g is not f and g.area > f.area and inside(f, g))
    solids = [f for f in faces if depth(f) % 2 == 0]
    holes = [f for f in faces if depth(f) % 2 == 1]
    result = []
    for s in solids:
        mine = [h for h in holes if inside(h, s) and depth(h) == depth(s) + 1]
        result.append(Face(s.outer_wire(), [h.outer_wire() for h in mine]))
    return result


def inside(small, big):
    return big.is_inside(small.outer_wire().center())


def path_wire(sketch):
    return Wire.combine([e for _, e in edges_of(sketch)], tol=1e-4)[0]


def exact_sweep(faces, path):
    """Barrido de líneas/arcos tangentes con superficies analíticas: cada línea extruye
    (cilindros/planos) y cada arco revoluciona (toros). El sweep genérico de OCCT deja
    superficies de revolución y aristas B-spline que luego no admiten redondeos."""
    section = list(faces); parts = []
    for edge in path.edges():
        a, b = edge.position_at(0), edge.position_at(1)
        if edge.geom_type == GeomType.LINE:
            parts.append(extrude(section, amount=(b - a).length, dir=(b - a).normalized()))
            section = [f.moved(Location(b - a)) for f in section]
        elif edge.geom_type == GeomType.CIRCLE:
            center = edge.arc_center; normal = (a - center).cross(edge.tangent_at(0)).normalized()
            angle = math.degrees(edge.length / edge.radius)
            axis = min((Axis(center, normal), Axis(center, -normal)),
                       key=lambda ax: (a.rotate(ax, angle) - b).length)
            parts.append(revolve(section, axis=axis, revolution_arc=angle))
            section = [f.rotate(axis, angle) for f in section]
        else:
            return sweep(faces, path=path, transition=Transition.RIGHT)
    result = parts[0]
    for part in parts[1:]:
        result = fuse(result, part)
    return result


def matches(edge, segments, tol=0.02):
    """Una arista OCCT coincide si el punto medio de algún segmento guardado cae sobre ella."""
    hits = 0
    for a, b in (seg for group in segments for seg in group):
        mid = (Vector(*a) + Vector(*b)) * (MM / 2)
        if edge.distance_to(mid) < tol:
            hits += 1
    return hits >= 2


log = []
tips = {}
t_total = time.perf_counter()
for feature in sorted(doc['features'], key=lambda f: f['order']):
    if not feature.get('enabled', True):
        continue
    t0 = time.perf_counter(); kind = feature['type']; base = tips.get(feature['body_id'])
    if kind == 'EXTRUDE':
        sk = sketches[feature['sketch_id']]
        prism = extrude(region(sk, feature['profile_id']), amount=feature['depth']*MM,
                        dir=plane_of(sk).z_dir)
        result = prism if base is None else fuse(base, prism)
    elif kind == 'SWEEP':
        sk = sketches[feature['sketch_id']]
        faces = region(sk, feature['profile_id'])
        body = exact_sweep(faces, path_wire(sketches[feature['path_sketch_id']]))
        result = body if base is None else fuse(base, body)
    elif kind == 'FILLET':
        chosen = [e for e in base.edges() if matches(e, feature['edges'])]
        result = fillet(chosen, radius=feature['width']*MM)
        kind += f' ({len(chosen)} aristas)'
    else:
        raise NotImplementedError(kind)
    tips[feature['body_id']] = result
    ms = (time.perf_counter() - t0) * 1000
    log.append(dict(feature=feature['name'], type=kind, ms=round(ms, 1), valid=result.is_valid,
                    volume_mm3=round(result.volume, 2), faces=len(result.faces()), edges=len(result.edges())))
    print(log[-1], flush=True)

solid = next(iter(tips.values()))
total = (time.perf_counter() - t_total) * 1000
print('TOTAL ms', round(total, 1))

# Acabados que el documento no contiene, para medir el kernel donde la malla falla.
stress = []


def attempt(name, op):
    t0 = time.perf_counter()
    try:
        r = op(); ok = r.is_valid; vol = round(r.volume, 2)
    except Exception as exc:
        r = None; ok = f"error: {type(exc).__name__}: {exc}"[:160]; vol = None
    stress.append(dict(prueba=name, ms=round((time.perf_counter()-t0)*1000, 1), valid=ok, volume_mm3=vol))
    print(stress[-1], flush=True)
    return r


def on_ring(e, x=50, cy=0, cz=90, r=22, tol=0.05):
    # El anillo de diseño llega partido en arcos y una B-spline del barrido: se elige por geometría.
    return all(abs(p.X-x) < tol and abs(math.hypot(p.Y-cy, p.Z-cz)-r) < tol
               for p in (e.position_at(t) for t in (0, .25, .5, .75, 1)))


junction = [e for e in solid.edges() if on_ring(e)]
attempt(f'Redondeo 3 mm en la unión tubo-brida lateral ({len(junction)} aristas)', lambda: fillet(junction, 3))
holes = [e for e in solid.edges() if e.geom_type == GeomType.CIRCLE and abs(e.radius-3.5) < 0.01]
attempt(f'Chaflán 0,4 mm en todos los taladros ({len(holes)} aristas)', lambda: chamfer(holes, 0.4))
outline = [e for e in solid.edges() if abs(e.center().X - 57) < 0.5]
attempt(f'Redondeo 1 mm del contorno exterior de la brida lateral ({len(outline)} aristas)', lambda: fillet(outline, 1))
attempt('Chaflán 0,5 mm en los taladros: choca con el redondeo de 2 mm (debe fallar)', lambda: chamfer(holes, 0.5))
attempt('Redondeo excesivo 10 mm en la unión lateral (debe fallar)', lambda: fillet(junction, 10))
both = attempt('Unión lateral 3 mm + taladros 0,4 mm encadenados', lambda: chamfer(
    [e for e in fillet(junction, 3).edges() if e.geom_type == GeomType.CIRCLE and abs(e.radius-3.5) < 0.01], 0.4))
t0 = time.perf_counter(); export_step(solid, out / 'codo.step'); step_ms = (time.perf_counter()-t0)*1000
tess = {}
for name, tol, ang in (('fino', 0.01, 0.1), ('recomendado', 0.02, 0.15), ('medio', 0.05, 0.3), ('grueso', 0.2, 0.5)):
    BRepTools.Clean_s(solid.wrapped)  # OCCT guarda la triangulación en la forma
    t0 = time.perf_counter()
    export_stl(solid, out / f'codo_{name}.stl', tolerance=tol, angular_tolerance=ang)
    tess[name] = dict(tolerance_mm=tol, angular=ang, ms=round((time.perf_counter()-t0)*1000, 1))
    print(name, tess[name])
if both is not None:
    BRepTools.Clean_s(both.wrapped); export_stl(both, out / 'codo_acabado.stl', tolerance=0.02, angular_tolerance=0.15)
json.dump(dict(features=log, stress=stress, total_ms=round(total, 1), step_ms=round(step_ms, 1),
               brep=dict(faces=len(solid.faces()), edges=len(solid.edges()), vertices=len(solid.vertices()),
                         valid=solid.is_valid, volume_mm3=solid.volume),
               tessellation=tess), open(out / 'resultado.json', 'w'), indent=1)
