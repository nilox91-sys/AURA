import os
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from qwen_service import QwenService, isolated_environment

FAKE='''import sys,json
print(json.dumps({'event':'ready','accelerated':True,'device':'test'}),flush=True)
for line in sys.stdin:
    request=json.loads(line)
    if request.get('text')=='error':
        print(json.dumps({'event':'error'}),flush=True)
    else:
        print(json.dumps({'event':'audio','audio':'test-frame'}),flush=True)
        print(json.dumps({'event':'done'}),flush=True)
'''

class ServiceTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.script=Path(self.temp.name)/'fake.py';self.script.write_text(FAKE)
        self.service=QwenService(Path(sys.executable),self.script,Path(self.temp.name))
        self.addCleanup(self.service.close)

    def test_warm_and_multiple_requests_reuse_one_process(self):
        self.service.warm();self.assertEqual(self.service.state,'ready')
        pid=self.service.process.pid
        for _ in range(2):
            self.assertEqual(list(self.service.stream({'text':'ok'})),[{'event':'audio','audio':'test-frame'}])
            self.assertEqual(self.service.process.pid,pid)
        self.assertTrue(self.service.accelerated)

    def test_cancel_releases_lock_and_next_request_recovers(self):
        chunks=self.service.stream({'text':'ok'});next(chunks);old=self.service.process
        chunks.close();self.assertIsNotNone(old.poll());self.assertFalse(self.service.lock.locked())
        self.assertEqual(len(list(self.service.stream({'text':'ok'}))),1)

    def test_bad_generation_does_not_poison_next_request(self):
        with self.assertRaises(RuntimeError):list(self.service.stream({'text':'error'}))
        self.assertFalse(self.service.lock.locked())
        self.assertEqual(len(list(self.service.stream({'text':'ok'}))),1)

    def test_unresponsive_worker_has_a_deadline(self):
        from queue import Queue
        self.service.events=Queue()
        with self.assertRaises(TimeoutError):self.service._next(time.monotonic())

    def test_environment_has_no_keys_and_keeps_windows_username(self):
        with patch.dict(os.environ,{'OPENROUTER_API_KEY':'private','HF_API_KEY':'private','USERNAME':'aura-test'}):
            env=isolated_environment(Path('model'))
        self.assertNotIn('OPENROUTER_API_KEY',env);self.assertNotIn('HF_API_KEY',env)
        self.assertEqual(env['HF_HUB_OFFLINE'],'1');self.assertEqual(env['USERNAME'],'aura-test')

if __name__=='__main__':unittest.main()
