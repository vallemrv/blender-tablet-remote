# ValleTrack integrado en Blender Tablet Remote

Adaptación del add-on ValleTrack 1.5.5 de **valle.mrv**, localizado en
`/home/valle/proyectos/valletrack`. El original se conserva intacto y se archivó una
copia de sus fuentes en `backups/valletrack-original/valletrack-1.5.5-original.zip`.
La integración tiene un único motor en `blender_tablet_remote/versioning`; no
registra los paneles ni las propiedades globales del add-on antiguo.

## Uso

1. Guarda el `.blend` con Archivo → Guardar como.
2. Abre **Archivo → Versiones · ValleTrack**. Escribe qué cambiaste y pulsa
   **Guardar versión local**. Funciona sin cuenta ni conexión a Gitea.
3. En **Cuenta y repo**, configura la dirección de Gitea y un token con
   `read:user` y `write:repository`. Puedes ajustar el nombre/correo de autor.
4. Crea un repositorio privado o conecta uno vacío existente. **Subir** publica
   las versiones locales; no se sube nada por guardar una versión.
5. **Explorar desde aquí**, sobre cualquier versión, abre otro recorrido desde
   ese commit. El nombre de la idea es opcional; el camino anterior sigue intacto.
6. **Ver historial** elige qué idea inspeccionar sin cambiar la escena.
   **Continuar esta idea** abre su último paso y conserva antes el avance del
   recorrido que abandonas. Guardar versión continúa la idea activa.
7. **Subir** publica todas las ideas de forma atómica, sin sobrescribir la principal
   con la alternativa abierta. **Descargar** importa los caminos nuevos y avanza
   los existentes solo cuando no divergen. No mezcla binarios automáticamente.
8. **Abrir repo de ValleTrack** clona repositorios creados con esta integración y
   abre su `model.blend`. No importa automáticamente el formato de repositorios
   arbitrarios ni migra historiales antiguos del ValleTrack original.

Cada proyecto tiene un ID persistente en las escenas del `.blend` y un repositorio
privado independiente en `~/.local/share/blender-tablet-remote/valletrack/repos/ID`.
Se versionan únicamente `model.blend` y `.gitattributes`: no se ejecuta `git add .`
sobre la carpeta del dibujo ni sobre el repositorio de código de Blender Remote.
Guardar como conserva el ID y, por tanto, continúa el historial del proyecto.
Los clones se abren en una copia de trabajo bajo `valletrack/projects/ID`, separada
del snapshot `repos/ID/model.blend` que Git cambia al navegar por las ideas.

Los recursos externos no están incluidos automáticamente. La casilla
**Empaquetar recursos compatibles** usa el empaquetado nativo de Blender antes de
guardar. Cachés, vídeos u otros recursos no empaquetables necesitan copia aparte.

## Archivos grandes y Gitea

Git LFS guarda los `.blend` como objetos binarios y deja punteros en Git. Se
instala para cada repositorio, sin cambiar la configuración global. En este
Manjaro se instaló Git LFS 3.8.0 en el directorio privado de herramientas. El
instalador `blender-backend/tools/install_git_lfs.py` descarga el binario oficial
Linux x86_64 y verifica su SHA-256; otras plataformas deben instalar Git LFS.

En Gitea debe estar habilitado `LFS_START_SERVER` y deben permitir las cargas el
servidor, el proxy y el almacenamiento. `LFS_MAX_FILE_SIZE` controla el tamaño
máximo; cero significa sin ese límite. LFS no evita consumir espacio: los cambios
binarios pueden ocupar una copia completa por versión.

Fuentes: [Git LFS](https://git-lfs.com/),
[Gitea: configuración LFS](https://docs.gitea.com/administration/git-lfs-setup/),
[Gitea: API y tokens](https://docs.gitea.com/development/api-usage/).

## Credenciales y transporte

El token se guarda solo en `valletrack/account.json`, con permisos 0600 y bajo un
directorio privado. No se cifra con un llavero del sistema. Nunca se devuelve en
los snapshots, se añade a una URL, se guarda en el `.blend` o se incluye en Git.
La tablet limpia el campo al enviar y no lo persiste. Configura la cuenta desde
una conexión remota de confianza; la conexión LAN de Blender Remote es la ya
configurada por el usuario.

Gitea usa HTTPS por defecto. HTTP fuera de localhost exige marcar explícitamente
que el token viajará sin cifrado. Las llamadas API rechazan redirecciones; las
credenciales Git se inyectan por entorno, vinculadas a la URL del servidor. Se
rechazan repositorios de otros servidores. Olvidar cuenta elimina el token local.

## Ejecución y recuperación

Git, LFS, HTTP y copias/hash de archivos se ejecutan en un hilo de I/O sin acceso
a bpy. El pump guarda/carga archivos y publica el estado del trabajo. Solo hay
una operación ValleTrack en curso; se puede cerrar el panel mientras termina.

Explorar o continuar una idea prepara su binario en un temporal del mismo
sistema de archivos. Antes de abrirlo, Blender vuelve a guardar el estado actual
y lo mueve a una copia de seguridad. También conserva las ediciones hechas
mientras Git preparaba el cambio. Ese avance se registra en el recorrido de
origen; después se activa la idea elegida o se crea `ideas/<nombre>` exactamente
en el commit seleccionado. No se añade una copia del pasado al final de una
lista lineal. El siguiente Guardar versión será hijo del punto elegido.

Si falla el registro del avance, se conserva la copia de seguridad y se muestra
su ruta. Abrir otro archivo durante la preparación impide aplicar el cambio.
Las escenas se abren con ejecución automática de scripts inhabilitada. Nunca se
hace force-push ni reset del historial. `restore` de clientes anteriores utiliza
este mismo camino de exploración; no hay una implementación lineal alternativa.

## Relación con el ValleTrack original

El original no creaba ramas Git con nombre: leía `git log --reflog`, reconstruía
recorridos por sus padres y los mostraba como Rama 1, Rama 2… Volver a un commit
movía HEAD mediante reset; guardar después iniciaba un recorrido distinto, y el
reflog permitía encontrar el anterior. La integración conserva esa forma de
explorar, pero usa referencias de rama permanentes para que ambos caminos sigan
accesibles y puedan sincronizarse con Gitea sin depender del reflog.

Validación: bifurcación en commits intermedios, regreso a ambos caminos tras
expirar el reflog y hacer GC, sincronización de todas las ideas con Git/LFS reales
y clonación; API Gitea simulada para
cuenta/repositorio, permisos y redirecciones; archivos `.blend` reales para
recuperación y ediciones concurrentes; parser y compilación Android. La conexión
con el Gitea real del usuario requiere que configure su cuenta.
