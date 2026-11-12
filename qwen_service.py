"""One managed model per server. Readers have deadlines; cancellation frees the GPU."""
import atexit
import json
import os
from queue import Queue, Empty, Full
import subprocess
from threading import Lock, Thread
import time

MAX_FRAME = 4 * 1024 * 1024


def isolated_environment(model_dir):
    allowed = {'PATH','SYSTEMROOT','WINDIR','SYSTEMDRIVE','COMSPEC','PATHEXT','TEMP','TMP',
               'USERPROFILE','LOCALAPPDATA','APPDATA','PROGRAMFILES','PROGRAMFILES(X86)',
               'PROGRAMDATA','PROCESSOR_ARCHITECTURE','NUMBER_OF_PROCESSORS','USERNAME'}
    result = {key:value for key,value in os.environ.items() if key.upper() in allowed}
    result.update(PYTHONUTF8='1', HF_HUB_OFFLINE='1', TRANSFORMERS_OFFLINE='1',
                  HF_HUB_DISABLE_TELEMETRY='1', DO_NOT_TRACK='1', AURA_QWEN_MODEL_DIR=str(model_dir))
    return result


class QwenService:
    def __init__(self, python, worker, model_dir):
        self.python, self.worker, self.model_dir = python, worker, model_dir
        self.process = None
        self.events = None
        self.lock = Lock()
        self.state = 'cold'
        self.accelerated = False
        self.device = None
        atexit.register(self.close)

    @staticmethod
    def _read(process, events):
        try:
            while True:
                raw = process.stdout.readline(MAX_FRAME + 1)
                if not raw or len(raw)>MAX_FRAME or not raw.endswith(b'\n'):
                    break
                event = json.loads(raw)
                if not isinstance(event,dict):
                    break
                try:
                    events.put(event, timeout=5)
                except Full:
                    process.kill()
                    break
        except (OSError, ValueError):
            pass
        finally:
            try: events.put_nowait({'event':'dead'})
            except Full: pass

    def _next(self, deadline):
        try:
            event = self.events.get(timeout=max(.01, deadline-time.monotonic()))
        except Empty:
            raise TimeoutError('Qwen deadline') from None
        if event.get('event') in ('dead','error'):
            raise RuntimeError('Qwen unavailable')
        return event

    def _start(self):
        if self.process and self.process.poll() is None and self.state in ('ready','speaking'):
            return
        self.close()
        self.state = 'loading'
        flags = {'creationflags':subprocess.CREATE_NO_WINDOW} if os.name=='nt' else {}
        self.process = subprocess.Popen([str(self.python),str(self.worker)], stdin=subprocess.PIPE,
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, cwd=self.worker.parent.parent,
            env=isolated_environment(self.model_dir), **flags)
        self.events = Queue(maxsize=24)
        Thread(target=self._read,args=(self.process,self.events),daemon=True).start()
        event = self._next(time.monotonic()+180)
        if event.get('event')!='ready':
            raise RuntimeError('Qwen startup')
        self.accelerated, self.device = event.get('accelerated',False), event.get('device')
        self.state='ready'

    def warm(self):
        if not self.lock.acquire(blocking=False):
            return
        try:
            self._start()
        except (OSError, RuntimeError, TimeoutError):
            self.close()
            self.state='error'
        finally:
            self.lock.release()

    def stream(self, request):
        if not self.lock.acquire(timeout=185):
            raise TimeoutError('Qwen busy')
        complete = False
        try:
            self._start()
            self.state='speaking'
            self.process.stdin.write((json.dumps(request,ensure_ascii=True)+'\n').encode())
            self.process.stdin.flush()
            deadline=time.monotonic()+210
            while True:
                event=self._next(deadline)
                if event.get('event')=='done':
                    complete=True
                    self.state='ready'
                    return
                if event.get('event')!='audio' or not isinstance(event.get('audio'),str):
                    raise RuntimeError('Qwen frame')
                yield event
        finally:
            if not complete:
                self.close()
            self.lock.release()

    def close(self):
        process, self.process = self.process, None
        self.state='cold'
        if process:
            if process.poll() is None:
                process.kill()
            try: process.wait(timeout=5)
            except subprocess.TimeoutExpired: pass
            for pipe in (process.stdin, process.stdout):
                try: pipe.close()
                except (OSError, AttributeError): pass
