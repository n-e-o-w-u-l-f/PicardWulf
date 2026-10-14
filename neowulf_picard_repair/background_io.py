"""Bounded serial database ownership and queued Qt delivery.

No worker receives a Picard File or mutable Qt object. GUI callbacks only
consume JSON envelopes; database/media operations run on named workers.
"""
from concurrent.futures import Future, ThreadPoolExecutor
from collections import OrderedDict
import json
import queue
import threading


class DatabaseWorker:
    def __init__(self, factory, path, predecessor=None):
        self._factory = factory
        self._path = path
        self._predecessor = predecessor
        self._commands = queue.Queue(maxsize=32)
        self._ready = Future()
        self._closed = False
        self.thread = threading.Thread(target=self._run, name='PicardWulf-SQLite', daemon=True)
        self.thread.start()

    def _run(self):
        lease = None
        try:
            if self._predecessor is not None:
                if not self._predecessor.wait_stopped(30):
                    raise RuntimeError('previous writer has not acknowledged a durable flush')
            # The lease survives until all provider work and flushes finish.
            # A concurrent enable must not reset an old engine's running jobs.
            self._path.parent.mkdir(parents=True, exist_ok=True)
            lease = self._path.with_suffix(self._path.suffix + '.writer-lock').open('a+b')
            if __import__('os').name == 'nt':
                import msvcrt
                lease.seek(0)
                if not lease.read(1):
                    lease.write(b'0')
                    lease.flush()
                lease.seek(0)
                msvcrt.locking(lease.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(lease, fcntl.LOCK_EX | fcntl.LOCK_NB)
            store = self._factory()
            store.open_writer()
            self._ready.set_result(store)
        except Exception as exc:
            self._ready.set_exception(exc)
        try:
            while True:
                command = self._commands.get()
                if command is None:
                    break
                name, args, kwargs, receipt = command
                try:
                    store = self._ready.result()
                    receipt.set_result(getattr(store, name)(*args, **kwargs))
                except Exception as exc:
                    receipt.set_exception(exc)
        finally:
            if self._ready.done() and self._ready.exception() is None:
                store.close_writer()
            if lease is not None:
                lease.close()

    def __getattr__(self, name):
        if name.startswith('_'):
            raise AttributeError(name)
        def call(*args, **kwargs):
            if self._closed:
                raise RuntimeError('database worker closed')
            receipt = Future()
            self._commands.put((name, args, kwargs, receipt))
            return receipt.result()
        return call

    def close(self):
        self._closed = True
        self._commands.put(None)
        self.thread.join()


def create_gui_io(parent, engine):
    """Instantiate on Qt thread; queued signals carry immutable JSON only."""
    from PyQt6.QtCore import QObject, pyqtSignal, Qt

    class GuiIO(QObject):
        delivered = pyqtSignal(str, str)

        def __init__(self):
            super().__init__(parent)
            self.active = True
            self.pending = set()
            self.results = OrderedDict()
            self.recent = []
            self.backups = {}
            self.epoch = 0
            self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix='PicardWulf-Backup')
            self.delivered.connect(self.receive, Qt.ConnectionType.QueuedConnection)

        def receive(self, channel, envelope):
            if not self.active:
                return
            self.pending.discard(channel)
            message = json.loads(envelope)
            if channel == 'results':
                if message.get('epoch',self.epoch)!=self.epoch:return
                for key in message.get('keys', []):
                    if key not in message.get('value', {}):self.results.pop(key, None)
                for key, value in message.get('value', {}).items():
                    self.results[key] = value
                    self.results.move_to_end(key)
                while len(self.results) > 400:
                    self.results.popitem(last=False)
            elif channel == 'recent':
                self.recent = message.get('value', [])
            else:
                self.backups[channel] = message

        def deliver(self, channel, future, keys=(), epoch=None):
            try:
                message = {'value': future.result()}
            except Exception as exc:
                message = {'error': type(exc).__name__}
            if keys:message['keys']=keys
            if channel=='results':message['epoch']=self.epoch if epoch is None else epoch
            try:
                self.delivered.emit(channel, json.dumps(message, ensure_ascii=False))
            except RuntimeError:
                pass  # dialog/plugin was deleted while a worker was finishing

        def read(self, keys):
            if not self.active or 'results' in self.pending:
                return
            keys=tuple(keys)
            epoch=self.epoch
            receipt = engine.request_results(keys)
            if receipt is not None:
                self.pending.add('results')
                receipt.add_done_callback(lambda f: self.deliver('results', f, keys, epoch))

        def invalidate(self,key):
            self.epoch+=1
            self.results.pop(key,None)

        def read_recent(self):
            if not self.active or 'recent' in self.pending:
                return
            receipt = engine.request_recent()
            if receipt is not None:
                self.pending.add('recent')
                receipt.add_done_callback(lambda f: self.deliver('recent', f))

        def backup(self, token, path):
            # One media backup at a time; no unbounded executor submission.
            if not self.active or any(k.startswith('backup:') for k in self.pending):
                return False
            from .native_workflow import backup_envelope
            self.pending.add(token)
            receipt = self.executor.submit(backup_envelope, str(path))
            receipt.add_done_callback(lambda f: self.deliver(token, f))
            return True

        def stop(self):
            self.active = False
            self.results.clear()
            self.backups.clear()
            self.executor.shutdown(wait=False, cancel_futures=True)

    return GuiIO()
