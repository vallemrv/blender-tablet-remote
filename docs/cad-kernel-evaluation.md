# Evaluación del kernel CAD

Fecha de la comprobación: 7 de septiembre de 2026. Alcance: primer recorrido
recomendado en las secciones 37–38 del documento solicitado, conservado en
[PLAN_CAD_PARAMETRICO_BLENDER_TABLET_REMOTE.md](../PLAN_CAD_PARAMETRICO_BLENDER_TABLET_REMOTE.md).

## Decisión para esta entrega

Usar `CadKernel` como frontera y una implementación nativa de Blender para los
perfiles simples y su extrusión. El documento paramétrico persistente es la fuente;
la malla es un resultado sustituible. No implementar un BREP, booleanos generales o
un solver universal. No anunciar operaciones que esta implementación no resuelve.

OCP es viable en el equipo comprobado: el ensayo binario descrito abajo cargó y
calculó un sólido dentro del Python de Blender. La elección nativa responde al
alcance reducido y a la distribución: el ensayo ocupó 251 MiB descomprimidos para
un único ABI/plataforma y todavía no acredita la matriz Windows/macOS/Linux ni
Blender 4.2. No significa que empaquetar OCP sea imposible. Su adaptación queda
separada del protocolo y de los documentos para un ciclo con sólidos avanzados.

## Entorno observado

- Blender instalado: 5.2.1 LTS, compilación `9e2066aef7ef`.
- Python embebido: CPython 3.13.13, arquitectura Linux x86_64.
- Python del sistema: 3.14.7; no sirve como prueba del ABI de Blender.
- En Blender: NumPy disponible; OCP, CadQuery, build123d, FreeCAD y SciPy ausentes.
- El manifest del complemento declara Blender 4.2 como mínimo. Esa versión usa
  Python 3.11 según las [notas oficiales de Blender 4.2](https://www.blender.org/download/releases/4-2/).
  Compatibilidad declarada no equivale a una ejecución comprobada en 4.2.

## Comparación

| Alternativa | Dependencias y empaquetado observado | Geometría y distribución |
| --- | --- | --- |
| CadQuery 2.8.0 / OCP | Metadatos PyPI: Python >=3.11, `cadquery-ocp>=7.9.3.1,<8.0`, VTK y dependencias numéricas. CadQuery puro ocupa poco, el kernel no. | OCCT aporta BREP, booleanos, redondeos, chaflanes y transferencia CAD. El proyecto documenta instalación pip/conda y recomienda aislamiento. |
| build123d 0.11.1 | Python >=3.10,<3.15; usa `cadquery-ocp-novtk>=7.9,<8`, NumPy 2, SciPy y otras dependencias. Evita VTK en su dependencia principal. | Otra API sobre OCCT. No elimina el requisito ABI/plataforma del kernel; no es un solver de restricciones universal listo para integrar. |
| FreeCAD Python API | El módulo no está instalado en este Blender y el nombre `FreeCAD` no tiene distribución PyPI en la consulta. FreeCAD publica una pila de dependencias nativas y paquetes por plataforma. | Host CAD completo y motor paramétrico, con mayor integración que transportar un kernel. No se probó incrustar una instalación completa de FreeCAD. |
| Blender nativo limitado | Usa las dependencias que el complemento ya tiene. | Apto para la geometría limitada del primer recorrido. No ofrece sólidos BREP ni promete fillet/STEP o topología persistente de caras. |

Fuentes primarias: [instalación de CadQuery](https://cadquery.readthedocs.io/en/latest/installation.html),
[instalación de build123d](https://build123d.readthedocs.io/en/latest/installation.html),
[metadatos CadQuery 2.8.0](https://pypi.org/pypi/cadquery/2.8.0/json),
[metadatos build123d 0.11.1](https://pypi.org/pypi/build123d/0.11.1/json),
[dependencias FreeCAD](https://freecad.github.io/Website/es/dev/setup/dependencies/),
[introducción OCCT](https://dev.opencascade.org/doc/overview/html/index.html).

CadQuery, build123d y el wrapper OCP declaran Apache 2.0. OCCT publica LGPL 2.1 con
excepción adicional; FreeCAD incluye su licencia LGPL y avisos de componentes.
La distribución futura de binarios debe incluir las licencias y avisos concretos
de los paquetes seleccionados. Referencias: [OCP](https://github.com/CadQuery/OCP/blob/master/LICENSE),
[build123d](https://github.com/gumyr/build123d/blob/dev/LICENSE),
[OCCT](https://occt3d.com/dev/doc/overview/html/occt_public_license.html),
[FreeCAD](https://github.com/FreeCAD/FreeCAD/blob/main/LICENSE).

## Ensayo reproducible

El ensayo instaló exclusivamente en un directorio temporal. No alteró el Python de
Blender, la instalación del complemento ni la escena del usuario.

```bash
blender --background --factory-startup --python-expr \
  "import sys,platform,importlib.util; print(sys.version,platform.machine()); print({n:bool(importlib.util.find_spec(n)) for n in ['OCP','cadquery','build123d','FreeCAD','scipy','numpy']})"

python3 -m pip install --target /tmp/blender-cad-kernel-spike \
  --only-binary=:all: --python-version 3.13 --implementation cp --abi cp313 \
  --platform manylinux_2_31_x86_64 --platform manylinux_2_28_x86_64 \
  --no-compile 'cadquery-ocp-novtk==7.9.3.1.1'

blender --background --factory-startup --python-exit-code 1 --python-expr \
  "import sys; sys.path.insert(0,'/tmp/blender-cad-kernel-spike'); from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox; from OCP.BRepAlgoAPI import BRepAlgoAPI_Cut; from OCP.GProp import GProp_GProps; from OCP.BRepGProp import BRepGProp; a=BRepPrimAPI_MakeBox(80.,45.,20.).Shape(); b=BRepPrimAPI_MakeBox(6.,6.,20.).Shape(); cut=BRepAlgoAPI_Cut(a,b).Shape(); p=GProp_GProps(); BRepGProp.VolumeProperties_s(cut,p); print(p.Mass()); assert abs(p.Mass()-71280.)<1.e-6"
```

Resultado observado: `71280.0`, salida 0. Wheel CPython 3.13 Linux de OCP-novtk:
64,3 MiB comprimidos; instalación temporal total: 251 MiB. También se localizaron
wheels de OCP 8 para varias plataformas/ABIs, pero CadQuery 2.8 y build123d 0.11.1
requieren OCP anterior a 8: no deben mezclarse simplemente los últimos releases.

Este ensayo prueba importación y una diferencia de cajas en el host indicado.
No certifica fillets, calidad de mallado, rendimiento de documentos grandes,
la pila completa de CadQuery/build123d o su distribución multiplataforma.


## Extensión del 8 de septiembre de 2026

El workspace incorpora ahora arcos y perfiles simples de líneas/arcos, restricciones
numéricas acotadas con NumPy y vaciado por booleano exacto de Blender sobre mallas.
El redondeo de sketch recorta dos líneas y añade un arco analítico restringido.
Esta extensión conserva el kernel nativo y el documento como fuente. No integra
FreeCAD/OCP ni anuncia BREP, STEP, fillet de sólidos o Shell. La comparación binaria
anterior sigue siendo evidencia de aquella evaluación, no de una dependencia de
la entrega actual. El alcance vigente está en [cad-workspace.md](cad-workspace.md).
