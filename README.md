# Blender Tablet Remote

Interfaz táctil Android para controlar Blender sin convertir la tablet en un
escritorio remoto. Blender conserva el motor 3D; la app aporta vídeo, gestos y
controles adaptados a dedo y stylus.

## Documentación

- [`AGENTS.md`](AGENTS.md): arquitectura, invariantes y reglas de trabajo.
- [`blender-backend/docs/protocol.md`](blender-backend/docs/protocol.md): contrato canónico entre ambos lados.
- [`docs/cad-workspace.md`](docs/cad-workspace.md): dibujar, restringir, arrastrar, extruir y vaciar en CAD.
- [`docs/sculpt-workspace.md`](docs/sculpt-workspace.md): pinceles, presión, simetría, Dyntopo y Multires.
- [`docs/reference-images.md`](docs/reference-images.md): tablero de imágenes de referencia en la tablet.
- [`docs/cad-kernel-evaluation.md`](docs/cad-kernel-evaluation.md): evaluación reproducible y límites del kernel CAD.

## Arquitectura

```text
Tablet Android                         PC
Jetpack Compose -- WebSocket :8765 --> Blender + add-on
viewport MJPEG  <-- HTTP :8766 ------- captura GPU + ffmpeg
```

Hay dos canales para que un fotograma lento nunca bloquee una orden. La app mantiene
una interfaz de viewport completo, reconexión automática, selección táctil/stylus,
navegación, transformaciones modales, modelado Edit Mode, menús de archivo/objetos y
entrada de valores con unidades. El inventario preciso está en `AGENTS.md`.

El workspace CAD tiene raíles propios de geometría y restricciones: líneas,
rectángulos/cuadrados, círculos, arcos y redondeo de sketch. Permite seleccionar y
arrastrar puntos/aristas, restringirlos y extruir perfiles cerrados; el vaciado por
profundidad usa incrementos con lápiz y transparencia automática. El documento,
sus cotas y dependencias se guardan en el `.blend`. El kernel sigue siendo de malla
nativa, con un solver acotado; Object y Edit conservan su flujo habitual.

Sculpt incorpora nueve pinceles nativos, suavizado e inversión, presión del lápiz
para fuerza y radio, simetría X/Y/Z, máscaras, Dyntopo y niveles Multires.
Multiresolución se añade también desde **Modificadores → +**, con niveles de Vista,
Escultura y Render y un botón para crear subdivisiones reales.
El panel Referencias permite importar varias imágenes, ampliarlas y colocarlas
junto al modelo. En CAD, **Bocetos → Editar** reabre un boceto existente; al
seleccionar un perfil o sólido aparece **Editar boceto**.

Para piezas pequeñas, Extruir/Bisel/Inset ajustan sus pasos iniciales a la selección:
una pieza de 1 mm comienza con 0,01 mm de paso y 0,02 mm de Bisel. Sus unidades,
botones y arrastre comparten esa medida. Los presets cambian la unidad de trabajo
y conservan el tamaño real. **Encuadrar objeto** está en el panel de vistas;
los toques consecutivos en Edit ya no alejan la vista. Las referencias se abren
desde **Archivo → Imágenes de referencia…**.

## Directorios

```text
blender-backend/   add-on de Blender, protocolo y herramientas
android-client/    aplicación Kotlin/Compose
```

## Compilar

```bash
# Android requiere JDK 17
export JAVA_HOME=/home/valle/.local/opt/jdk-17.0.20+8
export PATH="$JAVA_HOME/bin:$PATH"
./gradlew :android-client:app:assembleDebug

# Add-on instalable
bash blender-backend/tools/build_addon.sh
```

El vídeo requiere `ffmpeg` en el `PATH` del PC.

## Uso

Instala el ZIP generado desde las preferencias de Blender, activa el add-on y habilita
**Arrancar con Blender** si quieres que el servidor se levante automáticamente. En la
tablet instala el APK, configura la IP del PC, puerto 8765 y token. El puerto MJPEG lo
anuncia el backend. No expongas estos puertos directamente a Internet; usa la VPN.

### Materiales, pintura y capturas

El workspace **Materiales** aísla uno o varios objetos y ofrece presets cotidianos
(Plástico, Aluminio, Hierro, Cristal, Roca, Madera, Mercurio…), una paleta sencilla,
acabados, ambientes y pintura de materiales con lápiz o dedo. Los presets personalizados
se importan como recetas JSON documentadas y las imágenes pintadas se guardan dentro
del `.blend`. **Archivo → Capturar escena** guarda un PNG limpio de la vista actual
desde cualquier modo.

- [Guía de Materiales y límites de pintura](docs/material-workspace.md)
- [Formato de recetas para IA y otros generadores](docs/material-recipe-v1.md)
- [JSON Schema v1](docs/material-recipe-v1.schema.json)
