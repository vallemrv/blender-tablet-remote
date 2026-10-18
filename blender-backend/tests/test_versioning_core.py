"""Pure Git/LFS tests: isolated repos, non-destructive history and Gitea API."""
import base64,importlib.util,json,os,stat,tempfile,threading,unittest,subprocess
from pathlib import Path
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from unittest.mock import patch
spec=importlib.util.spec_from_file_location('valletrack_core',Path(__file__).resolve().parents[1]/'blender_tablet_remote/versioning/core.py')
core=importlib.util.module_from_spec(spec);spec.loader.exec_module(core)

class GitTests(unittest.TestCase):
    def setUp(self):
        self.folder=tempfile.TemporaryDirectory();self.addCleanup(self.folder.cleanup)
        self.root=Path(self.folder.name);self.store=core.Store(self.root/'private');self.id='a'*32
        self.store.identity('Test Author','test@example.invalid')
        self.source=self.root/'model with spaces.blend';self.source.write_bytes(b'BLENDER'+b'first'*20000)
    def test_real_lfs_snapshots_keep_unrelated_files_out_and_restore_preserves_history(self):
        (self.root/'unrelated.txt').write_text('never commit this')
        a=self.store.snapshot(self.id,self.source,'Primera "versión"')
        first=self.source.read_bytes();repo=self.store.repo(self.id)
        blob=self.store.git(repo,'show','HEAD:model.blend').stdout
        self.assertTrue(blob.startswith(b'version https://git-lfs.github.com/spec/v1'))
        tracked=self.store.git(repo,'ls-files').stdout.decode().splitlines()
        self.assertEqual(tracked,['.gitattributes','model.blend'])
        self.source.write_bytes(b'BLENDER second')
        b=self.store.snapshot(self.id,self.source,'Segunda')
        self.source.write_bytes(b'BLENDER unsaved-on-git')
        result=self.store.prepare_navigation(self.id,str(self.source),'explore',revision=a['commit'])
        self.assertEqual(Path(result['restore_path']).read_bytes(),first)
        self.assertEqual(self.source.read_bytes(),b'BLENDER unsaved-on-git')
        history=self.store.status(self.id,str(self.source))['commits']
        self.assertEqual(len(history),3)
        self.assertIn(b['commit'],[x['id'] for x in history])
        self.assertTrue(history[0]['message'].startswith('Avance guardado'))
        Path(result['restore_path']).unlink()
    def test_no_change_does_not_create_empty_commit_and_environment_is_isolated(self):
        with patch.dict(os.environ,{'GIT_DIR':'/not/our/repository','GIT_TRACE_CURL':'1'}):
            first=self.store.snapshot(self.id,self.source,'One')
            second=self.store.snapshot(self.id,self.source,'Same')
            self.assertEqual(first['commit'],second['commit'])
            self.assertNotIn('GIT_DIR',self.store.environment());self.assertNotIn('GIT_TRACE_CURL',self.store.environment())
    def test_real_push_clone_and_fast_forward_with_lfs(self):
        first=self.store.snapshot(self.id,self.source,'Start')
        oldest=self.source.read_bytes()
        self.source.write_bytes(b'BLENDER newer head')
        self.store.snapshot(self.id,self.source,'Before clone')
        repo=self.store.repo(self.id);remote=self.root/'remote.git';remote.mkdir()
        self.store.git(remote,'init','--bare','--initial-branch=main')
        self.store.git(repo,'remote','add','origin',str(remote))
        config=self.store.settings();config.update(server='https://example.invalid',username='test',token='test-only')
        core._write_json(self.store.settings_path,config)
        with patch.object(self.store,'_remote',return_value=repo):self.store.push(self.id)
        expected=self.source.read_bytes()
        with patch.object(self.store,'remote_url',return_value=(str(remote),['test','model'])),patch.object(self.store,'api',return_value=dict(default_branch='main')):
            cloned=self.store.clone_project('https://example.invalid/test/model.git')
        clone_repo=self.store.repo(cloned['repo_id'])
        self.assertEqual(Path(cloned['open_path']).read_bytes(),expected)
        restored=self.store.prepare_navigation(cloned['repo_id'],cloned['open_path'],'explore',revision=first['commit'])
        self.assertEqual(Path(restored['restore_path']).read_bytes(),oldest)
        Path(restored['restore_path']).unlink()
        clone_source=Path(cloned['open_path']);clone_source.write_bytes(b'BLENDER remote version')
        self.store.snapshot(cloned['repo_id'],clone_source,'Remote update')
        with patch.object(self.store,'_remote',return_value=clone_repo):self.store.push(cloned['repo_id'])
        with patch.object(self.store,'_remote',return_value=repo):self.store.pull(self.id)
        self.assertEqual((repo/'model.blend').read_bytes(),b'BLENDER remote version')
        self.assertEqual(self.source.read_bytes(),expected)
        # Divergent binary histories are never reset or merged automatically.
        self.source.write_bytes(b'BLENDER local branch');local=self.store.snapshot(self.id,self.source,'Local')
        clone_source.write_bytes(b'BLENDER other update');self.store.snapshot(cloned['repo_id'],clone_source,'Other')
        with patch.object(self.store,'_remote',return_value=clone_repo):self.store.push(cloned['repo_id'])
        with patch.object(self.store,'_remote',return_value=repo),self.assertRaises(core.VersionError):self.store.pull(self.id)
        self.assertEqual(self.store.status(self.id,str(self.source))['commits'][0]['id'],local['commit'])
        self.assertEqual((repo/'model.blend').read_bytes(),b'BLENDER local branch')

    def navigate(self,mode,**values):
        result=self.store.prepare_navigation(self.id,str(self.source),mode,**values)
        backup=self.root/'backup.blend';backup.write_bytes(self.source.read_bytes())
        self.source.write_bytes(Path(result['restore_path']).read_bytes());Path(result['restore_path']).unlink()
        return self.store.finish_navigation(self.id,str(self.source),str(backup),result['navigation'])
    def test_exploration_forks_at_commit_and_returns_to_both_paths_after_gc(self):
        first=self.store.snapshot(self.id,self.source,'A');first_bytes=self.source.read_bytes()
        self.source.write_bytes(b'BLENDER main B');second=self.store.snapshot(self.id,self.source,'B')
        self.source.write_bytes(b'BLENDER main C');third=self.store.snapshot(self.id,self.source,'C')
        idea=self.navigate('explore',revision=second['commit'],label='Otra idea')
        self.assertEqual(idea['branch'],'ideas/otra-idea');self.assertEqual(idea['head'],second['commit'])
        self.assertEqual(self.source.read_bytes(),b'BLENDER main B')
        self.source.write_bytes(b'BLENDER alternative D');fourth=self.store.snapshot(self.id,self.source,'D')
        self.assertEqual(fourth['commits'][0]['parents'],[second['commit']])
        viewed=self.store.status(self.id,str(self.source),history_branch='main')
        self.assertEqual(viewed['branch'],'ideas/otra-idea');self.assertEqual(viewed['commits'][0]['id'],third['commit'])
        self.assertEqual(self.source.read_bytes(),b'BLENDER alternative D')
        self.navigate('switch',branch='main');self.assertEqual(self.source.read_bytes(),b'BLENDER main C')
        repo=self.store.repo(self.id)
        self.store.git(repo,'reflog','expire','--expire=now','--all');self.store.git(repo,'gc','--prune=now')
        self.navigate('switch',branch='ideas/otra-idea');self.assertEqual(self.source.read_bytes(),b'BLENDER alternative D')
        paths=self.store.status(self.id,str(self.source))['branches']
        self.assertEqual({x['name'] for x in paths},{'main','ideas/otra-idea'})
        self.assertEqual(next(x['base'] for x in paths if x['name']=='ideas/otra-idea'),second['commit'])
        self.assertEqual(self.store.git(repo,'rev-parse','main').stdout.decode().strip(),third['commit'])
    def test_remote_roundtrip_preserves_every_idea_without_overwriting_main(self):
        first=self.store.snapshot(self.id,self.source,'A')
        self.source.write_bytes(b'BLENDER original route');main=self.store.snapshot(self.id,self.source,'B')
        self.navigate('explore',revision=first['commit'],label='Prueba')
        self.source.write_bytes(b'BLENDER idea route');idea=self.store.snapshot(self.id,self.source,'C')
        repo=self.store.repo(self.id);remote=self.root/'ideas.git';remote.mkdir();self.store.git(remote,'init','--bare','--initial-branch=main')
        self.store.git(repo,'remote','add','origin',str(remote))
        config=self.store.settings();config.update(server='https://example.invalid',username='test',token='test-only');core._write_json(self.store.settings_path,config)
        with patch.object(self.store,'_remote',return_value=repo):self.store.push(self.id)
        self.assertEqual(self.store.git(remote,'rev-parse','main').stdout.decode().strip(),main['commit'])
        self.assertEqual(self.store.git(remote,'rev-parse','ideas/prueba').stdout.decode().strip(),idea['commit'])
        with patch.object(self.store,'remote_url',return_value=(str(remote),['test','ideas'])),patch.object(self.store,'api',return_value=dict(default_branch='main')):
            cloned=self.store.clone_project('https://example.invalid/test/ideas.git')
        self.assertEqual({b['name'] for b in cloned['branches']},{'main','ideas/prueba'})
        self.assertEqual(Path(cloned['open_path']).read_bytes(),b'BLENDER original route')
        self.assertNotEqual(Path(cloned['open_path']),self.store.repo(cloned['repo_id'])/'model.blend')
        restored=self.store.prepare_navigation(cloned['repo_id'],cloned['open_path'],'switch',branch='ideas/prueba')
        self.assertEqual(Path(restored['restore_path']).read_bytes(),b'BLENDER idea route');Path(restored['restore_path']).unlink()

        self.source.write_bytes(b'BLENDER idea next');next_step=self.store.snapshot(self.id,self.source,'Next idea step')
        with patch.object(self.store,'_remote',return_value=repo):self.store.push(self.id)
        with patch.object(self.store,'_remote',return_value=self.store.repo(cloned['repo_id'])):self.store.pull(cloned['repo_id'])
        self.assertEqual(Path(cloned['open_path']).read_bytes(),b'BLENDER original route')
        history=self.store.status(cloned['repo_id'],cloned['open_path'],history_branch='ideas/prueba')
        self.assertEqual(history['commits'][0]['id'],next_step['commit'])

    def test_invalid_restore_and_identity_are_rejected(self):
        self.store.snapshot(self.id,self.source,'One')
        for value in ['HEAD','--help','../other','a'*40]:
            with self.assertRaises(core.VersionError):self.store.prepare_navigation(self.id,str(self.source),'explore',revision=value)
        self.assertEqual(len(self.store.status(self.id,str(self.source))['commits']),1)
        with self.assertRaises(core.VersionError):self.store.repo('../escape')
        with self.assertRaises(core.VersionError):self.store.identity('', 'bad')

class GiteaTests(unittest.TestCase):
    def setUp(self):
        self.folder=tempfile.TemporaryDirectory();self.addCleanup(self.folder.cleanup)
        self.store=core.Store(Path(self.folder.name)/'private');self.calls=[]
        calls=self.calls
        class Handler(BaseHTTPRequestHandler):
            def log_message(self,*args):pass
            def do_GET(self):
                calls.append((self.path,self.headers.get('Authorization'),None))
                if self.path=='/redirect/api/v1/user':
                    self.send_response(302);self.send_header('Location','/api/v1/user');self.end_headers();return
                if self.headers.get('Authorization')!='token test-secret-token':
                    self.send_response(401);self.end_headers();return
                self.send_response(200);self.end_headers()
                self.wfile.write(json.dumps(dict(login='valle',email='valle@example.invalid',default_branch='master')).encode())
            def do_POST(self):
                payload=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                calls.append((self.path,self.headers.get('Authorization'),payload))
                self.send_response(201);self.end_headers();self.wfile.write(json.dumps(dict(name=payload['name'])).encode())
        self.server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        threading.Thread(target=self.server.serve_forever,daemon=True).start()
        self.addCleanup(self.server.server_close);self.addCleanup(self.server.shutdown)
        self.url='http://127.0.0.1:'+str(self.server.server_port)
    def test_account_token_is_private_and_never_in_public_data_or_remote_url(self):
        result=self.store.connect(self.url,'test-secret-token')
        self.assertTrue(result['account']['has_token']);self.assertNotIn('test-secret-token',json.dumps(result))
        self.assertEqual(stat.S_IMODE(self.store.settings_path.stat().st_mode),0o600)
        repo_id='b'*32;source=Path(self.folder.name)/'scene.blend';source.write_bytes(b'BLENDER test')
        self.store.snapshot(repo_id,source,'Start');self.store.create_remote(repo_id,'scene')
        self.assertEqual(self.calls[-2][2],dict(name='scene',private=True,auto_init=False))
        config=self.store.git(self.store.repo(repo_id),'config','--get','remote.origin.url').stdout.decode()
        self.assertNotIn('test-secret-token',config);self.assertIn('/valle/scene.git',config)
        self.assertEqual(self.store.metadata(repo_id)['remote_branch'],'master')
        with self.assertRaises(core.VersionError):self.store.remote_url('https://another.example/valle/scene.git')
        self.store.forget();self.assertNotIn('test-secret-token',self.store.settings_path.read_text())
    def test_git_errors_redact_raw_and_encoded_credentials(self):
        self.store.connect(self.url,'test-secret-token')
        encoded=base64.b64encode(b'valle:test-secret-token').decode()
        failure=subprocess.CompletedProcess(['git'],1,b'',('test-secret-token Authorization: Basic '+encoded).encode())
        with patch.object(core.subprocess,'run',return_value=failure),self.assertRaises(core.VersionError) as caught:
            self.store.git(self.store.root,'push',authenticated=True)
        self.assertNotIn('test-secret-token',str(caught.exception));self.assertNotIn(encoded,str(caught.exception))

    def test_redirects_and_bad_tokens_do_not_replace_account(self):
        with self.assertRaises(core.VersionError):self.store.connect(self.url+'/redirect','test-secret-token')
        self.assertEqual(len(self.calls),1);self.assertFalse(self.store.settings_path.exists())
        with self.assertRaises(core.VersionError) as error:self.store.connect(self.url,'bad-secret')
        self.assertNotIn('bad-secret',str(error.exception));self.assertFalse(self.store.settings_path.exists())
    def test_http_requires_explicit_opt_in_and_url_cannot_contain_credentials(self):
        with self.assertRaises(core.VersionError):self.store.validate_server('http://gitea.lan')
        self.assertEqual(self.store.validate_server('http://gitea.lan',True),'http://gitea.lan')
        for url in ['https://user:secret@example.test','file:///tmp','https://example.test?token=abc','https://example.test\n']:
            if url.endswith('\n'):continue
            with self.assertRaises(core.VersionError):self.store.validate_server(url)

if __name__=='__main__':unittest.main()
