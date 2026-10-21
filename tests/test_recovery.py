"""Meaningful failure-boundary and persistence tests; no third-party dependencies."""
import json
from pathlib import Path
import tempfile
import threading
import unittest
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from engine import FileSystem
from app import make_server


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.fs = FileSystem(self.root)

    def tearDown(self):
        self.tmp.cleanup()

    def seed(self):
        self.fs.start('create', 'notes.txt', 'OS project')
        self.fs.run()

    def test_every_journaled_crash_boundary_for_all_operations(self):
        for op in ('create', 'edit', 'delete'):
            for boundary in range(6):
                with self.subTest(op=op, boundary=boundary):
                    self.fs.reset()
                    if op != 'create':
                        self.seed()
                    before = self.fs.state()['files']
                    self.fs.start(op, 'notes.txt', 'OS project completed')
                    expected = self.fs.control['pending']['after']
                    for _ in range(boundary):
                        self.fs.step()
                    self.fs.crash()
                    self.fs = FileSystem(self.root)  # fresh process-equivalent instance
                    self.fs.recover()
                    self.assertEqual(self.fs.check(), [])
                    if boundary >= 3:  # COMMIT has reached the journal
                        self.assertEqual(self.fs.disk, expected)
                    else:
                        self.assertEqual(self.fs.state()['files'], before)
                    # Recovery is repeat-safe on subsequent unrelated crashes.
                    self.fs.start('create', 'other.txt', 'later')
                    self.fs.crash()
                    self.fs.recover()
                    self.assertEqual(self.fs.check(), [])

    def test_no_journal_loses_consistency_after_data_write(self):
        self.fs.set_mode(False)
        self.seed()
        self.fs.start('edit', 'notes.txt', 'OS project completed')
        self.fs.step()
        self.assertTrue(self.fs.check())
        self.fs.crash()
        self.fs = FileSystem(self.root)
        self.fs.recover()
        self.assertTrue(self.fs.check())
        with self.assertRaises(ValueError):
            self.fs.start('create', 'new.txt', 'no')

    def test_recovery_uses_journal_not_pending_plan(self):
        self.seed()
        self.fs.start('edit', 'notes.txt', 'durable result')
        for _ in range(3): self.fs.step()
        self.fs.crash()
        self.fs.control['pending']['after'] = {'blocks': [], 'files': {}}
        self.fs.save_control()
        self.fs = FileSystem(self.root)
        self.fs.recover()
        self.assertEqual(self.fs.content('notes.txt'), b'durable result')

    def test_restart_without_clicking_crash(self):
        self.seed()
        self.fs.start('edit', 'notes.txt', 'restart')
        for _ in range(3): self.fs.step()
        self.fs = FileSystem(self.root)
        self.assertTrue(self.fs.control['crashed'])
        self.fs.recover()
        self.assertEqual(self.fs.content('notes.txt'), b'restart')

    def test_utf8_empty_full_and_validation(self):
        for name, content in [('empty.txt',''),('unicode.txt','Hello 🌱 മലയാളം')]:
            self.fs.start('create',name,content)
            self.fs.run()
            self.assertEqual(self.fs.content(name).decode(),content)
        self.assertEqual(self.fs.check(), [])
        for name in ('../host.txt','/etc/file','file with spaces',''):
            with self.assertRaises(ValueError): self.fs.start('create',name,'x')
        with self.assertRaises(ValueError): self.fs.start('create','huge','x'*1600)
        self.fs.reset()
        self.fs.start('create','full','x'*1536)
        self.fs.run()
        self.assertEqual(self.fs.state()['used'],48)
        with self.assertRaises(ValueError): self.fs.start('create','extra','x')
        self.fs.start('delete','full')
        self.fs.run()
        self.assertEqual(self.fs.state()['used'],0)

    def test_multiple_commits_recover_in_order(self):
        self.seed()
        for text in ('one','two','three'):
            self.fs.start('edit','notes.txt',text)
            for _ in range(4):self.fs.step()
            self.fs.crash()
            self.fs.recover()
            self.assertEqual(self.fs.content('notes.txt').decode(),text)
            self.assertEqual(self.fs.check(),[])


class HTTPTests(unittest.TestCase):
    def test_server_routes_and_persistence(self):
        with tempfile.TemporaryDirectory() as d:
            server = make_server(Path(d),0)
            worker = threading.Thread(target=server.serve_forever,daemon=True)
            worker.start()
            base = f'http://127.0.0.1:{server.server_port}'
            try:
                for path in ('/','/style.css','/app.js'):
                    with urlopen(base+path) as r:self.assertEqual(r.status,200)
                def post(path, data, origin=None):
                    headers={'Content-Type':'application/json'}
                    if origin: headers['Origin']=origin
                    return urlopen(Request(base+path,json.dumps(data).encode(),headers))
                with post('/api/start',{'op':'create','name':'demo.txt','content':'hello'}) as r:
                    self.assertIsNotNone(json.load(r)['pending'])
                with post('/api/run',{}) as r:
                    self.assertEqual(json.load(r)['files'][0]['content'],'hello')
                with self.assertRaises(HTTPError) as ctx:post('/api/reset',{'confirm':'RESET'},'https://elsewhere.example')
                self.assertEqual(ctx.exception.code,403)
                with self.assertRaises(HTTPError):post('/api/reset',{})
            finally:
                server.shutdown()
                server.server_close()
                worker.join()


if __name__ == '__main__':
    unittest.main()
