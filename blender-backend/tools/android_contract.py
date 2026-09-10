#!/usr/bin/env python3
"""Check CAD wire fixtures against Python registry declarations and Android wires.

Static contract check only; geometry/transaction tests run in Blender test_cad.py.
"""
import ast
import json
from pathlib import Path

root=Path(__file__).resolve().parents[2]
backend=root/'blender-backend'
fixture=json.loads((backend/'tests/fixtures/cad_v1.json').read_text())
protocol={}
exec(compile((backend/'blender_tablet_remote/protocol.py').read_text(),'protocol.py','exec'),protocol)
assert 'CAD' in protocol['ENUMS']['mode']
for key,value in fixture['capability'].items():
    assert protocol['FEATURES']['cad'][key]==value,key
commands=set()
for path in (backend/'blender_tablet_remote/commands').glob('*.py'):
    for node in ast.walk(ast.parse(path.read_text())):
        if isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef)):
            for decorator in node.decorator_list:
                if isinstance(decorator,ast.Call) and isinstance(decorator.func,ast.Name) and decorator.func.id=='command':
                    commands.add(ast.literal_eval(decorator.args[0]))
for item in fixture['commands']:
    assert item['command'] in commands,item['command']
android='\n'.join(p.read_text() for p in (root/'android-client/app/src/main/java').rglob('*.kt'))
for item in fixture['commands']:
    if item['command'].startswith('cad.'):
        assert '"'+item['command']+'"' in android, 'Android missing '+item['command']
for key in ('active_sketch_id','can_confirm','profile_id'):
    assert '"'+key+'"' in android,key
print(f'CAD v1: capability, {len(fixture["commands"])} commands and state fixture match backend + Android.')
