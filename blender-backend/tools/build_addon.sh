#!/usr/bin/env bash
# Empaqueta el add-on en un zip instalable y lo valida con Blender.
#
#   ./tools/build_addon.sh            -> dist/blender_tablet_remote-0.1.0.zip
#
# Instalación en Blender: Edit > Preferences > Add-ons > flecha ▾ > Install from Disk
set -euo pipefail

cd "$(dirname "$0")/.."
ROOT="$PWD"
PKG="blender_tablet_remote"
VERSION="$(grep -m1 '^version' "$PKG/blender_manifest.toml" | cut -d'"' -f2)"
OUT="$ROOT/dist/${PKG}-${VERSION}.zip"

mkdir -p "$ROOT/dist"
rm -f "$OUT"

# __pycache__ fuera: Blender rechaza extensiones con .pyc dentro.
find "$PKG" -name '__pycache__' -type d -exec rm -rf {} + 2>/dev/null || true
zip -r -q "$OUT" "$PKG" -x '*.pyc' -x '*__pycache__*'

echo "-> $OUT"

if command -v blender >/dev/null 2>&1; then
    blender --command extension validate "$OUT"
fi
