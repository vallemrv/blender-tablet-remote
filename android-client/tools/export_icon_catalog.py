#!/usr/bin/env python3
"""Exporta los mismos trazados del APK a SVG y a una lámina sin dependencias web."""
from pathlib import Path
import html
import re
import zipfile

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "android-client/app/src/main/java/com/blendertablet/remote/ui/StudioIcons.kt"
OUT = ROOT / "dist/iconos"


def main():
    glyphs = re.findall(r'"([A-Z_]+)" to Glyph\("([^"]+)", "([^"]+)", "([^"]+)"\)', SOURCE.read_text())
    if len(glyphs) != SOURCE.read_text().count(' to Glyph('):
        raise ValueError("Algún dibujo no tiene el formato de exportación esperado")
    if len({key for key, *_ in glyphs}) != len(glyphs):
        raise ValueError("Hay identificadores repetidos")
    if len({path for *_, path in glyphs}) != len(glyphs):
        raise ValueError("Dos iconos distintos tienen el mismo dibujo")
    OUT.mkdir(parents=True, exist_ok=True)
    cards, board = [], []
    groups = list(dict.fromkeys(group for _, _, group, _ in glyphs))
    with zipfile.ZipFile(OUT / "blender-remote-iconos-svg.zip", "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("LEEME.txt", "Iconos originales de Blender Remote.\n"
                         "Fuente editable: ui/StudioIcons.kt. Generado por export_icon_catalog.py.\n"
                         "Cuadrícula 24 × 24; trazo 1.7; extremos y uniones redondos.\n"
                         "Sin descargas ni recursos gráficos de terceros.\n")
        for index, (key, label, group, path) in enumerate(glyphs):
            drawing = f'<path d="{path}" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"/>'
            svg = f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" role="img" aria-label="{html.escape(label)}">{drawing}</svg>'
            archive.writestr(f"svg/{key.lower()}.svg", svg)
            cards.append(f'<article data-group="{html.escape(group)}" data-search="{html.escape(label + " " + key)}">'
                         f'<div class="sample">{svg}</div><b>{html.escape(label)}</b><small>{key}</small></article>')
            x, y = (index % 10) * 144, (index // 10) * 108
            board.append(f'<g transform="translate({x},{y})"><rect x="4" y="4" width="136" height="100" rx="10" fill="#222833"/>'
                         f'<g transform="translate(54,15) scale(1.5)" color="#e7edf6">{drawing}</g>'
                         f'<text x="72" y="70" text-anchor="middle" fill="#e7edf6" font-family="sans-serif" font-size="10">{html.escape(label)}</text>'
                         f'<text x="72" y="90" text-anchor="middle" fill="#8c9eb3" font-family="sans-serif" font-size="8">{key}</text></g>')
    page = '''<!doctype html><html lang="es"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Iconos · Blender Remote</title><style>
:root{color-scheme:dark;--bg:#141922;--panel:#222833;--ink:#e7edf6;--muted:#a3b1c4;--accent:#69b9ef;--size:32px}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:16px system-ui,sans-serif}
body.light{color-scheme:light;--bg:#eef1f5;--panel:white;--ink:#202b3c;--muted:#506079;--accent:#1375ad}
header{padding:30px 24px 14px;max-width:1320px;margin:auto}h1{font-size:30px;margin:0 0 12px}p{color:var(--muted);line-height:1.6;max-width:850px;margin:8px 0}
.controls{display:flex;flex-wrap:wrap;align-items:center;gap:12px;padding:16px 24px;background:var(--bg);position:sticky;top:0;z-index:1;border-bottom:1px solid var(--muted)}
input,select,button{font:inherit;color:var(--ink);background:var(--panel);border:1px solid var(--muted);border-radius:8px;padding:10px;min-height:44px}
input[type=search]{flex:1;min-width:150px}label{display:flex;align-items:center;gap:8px}button{cursor:pointer}
main{display:grid;grid-template-columns:repeat(auto-fill,minmax(155px,1fr));gap:12px;max-width:1320px;margin:auto;padding:24px}
article{background:var(--panel);border:1px solid transparent;border-radius:12px;min-height:156px;padding:14px;text-align:center}
article:hover{border-color:var(--accent)}article[hidden]{display:none}.sample{height:64px;display:grid;place-items:center;color:var(--ink)}
svg{width:var(--size);height:var(--size)}b{display:block;font-size:14px;font-weight:550}small{display:block;color:var(--muted);font-size:10px;margin-top:8px;overflow-wrap:anywhere}
.active .sample{color:var(--accent)}#count{color:var(--muted);font-size:13px}footer{padding:0 24px 30px;color:var(--muted)}
</style><header><h1>Blender Remote · Iconos</h1><p>Un dibujo por intención. La misma herramienta conserva su símbolo en el rail, el menú y la bandeja. Los controles comunes comparten el mismo trazo que las herramientas de modelado.</p>
<p>Prueba el tamaño de 24 px para ver cómo se leen en los botones. El color indica estado; la forma distingue la acción. Esta lámina usa los trazados originales que lleva el APK.</p></header>
<div class="controls"><input id="search" type="search" placeholder="Buscar: bisecar, snap, lattice…" aria-label="Buscar iconos">
<select id="group" aria-label="Familia"><option value="">Todas las familias</option>__OPTIONS__</select>
<label>Tamaño <select id="size"><option>24</option><option selected>32</option><option>48</option><option>64</option></select></label>
<button id="theme">Fondo claro</button><button id="active" aria-pressed="false">Ver activos</button><span id="count"></span></div>
<main>__CARDS__</main><footer>Dibujos vectoriales originales · 24 × 24 · Trazo 1,7 · Sin imágenes ni fuentes externas.</footer>
<script>
const cards=[...document.querySelectorAll('article')];const search=document.querySelector('#search');const group=document.querySelector('#group');
const normalize=s=>s.normalize('NFD').replace(/[\u0300-\u036f]/g,'').toLowerCase();
function filter(){let n=0;for(const card of cards){card.hidden=!(normalize(card.dataset.search).includes(normalize(search.value))&&(!group.value||card.dataset.group===group.value));if(!card.hidden)n++}document.querySelector('#count').textContent=n+' iconos'}
search.oninput=filter;group.onchange=filter;filter();document.querySelector('#size').onchange=e=>document.documentElement.style.setProperty('--size',e.target.value+'px');
document.querySelector('#theme').onclick=e=>{document.body.classList.toggle('light');e.target.textContent=document.body.classList.contains('light')?'Fondo oscuro':'Fondo claro'};
document.querySelector('#active').onclick=e=>{const on=document.body.classList.toggle('active');e.target.setAttribute('aria-pressed',on);e.target.textContent=on?'Ver normales':'Ver activos'};
</script></html>'''
    page = page.replace('__CARDS__', ''.join(cards)).replace('__OPTIONS__', ''.join(f'<option>{html.escape(group)}</option>' for group in groups))
    (OUT / "blender-remote-iconos.html").write_text(page)
    height = ((len(glyphs) + 9) // 10) * 108
    (OUT / "lamina.svg").write_text(f'<svg xmlns="http://www.w3.org/2000/svg" width="1440" height="{height}" viewBox="0 0 1440 {height}"><rect width="1440" height="{height}" fill="#141922"/>{"".join(board)}</svg>')
    print(f"{len(glyphs)} iconos: {OUT}")


if __name__ == "__main__":
    main()
