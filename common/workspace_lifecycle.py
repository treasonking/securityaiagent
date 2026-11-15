"""Fail-closed, local single-Controller admission boundary for deployment.

No network, authority override or automatic stale-lock removal. A crashed holder
requires operator inspection before its marker is removed.
"""
from contextlib import contextmanager
import json
from pathlib import Path


class WorkspaceBusy(ValueError):
    pass


@contextmanager
def admission(root, *, deployment=False):
    root=Path(root)
    root.mkdir(parents=True,exist_ok=True)
    lock=root/'.admission.lock'
    try: lock.mkdir()
    except FileExistsError: raise WorkspaceBusy('WORKSPACE_BUSY') from None
    try:
        if not deployment and (root/'.deployment-fence.json').exists():
            raise WorkspaceBusy('WORKSPACE_MAINTENANCE')
        yield
    finally:
        lock.rmdir()


def idle(root):
    for path in (Path(root)/'jobs').glob('*.json'):
        value=json.loads(path.read_text(encoding='utf-8'))
        if value.get('status') not in {'COMPLETED','FAILED','CANCELLED','TIMED_OUT','INTERRUPTED','REJECTED'}:
            raise WorkspaceBusy('WORKSPACE_RUN_IN_PROGRESS')


@contextmanager
def fence(root, owner):
    root=Path(root)
    marker=root/'.deployment-fence.json'
    with admission(root,deployment=True):
        idle(root)
        try:
            with marker.open('x',encoding='utf-8') as stream:
                json.dump({'owner':owner},stream)
        except FileExistsError: raise WorkspaceBusy('WORKSPACE_MAINTENANCE') from None
    try: yield
    finally:
        # Do not remove another actor's marker or silently recover corrupt state.
        if json.loads(marker.read_text(encoding='utf-8'))!={'owner':owner}:
            raise WorkspaceBusy('WORKSPACE_FENCE_CHANGED')
        marker.unlink()
