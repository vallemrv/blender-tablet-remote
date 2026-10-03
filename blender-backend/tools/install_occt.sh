#!/usr/bin/env bash
# Instala OpenCascade (OCP) para el Python de Blender en un directorio privado.
# El add-on lo carga desde ahí en su proceso CAD auxiliar; no toca el Python de Blender.
# Uso: bash install_occt.sh [blender] [destino]
set -euo pipefail
BLENDER=${1:-blender}
TARGET=${2:-$HOME/.local/share/blender-tablet-remote/occt}
PY=$("$BLENDER" -b --factory-startup --python-expr \
  "import sys; print('BTRPY', f'{sys.version_info.major}.{sys.version_info.minor}')" 2>/dev/null | sed -n 's/^BTRPY //p')
[ -n "$PY" ] || { echo "No se pudo leer la versión de Python de $BLENDER" >&2; exit 1; }
command -v uv >/dev/null || { echo "Hace falta uv (https://docs.astral.sh/uv/)" >&2; exit 1; }
mkdir -p "$TARGET"
uv pip install --target "$TARGET" --python-version "$PY" --python-platform x86_64-manylinux_2_28 \
  --only-binary :all: "cadquery-ocp-novtk==8.0.1.0.0"
"$BLENDER" -b --factory-startup --python-expr \
  "import sys; sys.path.append('$TARGET'); from OCP.BRepAlgoAPI import BRepAlgoAPI_Fuse; print('BTROK')" 2>/dev/null | grep -q BTROK \
  && echo "OpenCascade listo en $TARGET (Python $PY)" || { echo "OCP no carga en Blender" >&2; exit 1; }
