"""Request deadlines and bounded, atomic audio caching."""
from contextvars import ContextVar
from pathlib import Path
import os
import tempfile
import time
from threading import RLock

provider_deadline = ContextVar('provider_deadline', default=None)
cache_lock = RLock()


def provider_timeout():
    deadline = provider_deadline.get()
    remaining = 20 if deadline is None else deadline - time.monotonic()
    if remaining <= 0:
        raise TimeoutError('Tempo massimo provider raggiunto.')
    return (min(3, remaining), min(18, remaining))


def cache_audio(path, content, max_bytes=128*1024*1024):
    with cache_lock:
        _cache_audio(path, content, max_bytes)


def _cache_audio(path, content, max_bytes=128*1024*1024):
    path = Path(path)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as stream:
            temporary = stream.name
            stream.write(content)
        os.replace(temporary, path)
    finally:
        if temporary and os.path.exists(temporary):
            os.unlink(temporary)
    files = sorted((item for item in path.parent.iterdir() if item.suffix in {'.mp3', '.wav'} and item.is_file()),
                   key=lambda item: item.stat().st_mtime)
    total = sum(item.stat().st_size for item in files)
    count = len(files)
    for item in files:
        if count <= 200 and total <= max_bytes:
            break
        if item == path:
            continue
        try:
            size = item.stat().st_size
            item.unlink()
            total -= size
            count -= 1
        except OSError:
            pass
