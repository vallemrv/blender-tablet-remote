"""Install a verified official Git LFS binary privately on this Linux x86_64 host."""
import hashlib,io,os,platform,tarfile,urllib.request
from pathlib import Path
VERSION='3.8.0'
SHA256='e455e00f15d9b95661b8d53498ffb0c3367962cf1ec73c31ab7369516cd6ab8d'
if platform.system()!='Linux' or platform.machine() not in ('x86_64','amd64'):
    raise SystemExit('Instala Git LFS para tu plataforma desde https://git-lfs.com')
url=f'https://github.com/git-lfs/git-lfs/releases/download/v{VERSION}/git-lfs-linux-amd64-v{VERSION}.tar.gz'
with urllib.request.urlopen(url,timeout=60) as r:data=r.read(100*1024*1024)
if hashlib.sha256(data).hexdigest()!=SHA256:raise SystemExit('Checksum de Git LFS no válido')
root=Path.home()/'.local/share/blender-tablet-remote/bin';root.mkdir(parents=True,exist_ok=True)
with tarfile.open(fileobj=io.BytesIO(data),mode='r:gz') as archive:
    member=next(m for m in archive.getmembers() if m.isfile() and Path(m.name).name=='git-lfs')
    target=root/'git-lfs';target.write_bytes(archive.extractfile(member).read());target.chmod(0o755)
print(target)
