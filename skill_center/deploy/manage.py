"""Operate only this independent application. No shared services are changed."""
import argparse
import hashlib
import json
import os
import secrets
import signal
import subprocess
import sys
import time
from pathlib import Path

os.umask(0o077)
PROJECT=Path(__file__).resolve().parents[1]
STORAGE=Path(os.getenv('SC_STORAGE',PROJECT/'storage')).resolve()
PID=STORAGE/'server.pid'
PORT=int(os.getenv('SC_PORT','18120'))


def initialize():
    STORAGE.mkdir(parents=True,exist_ok=True)
    config=STORAGE/'admin.json'
    if config.exists():
        print('Administrator already configured; credentials preserved.'); return
    username=os.getenv('SC_ADMIN_USERNAME','xh')
    password=secrets.token_urlsafe(18)
    salt=secrets.token_hex(16)
    hashed=hashlib.pbkdf2_hmac('sha256',password.encode(),bytes.fromhex(salt),600000).hex()
    config.write_text(json.dumps({'username':username,'salt':salt,'password_hash':hashed}),encoding='utf-8')
    access=STORAGE/'initial-access.txt'
    access.write_text(f'BioFlow Skill 中心独立管理员\n用户名：{username}\n密码：{password}\n访问：http://127.0.0.1:{PORT}/skills\n此账号仅用于 Skill 中心，与 SSH 登录无关。\n',encoding='utf-8')
    config.chmod(0o600); access.chmod(0o600)
    print('Administrator configured. Credentials: storage/initial-access.txt (0600).')


def running():
    if not PID.exists(): return None
    pid=int(PID.read_text())
    try:
        cmdline=Path(f'/proc/{pid}/cmdline').read_bytes().decode().replace('\0',' ')
        cwd=Path(f'/proc/{pid}/cwd').resolve()
        if cwd!=PROJECT or 'uvicorn backend.main:app' not in cmdline: return None
        if Path(f'/proc/{pid}/stat').read_text().split()[2]=='Z': return None
        return pid
    except (OSError,ValueError): return None


def start():
    initialize()
    if running(): print('Already running:',running()); return
    import socket
    with socket.socket() as sock:
        if sock.connect_ex(('127.0.0.1',PORT))==0: raise SystemExit('Port occupied; existing listener was not changed.')
    log=(STORAGE/'server.log').open('ab')
    env={**os.environ,'SC_STORAGE':str(STORAGE)}
    process=subprocess.Popen([sys.executable,'-m','uvicorn','backend.main:app','--host','127.0.0.1','--port',str(PORT),'--no-access-log'],cwd=PROJECT,env=env,stdin=subprocess.DEVNULL,stdout=log,stderr=log,start_new_session=True)
    PID.write_text(str(process.pid)); log.close()
    import urllib.request
    for _ in range(40):
        if process.poll() is not None: raise SystemExit('Startup failed. See storage/server.log.')
        try:
            with urllib.request.urlopen(f'http://127.0.0.1:{PORT}/api/v1/health',timeout=1) as response:
                print('Started',process.pid,response.read().decode()); return
        except OSError: time.sleep(.25)
    raise SystemExit('Health check timed out. See storage/server.log.')


def stop():
    pid=running()
    if not pid: print('No verified Skill Center process to stop.'); return
    os.kill(pid,signal.SIGTERM)
    for _ in range(40):
        if not running(): PID.unlink(missing_ok=True); print('Stopped',pid); return
        time.sleep(.25)
    raise SystemExit('Process did not stop; no unrelated process was terminated.')


def backup(target):
    if running(): raise SystemExit('Stop this application before taking a consistent backup.')
    import tarfile
    target=Path(target).resolve()
    if target.is_relative_to(STORAGE): raise SystemExit('Backup target must be outside storage.')
    target.parent.mkdir(parents=True,exist_ok=True)
    with tarfile.open(target,'w:gz') as archive: archive.add(STORAGE,arcname='storage',filter=lambda item:None if item.name.endswith(('server.pid','server.log')) else item)
    target.chmod(0o600); print('Backup saved:',target)


def restore(archive_path):
    if running(): raise SystemExit('Stop before restoring.')
    if STORAGE.exists() and any(STORAGE.iterdir()): raise SystemExit('Restore requires a separate, empty storage directory.')
    import tarfile
    with tarfile.open(archive_path,'r:gz') as archive:
        for item in archive.getmembers():
            p=Path(item.name)
            if p.is_absolute() or '..' in p.parts or item.issym() or item.islnk() or not (item.isfile() or item.isdir()) or not p.parts or p.parts[0]!='storage': raise SystemExit('Unsafe backup entry.')
        parent=STORAGE.parent
        # Archive uses storage as its only root; move it when restoring to a different name.
        import tempfile,shutil
        with tempfile.TemporaryDirectory(dir=parent) as temp:
            archive.extractall(temp)
            shutil.copytree(Path(temp)/'storage',STORAGE,dirs_exist_ok=True)
    print('Restored into:',STORAGE)


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('action',choices=['init','start','stop','status','backup','restore'])
    parser.add_argument('path',nargs='?')
    args=parser.parse_args()
    if args.action=='init': initialize()
    elif args.action=='start': start()
    elif args.action=='stop': stop()
    elif args.action=='status': print(json.dumps({'pid':running(),'port':PORT,'storage':str(STORAGE)}))
    elif args.action=='backup': backup(args.path or PROJECT/'backups'/f'skill-center-{int(time.time())}.tar.gz')
    elif args.action=='restore': restore(args.path)
