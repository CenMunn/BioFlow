import json
import gc
from contextlib import closing
import contextlib
import io
import os
from pathlib import Path
import socket
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import quickstart as q


class QuickstartTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.addCleanup(gc.collect)
        self.work = Path(self.tmp.name) / 'workspace'

    def test_fixtures_are_deterministic_labeled_and_never_overwritten(self):
        q.fixtures(self.work)
        first = (self.work / 'fixtures/toy_R1.fastq.gz').read_bytes()
        other = Path(self.tmp.name) / 'other'
        q.fixtures(other)
        self.assertEqual(first, (other / 'fixtures/toy_R1.fastq.gz').read_bytes())
        self.assertIn('no biological significance', (self.work / 'fixtures/README.txt').read_text())
        self.assertEqual((self.work / 'fixtures/matrix.tsv').read_text().splitlines()[0], 'sample_id\tfeature_id\tvalue')
        with self.assertRaises(FileExistsError):
            q.fixtures(self.work)

    def test_initialization_requires_password_and_refuses_existing_workspace(self):
        with self.assertRaises(ValueError):
            q.initialize(self.work, 'researcher', '')
        self.assertFalse(self.work.exists())
        self.work.mkdir()
        (self.work / 'keep').write_text('keep')
        with self.assertRaises(FileExistsError):
            q.initialize(self.work, 'researcher', 'long-enough-password')
        self.assertEqual((self.work / 'keep').read_text(), 'keep')

    def test_new_account_uses_existing_auth_and_cannot_be_reset(self):
        try:
            from backend.bioflow_platform.store import Store
            from backend.bioflow_platform.auth import verify_password
        except ImportError:
            self.skipTest('Existing account module requires documented FastAPI dependency')
        result = q.initialize(self.work, 'researcher', 'unique-test-password')
        self.assertNotIn('unique-test-password', json.dumps(result))
        with closing(Store(self.work / 'bioflow.sqlite3').connect()) as db:
            stored = db.execute('SELECT password_hash FROM users').fetchone()[0]
        self.assertTrue(verify_password('unique-test-password', stored))
        with self.assertRaises(FileExistsError):
            q.initialize(self.work, 'researcher', 'replacement-password')
        with closing(Store(self.work / 'bioflow.sqlite3').connect()) as db:
            self.assertEqual(db.execute('SELECT password_hash FROM users').fetchone()[0], stored)

    def test_start_requires_explicit_development_consent(self):
        with self.assertRaisesRegex(ValueError, 'isolated-development'):
            q.start(self.work, 18800, 18803)

    def test_missing_dependencies_explain_failure(self):
        output = io.StringIO()
        with patch.object(q.importlib.util, 'find_spec', return_value=None), contextlib.redirect_stdout(output):
            self.assertFalse(q.check())
        self.assertIn('uvicorn', json.loads(output.getvalue())['missing_python_packages'])

    def test_busy_port_refused_without_touching_listener(self):
        with socket.socket() as listener:
            listener.bind(('127.0.0.1', 0))
            listener.listen()
            with self.assertRaises(OSError):
                q.require_free_ports([listener.getsockname()[1]])
            self.assertNotEqual(listener.fileno(), -1)

    def test_environment_does_not_inherit_production_configuration(self):
        with patch.dict(q.os.environ, {'BIOFLOW_DATABASE': '/production/db', 'BIOLLM_AUTO_RETRY': '1', 'PYTHONPATH': '/production/modules'}):
            env = q.environment(self.work, 18803)
        self.assertEqual(env['BIOFLOW_DATABASE'], str(self.work / 'bioflow.sqlite3'))
        self.assertEqual(env['BIOLLM_AUTO_RETRY'], '0')
        self.assertEqual(env['BIOLLM_AUTO_RUN'], '0')
        self.assertEqual(env['BIOLLM_MAX_CONCURRENT_TASKS'], '1')
        self.assertNotIn('PYTHONPATH', env)

    def test_child_commands_have_correct_cwd_and_loopback(self):
        commands = q.commands(18800, 18803)
        self.assertEqual(commands[0][0], q.ROOT / 'BioLLM_RawDataAnalysis')
        self.assertEqual(commands[1][0], q.ROOT)
        for cwd, command in commands:
            self.assertIn('127.0.0.1', command)
            self.assertNotIn('0.0.0.0', command)

    def test_missing_nextflow_fails_not_skips(self):
        with patch.object(q.shutil, 'which', return_value=None):
            with self.assertRaisesRegex(RuntimeError, 'Nextflow'):
                q.smoke(True)

    def test_cleanup_stops_owned_descendant_even_after_leader_exit(self):
        class Child:
            pid = 999999
            def poll(self): return 0
            def wait(self, timeout): return 0
        groups = {999999: True, 888888: True}
        def killpg(pgid, sig):
            if not groups[pgid]:
                raise ProcessLookupError()
            if sig == signal.SIGTERM:
                groups[pgid] = False
        with patch.object(q.os, 'killpg', side_effect=killpg, create=True):
            q.cleanup([Child()], grace_seconds=0)
        self.assertFalse(groups[999999])
        self.assertTrue(groups[888888], 'Unowned group must remain untouched')

    def test_cleanup_escalates_surviving_group_independently_of_leader_wait(self):
        class Child:
            pid = 999999
            def poll(self): return 0
            def wait(self, timeout): return 0
        alive = {999999}
        def killpg(pgid, sig):
            if pgid not in alive:
                raise ProcessLookupError()
            if sig == signal.SIGKILL:
                alive.remove(pgid)
        # Windows has no SIGKILL/killpg, but can exercise the owned-group logic
        # against this narrow OS-boundary fake; actual signals are Linux-gated.
        with patch.object(q.signal, 'SIGKILL', 9, create=True), patch.object(q.os, 'killpg', side_effect=killpg, create=True):
            q.cleanup([Child()], grace_seconds=0)
        self.assertEqual(alive, set(), 'TERM-resistant owned descendant must receive KILL')

    @unittest.skipUnless(sys.platform.startswith('linux') and Path('/proc').is_dir(), 'Real owned-process-group lifecycle requires Linux /proc')
    def test_real_cleanup_after_leader_exit_and_with_term_resistant_descendant(self):
        # Only groups created by this test are ever signaled; /proc checks liveness,
        # not process discovery. Zombies count as stopped (not executable work).
        def running(pid):
            try:
                return Path(f'/proc/{pid}/stat').read_text().split(') ', 1)[1][0] != 'Z'
            except FileNotFoundError:
                return False
        unrelated = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)'], start_new_session=True)
        self.addCleanup(lambda: (unrelated.kill(), unrelated.wait()) if unrelated.poll() is None else None)
        for resistant in (False, True):
            with self.subTest(term_resistant=resistant):
                marker = Path(self.tmp.name) / f'child-{resistant}.ready'
                descendant_code = ('import signal,time; from pathlib import Path; '
                                   + ('signal.signal(signal.SIGTERM, signal.SIG_IGN); ' if resistant else '')
                                   + f'Path({str(marker)!r}).write_text("ready"); time.sleep(30)')
                leader_code = ('import subprocess,sys; p=subprocess.Popen([sys.executable,"-c",sys.argv[1]]); '
                               'print(p.pid,flush=True)')
                leader = subprocess.Popen([sys.executable, '-c', leader_code, descendant_code],
                                          start_new_session=True, stdout=subprocess.PIPE, text=True)
                descendant = None
                try:
                    descendant = int(leader.stdout.readline())
                    leader.wait(timeout=5)
                    deadline = time.monotonic() + 5
                    while not marker.exists() and time.monotonic() < deadline:
                        time.sleep(0.02)
                    self.assertTrue(marker.exists(), 'Descendant must install its TERM handler before cleanup')
                    q.cleanup([leader], grace_seconds=0.1)
                    deadline = time.monotonic() + 3
                    while running(descendant) and time.monotonic() < deadline:
                        time.sleep(0.02)
                    self.assertFalse(running(descendant))
                    self.assertIsNone(unrelated.poll())
                finally:
                    try:
                        os.killpg(leader.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                    leader.wait(timeout=5)
                    leader.stdout.close()


if __name__ == '__main__':
    unittest.main()
