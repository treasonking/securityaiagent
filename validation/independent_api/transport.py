"""Local Worker lifecycle, independent of the older fixture's server helper."""
from contextlib import contextmanager
import socket
import threading
import time

import uvicorn


@contextmanager
def worker_server(app, port=0):
    # Only the harness can reuse its own previous listener for a policy restart.
    with socket.socket() as listener:
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        listener.bind(('127.0.0.1', port))
        listener.listen(64)
        selected = listener.getsockname()[1]
        server = uvicorn.Server(uvicorn.Config(app, log_level='error', access_log=False))
        thread = threading.Thread(target=server.run, kwargs={'sockets': [listener]}, daemon=True)
        thread.start()
        try:
            deadline = time.monotonic() + 10
            while not server.started and thread.is_alive() and time.monotonic() < deadline:
                time.sleep(.01)
            if not server.started:
                raise RuntimeError('worker startup failed')
            yield selected
        finally:
            server.should_exit = True
            thread.join(timeout=10)
            if thread.is_alive():
                raise RuntimeError('worker shutdown failed')
