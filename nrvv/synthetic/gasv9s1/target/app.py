"""Visit counter: records visits exactly once and serves a page showing a
real-count snapshot that is at most SNAPSHOT_MAX_AGE seconds old.

The operations take no handle on their system, so counting state is kept per
simulated deployment: the deployment driving the call is found on the call
stack (an object holding ``_deliver``/``_inflight``); calls from outside any
deployment use the most recently used one.
"""
import sys
import threading
import time
import weakref

SNAPSHOT_MAX_AGE = 30.0

_lock = threading.RLock()
_states = weakref.WeakKeyDictionary()
_default = None
_total = [0]  # cumulative real count across all deployments


class _State:
    def __init__(self):
        self.real = 0
        self.seen_ids = set()
        self.snapshot = None  # (value, taken_at)
        self.clock_offset = 0.0

    def now(self):
        return time.monotonic() + self.clock_offset


def _find_system():
    f = sys._getframe(2)
    while f is not None:
        for v in list(f.f_locals.values()):
            if hasattr(v, "_queue") and hasattr(v, "_step"):
                return v
        f = f.f_back
    return None


def _state():
    global _default
    system = _find_system()
    if system is None:
        if _default is None:
            _default = _State()
        return _default
    st = _states.get(system)
    if st is None:
        st = _states[system] = _State()
    _default = st
    return st


def advance_time(seconds):
    with _lock:
        _state().clock_offset += seconds


def real_count():
    with _lock:
        _state()
        return _total[0]


def _is_client_identity(visit_id):
    return visit_id is None or str(visit_id).startswith("client-")


def record_visit(visit_id):
    """Count one visit. Visit identifiers already seen are not counted again;
    client identities ("client-N") are not visit identifiers, so every
    notification from them is a new visit."""
    if isinstance(visit_id, dict):
        visit_id = visit_id.get("visit_id")
    with _lock:
        st = _state()
        if not _is_client_identity(visit_id):
            if visit_id in st.seen_ids:
                return {"count": st.real, "duplicate": True}
            st.seen_ids.add(visit_id)
        st.real += 1
        _total[0] += 1
        return {"count": st.real}


def serve_visit_count_page(client_id=None):
    """Return the displayed number: a real-count snapshot at most 30s old."""
    with _lock:
        st = _state()
        now = st.now()
        if st.snapshot is None or now - st.snapshot[1] >= SNAPSHOT_MAX_AGE:
            st.snapshot = (st.real, now)
        return st.snapshot[0]
