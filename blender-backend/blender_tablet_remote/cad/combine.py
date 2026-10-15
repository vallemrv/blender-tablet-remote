"""Body boolean dependencies and captured relative placement, in document metres."""
from . import document as model
from ..errors import BadPayload,CommandError

FIELDS=('tool_body_id','operation','clearance','keep_tool','tool_transform')


def validate(doc, feature):
    body=feature['body_id'];tool=feature.get('tool_body_id')
    model.find(doc,'bodies',body);model.find(doc,'bodies',tool)
    if body==tool:raise BadPayload('Elige otro cuerpo como herramienta')
    if feature.get('operation') not in ('CUT','UNION','INTERSECT'):raise BadPayload('Restar, unir o intersecar')
    feature['clearance']=model.number(feature.get('clearance',0))
    if feature['clearance']<0:raise BadPayload('La holgura no puede ser negativa')
    if feature['operation']!='CUT':feature['clearance']=0.
    if not isinstance(feature.get('keep_tool',True),bool):raise BadPayload('Mantener herramienta debe ser booleano')
    matrix=feature.get('tool_transform')
    if matrix is not None:
        if not isinstance(matrix,list) or len(matrix)!=4 or any(not isinstance(row,list) or len(row)!=4 for row in matrix):raise BadPayload('Transformación de cuerpo inválida')
        for row in matrix:
            for v in row:model.number(v)
        if matrix[3]!=[0,0,0,1]:raise BadPayload('Transformación de cuerpo inválida')
        a,b,c=matrix[:3]
        determinant=a[0]*(b[1]*c[2]-b[2]*c[1])-a[1]*(b[0]*c[2]-b[2]*c[0])+a[2]*(b[0]*c[1]-b[1]*c[0])
        if abs(determinant)<1e-12:raise BadPayload('La herramienta tiene una escala nula')
    graph={b['id']:set() for b in doc['bodies']}
    features=[f for f in doc['features'] if f.get('id')!=feature.get('id')]+[feature]
    for f in features:
        if f['type']=='COMBINE':graph[f['body_id']].add(f['tool_body_id'])
    for b in doc['bodies']:
        if b.get('source'):
            source=model.find(doc,'features',b['source']['feature_id']);graph[b['id']].add(source['body_id'])
    visiting=set();done=set()
    def visit(key):
        if key in visiting:raise CommandError('La combinación crearía un ciclo entre cuerpos',code='cad_dependency')
        if key in done:return
        visiting.add(key)
        for parent in graph[key]:visit(parent)
        visiting.remove(key);done.add(key)
    for key in graph:visit(key)
    return feature
