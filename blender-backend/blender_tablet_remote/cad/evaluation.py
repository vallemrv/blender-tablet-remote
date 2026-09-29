"""CAD evaluation on plain snapshots; run by the auxiliary Blender main thread."""
from . import document as model
from .kernel import kernel, ExtrusionPreviewCache, finish_edges, loft, helix
from ..errors import CommandError
from . import mirror


def geometry_key(doc, limit, scale):
    """Unused sketches, names and revisions do not invalidate a displayed solid."""
    features = []
    sketches = {}
    for node in model.history(doc):
        if node['kind'] == 'FEATURE' and node['enabled']:
            feature = dict(node)
            feature.pop('name', None)
            features.append(feature)
            for key in ('profile_id', 'to_profile_id'):
                if node.get(key):
                    sketch, _ = model.profile(doc, node[key])
                    sketches[sketch['id']] = dict(frame=model.frame(sketch), entities=sketch['entities'])
        if node['id'] == limit:
            break
    return model.dumps(dict(id=doc['id'], features=features, sketches=sketches, scale=scale))


class Evaluator:
    def __init__(self):
        self._extrusion_cache = ExtrusionPreviewCache()
        self._solids = {}
        self._body_meshes = {}

    def evaluate(self, doc, *, limit=None, scale=1.):
        import hashlib
        model.resolve_supports(doc)
        sequence = model.history(doc)
        if limit:
            end=next((i for i,node in enumerate(sequence) if node['id']==limit),None)
            if end is not None: sequence=sequence[:end+1]
        extrusion_cache=self._extrusion_cache
        tips={}; solids={}; keys={}
        for feature in sequence:
            if feature['kind']!='FEATURE' or not mirror.active(doc,feature): continue
            identifier=feature['id']; body=feature['body_id']
            previous=tips.get(body)
            if feature['type'] in model.FINISHES:
                if previous is None:
                    raise CommandError('El cuerpo no tiene un sólido que redondear',code='cad_dependency')
                signature=(doc['id'],feature['type'],feature['width'],feature.get('segments',1),
                           model.dumps(feature['edges']),keys.get(previous))
                cached=self._solids.get(identifier)
                if cached is None or cached[0]!=model.dumps(signature):
                    cached=(model.dumps(signature),finish_edges(solids[previous],feature['edges'],feature['width'],feature.get('segments',1)))
                    self._solids[identifier]=cached
                solids[identifier]=cached[1]
                keys[identifier]=hashlib.blake2b(repr(signature).encode(),digest_size=16).hexdigest()
                tips[body]=identifier
                continue
            if feature['type']=='HELIX':
                sketch,source=model.profile(doc,feature['profile_id'])
                signature=(doc['id'],'HELIX',feature['profile_id'],feature['axis'],feature['pitch'],feature['turns'],feature['hand'],
                           model.dumps(dict(frame=model.frame(sketch),entities=sketch['entities'])),keys.get(previous))
                cached=self._solids.get(identifier)
                if cached is None or cached[0]!=model.dumps(signature):
                    operand=helix(sketch,source,feature['axis'],feature['pitch'],feature['turns'],feature['hand'])
                    if previous: operand=kernel.union(solids[previous],operand)
                    cached=(model.dumps(signature),operand)
                    self._solids[identifier]=cached
                solids[identifier]=cached[1]
                keys[identifier]=hashlib.blake2b(repr(signature).encode(),digest_size=16).hexdigest()
                tips[body]=identifier
                continue
            if feature['type']=='LOFT':
                first,source=model.profile(doc,feature['profile_id']); second,target=model.profile(doc,feature['to_profile_id'])
                signature=(doc['id'],'LOFT',feature['profile_id'],feature['to_profile_id'],
                           model.dumps([dict(frame=model.frame(s),entities=s['entities']) for s in (first,second)]),keys.get(previous))
                cached=self._solids.get(identifier)
                if cached is None or cached[0]!=model.dumps(signature):
                    operand=loft(first,source,second,target)
                    if previous: operand=kernel.union(solids[previous],operand)
                    cached=(model.dumps(signature),operand)
                    self._solids[identifier]=cached
                solids[identifier]=cached[1]
                keys[identifier]=hashlib.blake2b(repr(signature).encode(),digest_size=16).hexdigest()
                tips[body]=identifier
                continue
            sketch,entity=model.profile(doc,feature['profile_id'])
            cut=feature.get('operation',feature['type'])=='CUT'
            depth=model.number(feature['depth'], positive=cut)
            extent=feature.get('extent','ONE')
            if extent not in ('ONE','BOTH'): extent='ONE'
            if cut and feature.get('target_id') not in solids:
                raise CommandError('Activa el sólido destino antes del vaciado',code='cad_dependency')
            signature=(doc['id'],feature['profile_id'],feature['type'],depth,extent,
                       model.dumps(dict(frame=model.frame(sketch),entities=sketch['entities'])),
                       keys.get(previous),feature.get('mirror'))
            cached=self._solids.get(identifier)
            if cached is None or cached[0]!=model.dumps(signature):
                operand=extrusion_cache.extrude(sketch,entity,depth,symmetric=True) if extent=='BOTH' else extrusion_cache.extrude(sketch,entity,-depth if cut else depth)
                if feature.get('mirror'): operand=mirror.solid(operand,feature['mirror'])
                if previous:
                    operand=kernel.cut(solids[previous],operand) if cut else kernel.union(solids[previous],operand)
                elif cut:
                    raise CommandError('El cuerpo no tiene un sólido para vaciar',code='cad_dependency')
                cached=(model.dumps(signature),operand)
                self._solids[identifier]=cached
            solids[identifier]=cached[1]
            keys[identifier]=hashlib.blake2b(repr(signature).encode(),digest_size=16).hexdigest()
            tips[body]=identifier
        # Form every display mesh before touching existing Blender objects.
        display={}
        for body,identifier in tips.items():
            signature=(keys[identifier],scale)
            cached=self._body_meshes.get(body)
            if cached is None or cached[0]!=model.dumps(signature):
                vertices,faces=solids[identifier]
                cached=(model.dumps(signature),([tuple(c/scale for c in v) for v in vertices],faces))
                self._body_meshes[body]=cached
            display[body]=cached
        feature_ids={f['id'] for f in doc['features']}
        self._solids={k:v for k,v in self._solids.items() if k in feature_ids}
        self._body_meshes={k:v for k,v in self._body_meshes.items() if k in tips}
        profile_ids={f['profile_id'].removeprefix('profile_') for f in doc['features'] if f.get('profile_id')}
        self._extrusion_cache.entries={k:v for k,v in self._extrusion_cache.entries.items() if k in profile_ids}
        return dict(display=display, tips=tips, solids=self._solids.copy(), profiles=self._extrusion_cache.entries.copy())


evaluator = Evaluator()


def calculate(request):
    operation = request['operation']
    if operation == 'evaluate':
        return evaluator.evaluate(request['doc'], limit=request.get('limit'), scale=request['scale'])
    if operation == 'solve':
        from .sketch import solve
        sketch = request['sketch']
        solve(sketch, request['goals'], drag=True)
        return sketch
    raise ValueError('Unknown CAD calculation')
