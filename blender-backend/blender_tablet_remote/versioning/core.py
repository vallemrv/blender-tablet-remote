"""ValleTrack 1.5.5 adaptation. Pure I/O: this module never imports bpy.

The original by valle.mrv used git add . and reset --hard. Each scene now owns
an isolated repository; restoring appends history and preserves a safety version.
"""
import base64,hashlib,json,os,re,shutil,subprocess,tempfile,uuid
from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit,quote
from urllib.request import Request,build_opener,HTTPRedirectHandler
from urllib.error import HTTPError,URLError

class VersionError(Exception):pass
class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):return None


def private_root():
    return Path.home()/'.local/share/blender-tablet-remote/valletrack'


def _write_json(path,value):
    path.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    fd,name=tempfile.mkstemp(prefix='.valletrack-',dir=path.parent)
    temporary=Path(name)
    with os.fdopen(fd,'w') as stream:json.dump(value,stream,ensure_ascii=False)
    os.replace(temporary,path)
    path.chmod(0o600)


def _fingerprint(path):
    stat=Path(path).stat()
    return [stat.st_size,stat.st_mtime_ns]


def _hash(path):
    digest=hashlib.sha256()
    with open(path,'rb') as stream:
        for block in iter(lambda:stream.read(1024*1024),b''):digest.update(block)
    return digest.hexdigest()


class Store:
    def __init__(self,root=None):
        self.root=Path(root) if root else private_root()
        self.root.mkdir(parents=True,exist_ok=True,mode=0o700)
        self.settings_path=self.root/'account.json'
    def settings(self):
        return json.loads(self.settings_path.read_text()) if self.settings_path.exists() else {}
    def public_account(self):
        c=self.settings()
        return {k:c.get(k,'') for k in ('server','username','author_name','author_email')}|dict(has_token=bool(c.get('token')),allow_http=bool(c.get('allow_http')))
    def repo(self,identifier):
        if not re.fullmatch('[a-f0-9]{32}',identifier or ''):raise VersionError('Guarda una primera versión para iniciar el proyecto')
        return self.root/'repos'/identifier
    def metadata(self,identifier):
        path=self.repo(identifier)/'project.json'
        return json.loads(path.read_text()) if path.exists() else {}
    def environment(self,authenticated=False):
        env=os.environ.copy()
        for key in list(env):
            if key.startswith('GIT_'):env.pop(key)
        env['PATH']=str(Path.home()/'.local/share/blender-tablet-remote/bin')+os.pathsep+env.get('PATH','')
        env['GIT_TERMINAL_PROMPT']='0';env['GIT_LFS_SKIP_SMUDGE']='0'
        # Do not inherit credentials/config entries from a parent process.
        for key in list(env):
            if key.startswith(('GIT_CONFIG_KEY_','GIT_CONFIG_VALUE_')):env.pop(key)
        values=[('credential.helper',''),('http.followRedirects','false')]
        if authenticated:
            c=self.settings()
            if not c.get('server') or not c.get('token'):raise VersionError('Conecta primero tu cuenta Gitea')
            auth=base64.b64encode((c['username']+':'+c['token']).encode()).decode()
            values.append(('http.'+c['server']+'/.extraheader','Authorization: Basic '+auth))
        env['GIT_CONFIG_COUNT']=str(len(values))
        for i,(key,value) in enumerate(values):env['GIT_CONFIG_KEY_'+str(i)]=key;env['GIT_CONFIG_VALUE_'+str(i)]=value
        return env
    def git(self,repo,*args,authenticated=False,input=None,output=None,check=True):
        if not shutil.which('git'):raise VersionError('Instala Git en el PC de Blender')
        try:
            result=subprocess.run(['git','-c','core.quotepath=false',*args],cwd=repo,env=self.environment(authenticated),
                                  input=input,stdout=output if output is not None else subprocess.PIPE,
                                  stderr=subprocess.PIPE,timeout=600)
        except subprocess.TimeoutExpired:raise VersionError('Git agotó el tiempo de espera; puedes volver a intentarlo') from None
        if check and result.returncode:
            message=result.stderr.decode('utf8','replace')[-1500:]
            secret=self.settings().get('token','')
            if secret:
                message=message.replace(secret,'***')
                encoded=base64.b64encode((self.settings().get('username','')+':'+secret).encode()).decode()
                message=message.replace(encoded,'***')
            message=re.sub(r'(https?://)[^\s/@]+:[^\s/@]+@',r'\1***@',message)
            raise VersionError(message.strip() or 'Git no pudo completar la operación')
        return result
    def has_lfs(self):
        return self.git(self.root,'lfs','version',check=False).returncode==0
    def _author(self):
        c=self.settings()
        values=[]
        for key,default in [('name','Blender Remote'),('email','blender-remote@localhost')]:
            configured=c.get('author_'+key)
            if not configured:
                r=self.git(self.root,'config','--global','--get','user.'+key,check=False)
                configured=r.stdout.decode().strip() if r.returncode==0 else default
            values.append(configured)
        return values
    def _install_lfs(self,repo):
        hooks=repo/'.git'/'valletrack-hooks';hooks.mkdir(exist_ok=True)
        self.git(repo,'config','core.hooksPath',str(hooks))
        self.git(repo,'lfs','install','--local','--force')

    def initialize(self,identifier,source):
        repo=self.repo(identifier)
        if not self.has_lfs():raise VersionError('Falta Git LFS. Ejecuta blender-backend/tools/install_git_lfs.py en el PC')
        repo.mkdir(parents=True,exist_ok=True,mode=0o700)
        if not (repo/'.git').exists():
            self.git(repo,'init','--initial-branch=main')
            (repo/'.gitattributes').write_text('model.blend filter=lfs diff=lfs merge=lfs -text\n')
        self._install_lfs(repo)
        name,email=self._author()
        self.git(repo,'config','user.name',name);self.git(repo,'config','user.email',email)
        meta=self.metadata(identifier);meta.update(source=str(Path(source).resolve()),filename=Path(source).name)
        if meta.get('primary_branch') not in self._heads(repo):meta['primary_branch']=self._primary(identifier,self._heads(repo))
        _write_json(repo/'project.json',meta)
        return repo
    def _commit(self,repo,message):
        self.git(repo,'add','--','.gitattributes','model.blend')
        changed=self.git(repo,'diff','--cached','--quiet',check=False).returncode
        if changed:self.git(repo,'-c','commit.gpgsign=false','commit','-m',message)
        return self.git(repo,'rev-parse','HEAD').stdout.decode().strip()
    def snapshot(self,identifier,source,message):
        if not isinstance(message,str) or not message.strip() or len(message)>500 or '\0' in message:raise VersionError('Escribe un mensaje de versión de hasta 500 caracteres')
        source=Path(source)
        if not source.is_file() or source.suffix.lower()!='.blend':raise VersionError('Guarda primero el archivo .blend')
        repo=self.initialize(identifier,source)
        before=_fingerprint(source)
        fd,name=tempfile.mkstemp(prefix='.snapshot-',dir=repo);os.close(fd)
        temporary=Path(name);shutil.copyfile(source,temporary)
        if before!=_fingerprint(source):temporary.unlink(missing_ok=True);raise VersionError('El archivo cambió mientras se guardaba la versión; inténtalo otra vez')
        os.replace(temporary,repo/'model.blend')
        commit=self._commit(repo,message.strip())
        meta=self.metadata(identifier);meta['saved_hash']=_hash(repo/'model.blend');_write_json(repo/'project.json',meta)
        return dict(commit=commit,message='Versión guardada',**self.status(identifier,str(source)))
    def _heads(self,repo,prefix='refs/heads/'):
        raw=self.git(repo,'for-each-ref','--sort=-committerdate','--format=%(refname)%00%(objectname)%00%(symref)',prefix).stdout.decode()
        return {ref.removeprefix(prefix):oid for line in raw.splitlines() for ref,oid,symbolic in [line.split('\0')]
                if not symbolic}
    def _primary(self,identifier,heads):
        meta=self.metadata(identifier)
        for candidate in (meta.get('primary_branch'),'main',meta.get('remote_branch')):
            if candidate in heads:return candidate
        return next(iter(heads),'main')
    def status(self,identifier=None,source='',history_branch=None):
        result=dict(ready=False,repo_id=identifier,source=source,account=self.public_account(),lfs_available=self.has_lfs(),commits=[],branches=[])
        if not identifier:return result
        repo=self.repo(identifier)
        if not (repo/'.git').exists():return result
        active=self.git(repo,'branch','--show-current').stdout.decode().strip()
        heads=self._heads(repo);primary=self._primary(identifier,heads)
        if history_branch is not None and history_branch not in heads:raise VersionError('Esa idea ya no existe')
        viewed=history_branch or active
        result.update(ready=True,local_path=str(repo),branch=active,head=heads.get(active,''),history_branch=viewed,primary_branch=primary)
        for name,tip in heads.items():
            base=self.git(repo,'merge-base','refs/heads/'+primary,'refs/heads/'+name,check=False) if primary in heads and name!=primary else None
            result['branches'].append(dict(name=name,tip=tip,active=name==active,
                label='Principal' if name==primary else name.removeprefix('ideas/').replace('-',' '),
                base=base.stdout.decode().strip() if base and base.returncode==0 else None))
        log=self.git(repo,'log','-100','--format=%H%x00%aI%x00%s%x00%an%x00%P','refs/heads/'+viewed,check=False)
        if log.returncode==0:
            for line in log.stdout.decode('utf8','replace').splitlines():
                parts=line.split('\0')
                if len(parts)==5:result['commits'].append(dict(id=parts[0],date=parts[1],message=parts[2],author=parts[3],parents=parts[4].split()))
        remote=self.git(repo,'remote','get-url','origin',check=False)
        if remote.returncode==0:result['remote']=remote.stdout.decode().strip()
        counts=self.git(repo,'rev-list','--left-right','--count','HEAD...@{upstream}',check=False)
        if counts.returncode==0:result['ahead'],result['behind']=map(int,counts.stdout.split())
        meta=self.metadata(identifier)
        result['file_changed']=bool(source and Path(source).is_file() and meta.get('saved_hash')!=_hash(source))
        return result
    def _idea_name(self,repo,label):
        if not isinstance(label,str) or len(label)>80:raise VersionError('Escribe un nombre de idea de hasta 80 caracteres')
        slug=re.sub(r'[^\w-]+','-',label.strip().lower()).strip('-')
        name='ideas/'+(slug or datetime.now().strftime('%Y%m%d-%H%M%S')+'-'+uuid.uuid4().hex[:4])
        self.git(repo,'check-ref-format','--branch',name)
        if name in self._heads(repo):raise VersionError('Ya existe una idea con ese nombre; continúala o elige otro')
        return name
    def prepare_navigation(self,identifier,source,mode,revision=None,branch=None,label=''):
        repo=self.repo(identifier);heads=self._heads(repo)
        current=self.git(repo,'branch','--show-current').stdout.decode().strip()
        if mode=='switch':
            if branch not in heads:raise VersionError('Esa idea ya no existe')
            if branch==current:return dict(message='Ya estás trabajando en esta idea')
            revision=heads[branch]
        elif mode=='explore':
            if not re.fullmatch('[0-9a-f]{40,64}',revision or ''):raise VersionError('Versión no válida')
            branch=self._idea_name(repo,label)
        else:raise VersionError('Acción de historial no válida')
        self.git(repo,'cat-file','-e',revision+':model.blend')
        self.snapshot(identifier,source,'Avance guardado antes de cambiar de idea')
        temporary=self._materialize(repo,source,revision)
        return dict(restore_path=temporary,navigation=dict(mode=mode,branch=branch,revision=revision,from_branch=current),
                    message='Idea preparada')
    def _materialize(self,repo,source,revision):
        fd,temp=tempfile.mkstemp(prefix='.valletrack-restore-',suffix='.blend',dir=Path(source).parent);os.close(fd)
        fd,name=tempfile.mkstemp(prefix='.restore-',dir=repo);os.close(fd)
        blob=Path(name)
        try:
            with blob.open('wb') as output:self.git(repo,'show',revision+':model.blend',output=output)
            pointer=blob.read_bytes() if blob.stat().st_size<2048 else b''
            if pointer.startswith(b'version https://git-lfs.github.com/spec/v1'):
                with open(temp,'wb') as output:self.git(repo,'lfs','smudge','--','model.blend',input=pointer,output=output,authenticated=bool(self.settings().get('token')))
            else:shutil.copyfile(blob,temp)
            with open(temp,'rb') as stream:
                if stream.read(100).startswith(b'version https://git-lfs.github.com/spec/v1'):raise VersionError('No se ha descargado el archivo LFS de esta versión')
            return temp
        except Exception:
            Path(temp).unlink(missing_ok=True);raise
        finally:blob.unlink(missing_ok=True)
    def finish_navigation(self,identifier,source,backup,navigation):
        repo=self.repo(identifier);heads=self._heads(repo)
        mode,branch,revision=navigation['mode'],navigation['branch'],navigation['revision']
        current=self.git(repo,'branch','--show-current').stdout.decode().strip()
        if current!=navigation['from_branch']:raise VersionError('El camino activo cambió mientras se preparaba la escena')
        if mode=='explore' and branch in heads:raise VersionError('Ya existe esa idea')
        if mode=='switch' and heads.get(branch)!=revision:raise VersionError('La idea de destino avanzó; vuelve a seleccionarla')
        self.snapshot(identifier,backup,'Avance guardado antes de cambiar de idea')
        if mode=='explore':self.git(repo,'switch','-c',branch,revision)
        else:self.git(repo,'switch',branch)
        meta=self.metadata(identifier);meta.update(source=str(Path(source).resolve()),filename=Path(source).name,
                                                  saved_hash=_hash(repo/'model.blend'))
        _write_json(repo/'project.json',meta)
        Path(backup).unlink(missing_ok=True)
        return dict(**self.status(identifier,source),message='Idea abierta; el otro recorrido se conserva')
    def validate_server(self,url,allow_http=False):
        if not isinstance(url,str):raise VersionError('Dirección Gitea no válida')
        value=url.strip().rstrip('/');u=urlsplit(value)
        if any(c.isspace() for c in value) or u.scheme not in ('http','https') or not u.hostname or u.username or u.password or u.query or u.fragment:
            raise VersionError('Usa la dirección HTTP(S) de Gitea sin credenciales en la URL')
        if u.scheme=='http' and u.hostname not in ('localhost','127.0.0.1','::1') and not allow_http:
            raise VersionError('Para proteger la cuenta, utiliza HTTPS en Gitea')
        return value
    def api(self,server,token,path,data=None):
        body=None if data is None else json.dumps(data).encode()
        request=Request(server+'/api/v1'+path,data=body,headers={'Authorization':'token '+token,'Content-Type':'application/json','Accept':'application/json'})
        try:
            with build_opener(NoRedirect()).open(request,timeout=30) as response:return json.load(response)
        except HTTPError as exc:
            code=exc.code;exc.close()
            raise VersionError('Gitea respondió HTTP '+str(code)+': revisa la dirección y los permisos del token') from None
        except (URLError,TimeoutError,ValueError):raise VersionError('No se pudo conectar con Gitea; revisa dirección, certificado y conexión') from None
    def connect(self,server,token,author_name='',author_email='',allow_http=False):
        server=self.validate_server(server,allow_http=allow_http)
        if not isinstance(token,str) or not token.strip():raise VersionError('Introduce un token de acceso de Gitea')
        user=self.api(server,token.strip(),'/user')
        if not user.get('login'):raise VersionError('Gitea no devolvió una cuenta válida')
        cfg=dict(server=server,token=token.strip(),username=user['login'],allow_http=bool(allow_http),
                 author_name=author_name.strip() or user.get('full_name') or user['login'],
                 author_email=author_email.strip() or user.get('email') or user['login']+'@localhost')
        _write_json(self.settings_path,cfg)
        return dict(account=self.public_account(),message='Cuenta Gitea conectada')
    def identity(self,name,email):
        if not isinstance(name,str) or not name.strip() or not isinstance(email,str) or '@' not in email:raise VersionError('Escribe nombre y correo para las versiones')
        c=self.settings();c.update(author_name=name.strip(),author_email=email.strip());_write_json(self.settings_path,c)
        return dict(account=self.public_account(),message='Autor guardado')
    def forget(self):
        c=self.settings()
        for key in ('token','server','username','allow_http'):c.pop(key,None)
        _write_json(self.settings_path,c)
        return dict(account=self.public_account(),message='Cuenta desconectada')
    def remote_url(self,url):
        c=self.settings();server=c.get('server','');u=urlsplit(url)
        if not server or not url.startswith(server+'/') or u.username or u.password or u.query or u.fragment:
            raise VersionError('El repositorio debe pertenecer a la cuenta Gitea configurada')
        tail=url[len(server)+1:].removesuffix('.git')
        parts=tail.split('/')
        if len(parts)!=2 or any(not re.fullmatch(r'[\w.-]+',x) or x in ('.','..') for x in parts):raise VersionError('Usa la URL HTTPS de usuario/repositorio.git')
        return server+'/'+tail+'.git',parts
    def link(self,identifier,url):
        repo=self.repo(identifier);url,parts=self.remote_url(url)
        c=self.settings();info=self.api(c['server'],c['token'],'/repos/'+quote(parts[0],safe='')+'/'+quote(parts[1],safe=''))
        branch=info.get('default_branch') or 'main'
        self.git(repo,'check-ref-format','--branch',branch)
        existing=self.git(repo,'remote','get-url','origin',check=False)
        self.git(repo,'remote','set-url' if existing.returncode==0 else 'add','origin',url)
        meta=self.metadata(identifier);meta['remote_branch']=branch;_write_json(repo/'project.json',meta)
        return dict(message='Repositorio conectado')
    def create_remote(self,identifier,name):
        if not isinstance(name,str) or not re.fullmatch(r'[\w.-]+',name) or name in ('.','..'):raise VersionError('Nombre de repositorio no válido')
        c=self.settings()
        if not c.get('token'):raise VersionError('Conecta primero la cuenta Gitea')
        result=self.api(c['server'],c['token'],'/user/repos',dict(name=name,private=True,auto_init=False))
        url=c['server']+'/'+c['username']+'/'+result['name']+'.git'
        try:return self.link(identifier,url)
        except VersionError as exc:raise VersionError('Repositorio creado en '+url+', pero falta conectarlo: '+str(exc)) from None
    def _remote(self,identifier):
        repo=self.repo(identifier);url=self.git(repo,'remote','get-url','origin').stdout.decode().strip()
        self.remote_url(url)
        return repo
    def clone_project(self,url):
        url,parts=self.remote_url(url);c=self.settings()
        info=self.api(c['server'],c['token'],'/repos/'+quote(parts[0],safe='')+'/'+quote(parts[1],safe=''))
        branch=info.get('default_branch') or 'main'
        self.git(self.root,'check-ref-format','--branch',branch)
        if not self.has_lfs():raise VersionError('Instala Git LFS antes de abrir este repositorio')
        identifier=uuid.uuid4().hex;repo=self.repo(identifier);repo.parent.mkdir(parents=True,exist_ok=True)
        try:
            self.git(self.root,'clone','--no-checkout','--branch',branch,'--',url,str(repo),authenticated=True)
            self._install_lfs(repo)
            self.git(repo,'checkout',branch,authenticated=True)
            self.git(repo,'lfs','pull',authenticated=True)
            source=repo/'model.blend'
            if source.is_symlink() or not source.is_file():raise VersionError('El repositorio no contiene model.blend de ValleTrack Remote')
            working=self.root/'projects'/identifier/'model.blend';working.parent.mkdir(parents=True,exist_ok=True)
            shutil.copyfile(source,working)
            _write_json(repo/'project.json',dict(source=str(working),filename='model.blend',remote_branch=branch,primary_branch=branch,saved_hash=_hash(source)))
            self._update_paths(repo,branch,branch)
            return dict(**self.status(identifier,str(working)),open_path=str(working),message='Repositorio descargado')
        except Exception:
            shutil.rmtree(repo,ignore_errors=True)
            shutil.rmtree(self.root/'projects'/identifier,ignore_errors=True)
            raise

    def push(self,identifier):
        repo=self._remote(identifier);heads=self._heads(repo)
        primary=self._primary(identifier,heads);remote_default=self.metadata(identifier).get('remote_branch',primary)
        refs=['refs/heads/'+name+':refs/heads/'+(remote_default if name==primary else name) for name in heads]
        if not refs:raise VersionError('Guarda una versión primero')
        self.git(repo,'push','--atomic','--set-upstream','origin',*refs,authenticated=True)
        return dict(message='Ideas y versiones subidas a Gitea')
    def _update_paths(self,repo,primary,remote_default):
        local=self._heads(repo);remote=self._heads(repo,'refs/remotes/origin/')
        active=self.git(repo,'branch','--show-current').stdout.decode().strip()
        updates=[]
        for name,tip in remote.items():
            target=primary if name==remote_default else name
            previous=local.get(target)
            if previous==tip:continue
            if previous:
                if self.git(repo,'merge-base','--is-ancestor',previous,tip,check=False).returncode:
                    if self.git(repo,'merge-base','--is-ancestor',tip,previous,check=False).returncode:
                        raise VersionError('La idea '+target+' ha divergido. Se conserva lo local; no se mezclan archivos Blender automáticamente')
                    continue  # Local is ahead: leave its work untouched.
            updates.append((target,previous,tip,name))
        # Validate every path before advancing any local branch.
        for target,previous,tip,name in updates:
            if target==active:self.git(repo,'merge','--ff-only','refs/remotes/origin/'+name,authenticated=True)
            else:self.git(repo,'update-ref','refs/heads/'+target,tip,previous or '0'*len(tip))
    def pull(self,identifier):
        repo=self._remote(identifier);heads=self._heads(repo);primary=self._primary(identifier,heads)
        remote_default=self.metadata(identifier).get('remote_branch',primary)
        self.git(repo,'fetch','origin','+refs/heads/*:refs/remotes/origin/*',authenticated=True)
        self._update_paths(repo,primary,remote_default)
        self.git(repo,'lfs','pull',authenticated=True)
        return dict(message='Ideas descargadas; elige el recorrido que quieres continuar')
