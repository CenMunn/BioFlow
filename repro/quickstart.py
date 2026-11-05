"""Isolated Linux development acceptance helpers, not a production deployment."""
import argparse
import getpass
import gzip
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import signal
import socket
import subprocess
import sys
import time
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def safe_path(path):
    path = Path(path).absolute()
    if '..' in path.parts or any(p.is_symlink() for p in (path, *path.parents)):
        raise ValueError('Traversal and symlinks are not allowed')
    return path


def initialize(workspace, username, password):
    workspace = safe_path(workspace)
    if not re.fullmatch(r'[A-Za-z0-9_][A-Za-z0-9_.-]{2,31}', username) or not 8 <= len(password) <= 128:
        raise ValueError('Username must be 3-32 safe characters; password must be 8-128 characters')
    if workspace.exists():
        raise FileExistsError('Workspace already exists; no credentials/state overwritten. Choose a fresh workspace')
    # Import existing account implementation, never migration scripts or gateway app.
    from backend.bioflow_platform.store import Store
    from backend.bioflow_platform.auth import create_user
    workspace.mkdir(parents=True, mode=0o700)
    store = Store(workspace / 'bioflow.sqlite3')
    create_user(store, username, password, 'developer')
    (workspace / 'initialized.json').write_text(json.dumps({'profile': 'light-software-only', 'username': username.lower()}), encoding='utf-8')
    return {'initialized': True, 'username': username.lower(), 'password': 'not displayed'}


def fixtures(workspace):
    folder = safe_path(workspace) / 'fixtures'
    safe_path(folder)
    folder.mkdir(parents=True, exist_ok=False)
    for mate in (1, 2):
        records = ''.join(f'@toy_{i:03d}/{mate}\n' + 'ACGT' * 25 + '\n+\n' + 'I' * 100 + '\n' for i in range(1, 17))
        with (folder / f'toy_R{mate}.fastq.gz').open('xb') as stream:
            stream.write(gzip.compress(records.encode('ascii'), mtime=0))
    (folder / 'matrix.tsv').write_text('sample_id\tfeature_id\tvalue\ntoy_A\tK00001\t4\ntoy_B\tK00001\t2\ntoy_A\tK00002\t0\ntoy_B\tK00002\t6\n', encoding='utf-8')
    (folder / 'matrix-contract.json').write_text(json.dumps({'kind': 'matrix', 'table': 'matrix.tsv', 'feature_type': 'KO', 'unit': 'counts', 'normalization': 'none'}), encoding='utf-8')
    (folder / 'README.txt').write_text('SYNTHETIC TOY SOFTWARE FIXTURE: no biological significance.\n16 repetitive paired reads, not an organism or disease cohort.\nQC warnings are expected; do not suppress them or use this for biological validation.\nMatrix values are invented counts for descriptive software checks only.\n', encoding='utf-8')
    return {'fixtures': str(folder), 'biological_significance': False}


def require_free_ports(ports):
    if len(set(ports)) != len(ports) or any(not 1024 <= p <= 65535 for p in ports):
        raise ValueError('Use distinct unprivileged ports 1024-65535')
    sockets = []
    try:
        for port in ports:
            sock = socket.socket()
            sockets.append(sock)
            sock.bind(('127.0.0.1', port))
    finally:
        for sock in sockets:
            sock.close()


def environment(workspace, analysis_port):
    # Explicitly drop inherited BioFlow settings and import-path injection.
    env = {k: v for k, v in os.environ.items() if not k.startswith(('BIOFLOW_', 'BIOLLM_', 'ARTICLE_WRITING_')) and k not in {'PYTHONPATH', 'PYTHONHOME'}}
    env.update(BIOFLOW_DATABASE=str(workspace / 'bioflow.sqlite3'),
               BIOFLOW_ANALYSIS_URL=f'http://127.0.0.1:{analysis_port}',
               BIOFLOW_ANALYSIS_ROOT=str(ROOT / 'BioLLM_RawDataAnalysis'),
               BIOFLOW_ALLOW_REGISTRATION='0', BIOFLOW_SKILL_CENTER_ENABLED='0',
               BIOFLOW_WRITING_URL='http://127.0.0.1:1', BIOFLOW_LITERATURE_URL='http://127.0.0.1:1',
               BIOLLM_STATE_ROOT=str(workspace / 'analysis'),
               BIOLLM_INPUT_ROOT=str(workspace / 'analysis/incoming'),
               BIOLLM_EXECUTION_ISOLATION='process_group', BIOLLM_AUTO_RETRY='0',
               BIOLLM_AUTO_RUN='0', BIOLLM_MAX_CONCURRENT_TASKS='1')
    return env


def commands(gateway_port, analysis_port):
    base = [sys.executable, '-m', 'uvicorn']
    return [(ROOT / 'BioLLM_RawDataAnalysis', base + ['backend.app.main:create_app', '--factory', '--host', '127.0.0.1', '--port', str(analysis_port)]),
            (ROOT, base + ['backend.bioflow_platform.app:app', '--host', '127.0.0.1', '--port', str(gateway_port)])]


def cleanup(children, grace_seconds=8):
    # Popen(start_new_session=True) gives each owned child its own PGID=PID.
    # Group lifetime is independent of its leader: never use poll()/wait() as
    # evidence that descendants are gone. Only these recorded groups are used.
    pending = {child.pid for child in children}
    for pgid in list(pending):
        try:
            os.killpg(pgid, signal.SIGTERM)
        except ProcessLookupError:
            pending.remove(pgid)
    deadline = time.monotonic() + grace_seconds
    while pending:
        for child in children:
            child.poll()  # Reap owned leaders without dropping their groups.
        for pgid in list(pending):
            try:
                os.killpg(pgid, 0)
            except ProcessLookupError:
                pending.remove(pgid)
        if not pending or time.monotonic() >= deadline:
            break
        time.sleep(min(0.05, max(0, deadline - time.monotonic())))
    for pgid in pending:
        try:
            os.killpg(pgid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    for child in children:
        child.wait(timeout=8)


def check():
    packages = ['fastapi', 'uvicorn', 'httpx', 'multipart', 'pydantic', 'yaml', 'numpy', 'pandas', 'matplotlib']
    missing = [name for name in packages if importlib.util.find_spec(name) is None]
    result = {'python': sys.version.split()[0], 'platform': sys.platform, 'missing_python_packages': missing,
              'nextflow': shutil.which('nextflow'), 'java': shutil.which('java'),
              'scope': 'software only; databases, writing, literature, AI and MAG not certified'}
    print(json.dumps(result, indent=2))
    return not missing and sys.version_info >= (3, 10) and sys.platform.startswith('linux')


def smoke(nextflow=False):
    if nextflow and (not shutil.which('nextflow') or not shutil.which('java')):
        raise RuntimeError('Nextflow and Java are required; no skipped test is counted as passed')
    command = [sys.executable, '-m', 'unittest', 'discover', '-s', 'repro/tests', '-v']
    subprocess.run(command, cwd=ROOT, check=True)
    if nextflow:
        env = environment(ROOT / 'runtime/reproduction', 18803)
        env['BIOFLOW_TEST_NEXTFLOW'] = '1'
        subprocess.run([sys.executable, '-m', 'pytest', '-q', 'backend/tests/test_typed_nextflow.py'],
                       cwd=ROOT / 'BioLLM_RawDataAnalysis', env=env, check=True)
    else:
        print('Nextflow NOT EXECUTED (request --nextflow explicitly). No biological pipeline tested.')


def start(workspace, gateway_port, analysis_port, isolated_development=False):
    if not isolated_development:
        raise ValueError('Requires --isolated-development in a fresh clone; process_group is not production isolation')
    if not sys.platform.startswith('linux'):
        raise RuntimeError('Launcher supports Linux only; check explains missing prerequisites')
    workspace = safe_path(workspace)
    if not workspace.is_relative_to(ROOT / 'runtime'):
        raise ValueError('Workspace must be inside this fresh clone runtime directory')
    if not (workspace / 'initialized.json').is_file() or not (workspace / 'bioflow.sqlite3').is_file():
        raise ValueError('Run init first in a fresh workspace')
    # Some existing assets write under source ROOT/runtime, not the selected state root.
    for path in (ROOT / 'runtime', ROOT / 'BioLLM_RawDataAnalysis/runtime'):
        safe_path(path)
        if path.exists() and any(not workspace.is_relative_to(p) for p in path.iterdir()):
            raise ValueError('Existing runtime outside workspace ancestry: use a fresh clone; never production')
    if not check():
        raise RuntimeError('Install documented dependencies in an isolated venv first')
    require_free_ports([gateway_port, analysis_port])
    lock = workspace / 'launcher.lock'
    with lock.open('x', encoding='utf-8') as handle:
        handle.write(str(os.getpid()))
    children = []
    previous = signal.signal(signal.SIGTERM, lambda *_: (_ for _ in ()).throw(KeyboardInterrupt()))
    try:
        for cwd, command in commands(gateway_port, analysis_port):
            children.append(subprocess.Popen(command, cwd=cwd, env=environment(workspace, analysis_port), start_new_session=True))
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        pending = {f'http://127.0.0.1:{gateway_port}/api/auth/me', f'http://127.0.0.1:{analysis_port}/api/health'}
        deadline = time.monotonic() + 45
        while pending:
            if any(child.poll() is not None for child in children):
                raise RuntimeError('Owned service exited during startup')
            if time.monotonic() > deadline:
                raise RuntimeError('Owned service readiness timeout')
            for url in list(pending):
                try:
                    with opener.open(url, timeout=1) as response:
                        if response.status == 200:
                            pending.remove(url)
                except OSError:
                    pass
            time.sleep(0.2)
        print(f'Ready: http://127.0.0.1:{gateway_port} (light software mode; AI retry off; MAG unavailable; auto-run off). Ctrl+C stops owned services.', flush=True)
        while all(child.poll() is None for child in children):
            time.sleep(0.5)
        raise RuntimeError('Owned service exited; stopping remaining owned services')
    except KeyboardInterrupt:
        print('Stopping owned development services')
    finally:
        cleanup(children)
        signal.signal(signal.SIGTERM, previous)
        lock.unlink()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['check', 'init', 'fixtures', 'start', 'smoke'])
    parser.add_argument('--workspace', type=Path, default=ROOT / 'runtime/reproduction')
    parser.add_argument('--username', default='researcher', help='New account name (init only)')
    parser.add_argument('--gateway-port', type=int, default=18800)
    parser.add_argument('--analysis-port', type=int, default=18803)
    parser.add_argument('--isolated-development', action='store_true', help='Acknowledge fresh clone and development-only process-group isolation')
    parser.add_argument('--nextflow', action='store_true', help='Run real opt-in Nextflow adapter tests, not biological consumers')
    args = parser.parse_args()
    try:
        if args.action == 'check':
            return 0 if check() else 1
        if args.action == 'init':
            password = os.environ.get('BIOFLOW_REPRO_PASSWORD') or getpass.getpass('New password (8-128 characters): ')
            print(json.dumps(initialize(args.workspace, args.username, password)))
        elif args.action == 'fixtures':
            print(json.dumps(fixtures(args.workspace)))
        elif args.action == 'start':
            start(args.workspace, args.gateway_port, args.analysis_port, args.isolated_development)
        else:
            smoke(args.nextflow)
        return 0
    except (OSError, ValueError, RuntimeError, ImportError, subprocess.CalledProcessError) as exc:
        print(f'ERROR: {exc}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
