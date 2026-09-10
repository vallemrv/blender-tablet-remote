# Tablet Material Recipe — versión 1

Especificación pública y reproducible de materiales para Blender Tablet Remote.
Codificación UTF-8, JSON RFC 8259. Identificador `format: "tablet-material"`,
`version: 1`. No requiere una IA: cualquier editor o generador puede producirlo.
El validador rechaza campos desconocidos, números no finitos y versiones incompatibles.

El [JSON Schema](material-recipe-v1.schema.json) describe la estructura. El compilador
canónico es `blender-backend/blender_tablet_remote/materials/recipes.py`. El orden de
las capas y la conversión de color descritos aquí forman parte del contrato.

## Documento

| Campo | Tipo y límites | Significado |
|---|---|---|
| `format` | `"tablet-material"` | Formato obligatorio |
| `version` | `1` | Versión obligatoria |
| `id` | `[a-z][a-z0-9_-]{0,47}` | Identificador obligatorio; los IDs incluidos están reservados |
| `label` | texto, 1–48 caracteres; se recortan espacios externos | Nombre visible obligatorio |
| `color` | `#RRGGBB`; por defecto `#B8B8B8` | Color base en sRGB |
| `surface` | objeto, opcional | Propiedades físicas de la superficie |
| `patterns` | lista, 0–8 elementos | Capas procedurales, en orden de abajo arriba |

Un documento ocupa como máximo 64 KiB. El compilador vuelve a validar antes de crear
nodos. Importar añade o actualiza un ID personalizado de la escena, sin modificar
materiales ya aplicados ni reemplazar los presets incluidos. Reimportar el mismo ID
actualiza su definición en el catálogo. El catálogo admite 64 IDs personalizados.

## Superficie

| Campo | Rango | Valor predeterminado | Entrada Principled BSDF |
|---|---|---|---|
| `roughness` | 0–1 | 0,4 | Roughness |
| `metallic` | 0–1 | 0 | Metallic |
| `transmission` | 0–1 | 0 | Transmission Weight |
| `ior` | 1–3 | 1,45 | IOR |
| `coat` | 0–1 | 0 | Coat Weight |

La salida BSDF conecta a Surface de Material Output. Color base y colores de capas
se convierten de sRGB a lineal por canal: `c/12.92` si `c ≤ 0.04045`; en otro caso
`((c+0.055)/1.055)^2.4`, donde `c` es el entero de ocho bits dividido entre 255.
Alfa es siempre 1; la transparencia física se expresa por transmisión.

## Patrones

Cada patrón es un objeto. No se permite ejecutar código ni nombrar nodos arbitrarios.
Todos parten de las coordenadas **Generated** del objeto, multiplicadas componente
a componente por `stretch`. No necesitan UV para el material completo.

| Campo | Valores/rango | Predeterminado |
|---|---|---|
| `kind` | `noise`, `wood`, `bands`, `cells` | Obligatorio |
| `scale` | 0,01–1000 | 5 |
| `stretch` | tres números, cada uno 0,01–100 | `[1,1,1]` |
| `detail` | 0–8 | 3 |
| `distortion` | 0–20 | 0 |
| `color` | `#RRGGBB` sRGB | `#303030` |
| `amount` | 0–1 | 0,5 |
| `bump` | 0–0,1 | 0 |

Traducción exacta:

- `noise`: Noise Texture 3D, Scale y Detail indicados; salida Fac.
- `wood`: Wave Texture con `wave_type=RINGS`; Scale, Detail y Distortion indicados;
  dirección de anillos X (predeterminado Blender); salida Fac.
- `bands`: Wave Texture con `wave_type=BANDS`; mismos parámetros; dirección X;
  salida Fac.
- `cells`: Voronoi Texture 3D, F1, distancia euclídea, Scale indicado; salida Distance.
  Detail y Distortion no intervienen en `cells`; Distortion no interviene en `noise`.

El factor de mezcla es la salida escalar multiplicada por `amount`. Un MixRGB de tipo
MIX mezcla el color anterior con `color` usando ese factor. El primer color anterior
es el color base; cada patrón posterior recibe la salida del anterior.

Si `bump > 0`, la salida escalar del patrón conecta a Height de un nodo Bump,
Distance=`bump`, Strength=1. La normal anterior conecta a Normal del siguiente Bump.
La última normal va a Principled Normal. Distance usa unidades nativas de Blender;
no desplaza vértices ni produce relieve geométrico. El último color mezclado va a
Principled Base Color. Las entradas no especificadas conservan los valores nativos
de Blender 4.4+; una versión de Blender diferente puede variar el aspecto ligeramente.
El archivo materializado guarda los nodos y valores concretos.

La elección «Pulido» de Android sustituye roughness por 0,12; «Gastado», por 0,8.
«Natural» usa la receta exacta. Elegir un color sustituye únicamente el color base,
conservando los colores secundarios definidos en sus patrones.

No se anuncian mapas descargables, nodos OSL, redes arbitrarias, desplazamiento real,
BRDF personalizados ni compatibilidad completa con MaterialX. El subconjunto está
pensado para generar materiales procedurales útiles y con coste limitado.

## Ejemplo

```json
{
  "format": "tablet-material",
  "version": 1,
  "id": "copper-aged",
  "label": "Cobre envejecido",
  "color": "#B87746",
  "surface": {"metallic": 0.85, "roughness": 0.5},
  "patterns": [
    {"kind": "noise", "scale": 6, "detail": 5,
     "color": "#46796B", "amount": 0.8, "bump": 0.003},
    {"kind": "noise", "scale": 120, "detail": 2,
     "color": "#47392D", "amount": 0.18, "bump": 0.0005}
  ]
}
```

Archivo listo para importar: [copper-aged.json](material-examples/copper-aged.json).
Otro ejemplo: [blue-marble.json](material-examples/blue-marble.json).

## Instrucción para una IA

> Genera únicamente un documento JSON Tablet Material Recipe versión 1 conforme a
> `material-recipe-v1.schema.json` y a la semántica de `material-recipe-v1.md`.
> Material deseado: [descripción]. Usa un ID propio y un nombre cotidiano en español.
> No incluyas código, campos ajenos al esquema ni más de ocho patrones. Usa colores
> sRGB hexadecimales. Ajusta roughness/metallic/transmission y combina noise/wood/bands/cells
> para la apariencia solicitada. Devuelve un archivo `.json` importable.

## Transporte

WebSocket JSON v2 sobre el mismo canal de control. Los comandos se registran y
validan en el hilo principal de Blender. Ejemplos sin token (la autenticación del
servidor se mantiene sin cambios):

```json
{"id":"1","type":"command","command":"mode.set","payload":{"mode":"MATERIAL"}}
{"id":"2","type":"command","command":"material.catalog","payload":{}}
{"id":"3","type":"command","command":"material.import","payload":{"recipe":{"format":"tablet-material","version":1,"id":"my-plastic","label":"Plástico azul","color":"#3080D0"}}}
{"id":"4","type":"command","command":"material.settings","payload":{"preset":"my-plastic","finish":"natural","environment":"studio"}}
{"id":"5","type":"command","command":"material.apply","payload":{}}
```

`material.catalog` devuelve las recetas completas normalizadas, por lo que un cliente
puede exportarlas sin ingeniería inversa. `material.import` devuelve el nuevo estado
para actualizar el catálogo Android. Las respuestas siguen `{type,response,id,ok,result}`
del contrato v2; los errores llevan `code` y `error`. Ver el
[protocolo de comandos](../blender-backend/docs/protocol.md).

Referencias del motor: [Principled BSDF](https://docs.blender.org/manual/en/latest/render/shader_nodes/shader/principled.html),
[View3DShading](https://docs.blender.org/api/current/bpy.types.View3DShading.html).
