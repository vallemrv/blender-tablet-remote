"""Main-thread Blender boundary plus a single pure-I/O background job."""
import copy,os,threading,uuid
from concurrent.futures import Future
from pathlib import Path
import bpy
from .core import Store,VersionError,_fingerprint
from ..errors import BadPayload,CommandError

KEY='btr_valletrack_project'

def identifier():
    for scene in bpy.data.scenes:
        value=scene.get(KEY)
        if isinstance(value,str) and len(value)==32 and all(c in '0123456789abcdef' for c in value):return value
    return None


def idle_scene():
    from ..commands.modal import session
    from ..commands.tools import tool_session
    from ..commands import sculpt
    from ..cad.runtime import runtime as cad
    from ..materials.runtime import runtime as material
    if session.active or tool_session.active or cad.session or sculpt._stroke or material.stroke:
        raise CommandError('Confirma o cancela la herramienta antes de guardar una versión',code='session_active')


def save_scene(pack=False):
    idle_scene()
    if not bpy.data.filepath:raise BadPayload('Guarda primero el archivo con Guardar como')
    if pack:bpy.ops.file.pack_all()
    from ..cad.runtime import runtime as cad
    with cad.saving():bpy.ops.wm.save_mainfile()
    return bpy.data.filepath


class Runtime:
    def __init__(self):
        self.store=None;self.future=None;self.context=None;self.cache={};self.action=None
    def get_store(self):
        if self.store is None:self.store=Store()
        return self.store
    def status(self):
        self.poll()
        value=copy.deepcopy(self.cache)
        if not self.future and value.get('repo_id')!=identifier():value={}
        value.update(available=True,busy=self.future is not None,action=self.action,
                     source=bpy.data.filepath,scene_dirty=bool(bpy.data.is_dirty),repo_id=identifier())
        return value
    def start(self,action,payload):
        if action=='restore':action='explore'  # Existing clients use the same safe navigation path.
        self.poll()
        if self.future:raise CommandError('Espera a que termine la operación de ValleTrack',code='version_busy')
        store=self.get_store();source=bpy.data.filepath;repo_id=identifier()
        if action=='commit':
            message=payload.get('message')
            if not isinstance(message,str) or not message.strip() or len(message)>500 or '\0' in message:
                raise BadPayload('Escribe un mensaje de versión de hasta 500 caracteres')
        if action in ('explore','switch','push','pull','link','create_remote') and repo_id is None:
            raise BadPayload('Guarda una primera versión local antes de usar las ideas')
        if action in ('commit','explore','switch','clone'):
            idle_scene()
            if not source and (action!='clone' or bpy.data.is_dirty):raise BadPayload('Guarda primero el archivo con Guardar como')
            if action=='commit' and repo_id is None:
                repo_id=uuid.uuid4().hex;bpy.context.scene[KEY]=repo_id
            if source and repo_id and Path(source).resolve()==(store.repo(repo_id)/'model.blend').resolve():
                # Older clones opened the repository's snapshot itself. Move to
                # an independent working file before branch checkouts can touch it.
                working=store.root/'projects'/repo_id/('model-'+uuid.uuid4().hex[:6]+'.blend')
                working.parent.mkdir(parents=True,exist_ok=True)
                from ..cad.runtime import runtime as cad
                with cad.saving():bpy.ops.wm.save_as_mainfile(filepath=str(working))
            if source:source=save_scene(bool(payload.get('pack_resources',False)))
        context=dict(source=source,repo_id=repo_id,scene=bpy.context.scene.as_pointer(),
                     fingerprint=_fingerprint(source) if source and Path(source).is_file() else None,
                     backup=payload.get('backup'))
        args=dict(payload);args.pop('_client_id',None)
        future=Future();self.future=future;self.context=context;self.action=action
        self.cache.pop('error',None);self.cache['message']='';self.cache['repo_id']=repo_id
        def work():
            try:
                if action=='status':result={}
                elif action=='finish_navigation':
                    result=store.finish_navigation(repo_id,source,args['backup'],args['navigation'])
                elif action=='clone':result=store.clone_project(args.get('url',''))
                elif action=='commit':result=store.snapshot(repo_id,source,args.get('message',''))
                elif action in ('explore','switch'):result=store.prepare_navigation(repo_id,source,action,args.get('revision'),args.get('branch'),args.get('label',''))
                elif action=='connect':result=store.connect(args.get('server'),args.get('access_token'),args.get('author_name',''),args.get('author_email',''),bool(args.get('allow_http',False)))
                elif action=='identity':result=store.identity(args.get('author_name'),args.get('author_email'))
                elif action=='forget':result=store.forget()
                elif action=='link':result=store.link(repo_id,args.get('url',''))
                elif action=='create_remote':result=store.create_remote(repo_id,args.get('name'))
                elif action=='push':result=store.push(repo_id)
                elif action=='pull':result=store.pull(repo_id)
                else:raise VersionError('Acción ValleTrack no compatible')
                result={**store.status(repo_id,source,args.get('history_branch') if action=='status' else None),**result}
                future.set_result(result)
            except Exception as exc:
                if 'result' in locals() and result.get('restore_path'):Path(result['restore_path']).unlink(missing_ok=True)
                # Never expose raw unexpected request exceptions or credentials.
                future.set_exception(exc if isinstance(exc,VersionError) else VersionError('No se pudo completar la operación de ValleTrack'))
            finally:args.clear()
        threading.Thread(target=work,name='BTR-ValleTrack',daemon=True).start()
        return self.status()
    def poll(self):
        if not self.future or not self.future.done():return
        future,context,action=self.future,self.context,self.action
        self.future=None;self.action=None;self.context=None
        try:
            result=future.result()
            if result.get('open_path'):
                idle_scene()
                if bpy.context.scene.as_pointer()!=context['scene'] or bpy.data.filepath!=context['source']:
                    raise VersionError('La escena cambió. El repositorio está descargado en '+result['open_path'])
                if bpy.data.filepath:save_scene()
                elif bpy.data.is_dirty:raise VersionError('Guarda la escena actual antes de abrir el repositorio descargado')
                from ..commands import file
                from ..cad.runtime import runtime as cad
                from ..materials.runtime import runtime as material
                material.leave();cad.leave()
                bpy.ops.wm.open_mainfile(filepath=result.pop('open_path'),use_scripts=False)
                file._reset_session()
                for scene in bpy.data.scenes:scene[KEY]=result['repo_id']
                save_scene()
            if result.get('restore_path'):
                temporary=Path(result.pop('restore_path'))
                try:
                    idle_scene()
                    if (bpy.context.scene.as_pointer()!=context['scene'] or bpy.data.filepath!=context['source']
                            or _fingerprint(context['source'])!=context['fingerprint']):
                        raise VersionError('La escena cambió durante la recuperación. Se conserva tu trabajo; vuelve a recuperar la versión')
                    # Save again on the main thread: edits made while Git was
                    # reading the old version also get a safety copy, never lost.
                    save_scene()
                    backup=Path(context['source']).with_name('.valletrack-before-'+uuid.uuid4().hex+'.blend')
                    os.replace(context['source'],backup)
                    try:
                        os.replace(temporary,context['source'])
                        from ..commands import file
                        from ..cad.runtime import runtime as cad
                        from ..materials.runtime import runtime as material
                        material.leave();cad.leave()
                        bpy.ops.wm.open_mainfile(filepath=context['source'],use_scripts=False)
                        file._reset_session()
                    except Exception:
                        os.replace(backup,context['source'])
                        bpy.ops.wm.open_mainfile(filepath=context['source'],use_scripts=False)
                        raise
                    for scene in bpy.data.scenes:
                        if scene.get(KEY)!=context['repo_id']:scene[KEY]=context['repo_id']
                    self.cache=result
                    self.start('finish_navigation',dict(backup=str(backup),navigation=result['navigation']))
                    return
                finally:temporary.unlink(missing_ok=True)
            self.cache=result
        except Exception as exc:
            self.cache['error']=str(exc) if isinstance(exc,(VersionError,CommandError)) else 'No se pudo completar ValleTrack'
            if action=='finish_navigation' and context.get('backup') and Path(context['backup']).exists():
                self.cache['error']+=' · La copia de seguridad sigue en '+context['backup']
        try:
            from ..bridge import broadcast_event
            broadcast_event('versioning.changed',self.status())
        except Exception:pass

runtime=Runtime()
