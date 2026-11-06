"""Price publishing server side: coalescing sends, ack matching, cost reports."""
from dataclasses import dataclass

LIFETIME = 100        # time after which an unacknowledged send may be resent
STALE_GRACE = 10      # ack lag beyond this counts as stale even without supersession
UNIT_COST = 1.0

_send = None
_clock = None
_keep = False
_stations = {}
_sends = {}
_order = []
_counter = 0
_unattributed = 0
_rate = 1


@dataclass
class StationState:
    latest_desired_price: object = None
    last_acknowledged_price: object = None
    settled: bool = True
    version: int = 0


class _Station:
    def __init__(self):
        self.price = None
        self.version = 0
        self.acked_price = None
        self.acked_version = 0
        self.open = set()
        self.cycle_first = None
        self.last_dispatch = 0
        self.backoff = LIFETIME
        self.pending_start = None
        self.superseded_start = None
        self.intervals = []

    @property
    def settled(self):
        return self.acked_version == self.version


class _Send:
    pass


def _now():
    return _clock() if _clock else 0


def reset():
    global _counter, _unattributed, _rate
    _stations.clear()
    _sends.clear()
    del _order[:]
    _counter = 0
    _unattributed = 0
    _rate = 1


def connect(send_to_station=None, current_time=None):
    global _send, _clock, _keep
    _send = send_to_station
    _clock = current_time
    if not _keep:
        reset()
    _keep = False


def restart():
    """Simulate a service restart: durable state is kept, ports are re-wired."""
    global _keep
    _keep = True


def configure(*args, **kwargs):
    global _rate
    if args:
        _rate = args[0]
    for v in kwargs.values():
        _rate = v


def _dispatch(station_id, st, original=None):
    global _counter
    _counter += 1
    r = _Send()
    r.send_id = "snd-%d" % _counter
    r.station_id = station_id
    r.price = st.price
    r.version = st.version
    r.time = _now()
    r.original = original
    r.acked = False
    r.outcome = None
    r.resolution_time = None
    _sends[r.send_id] = r
    _order.append(r)
    st.open.add(r.send_id)
    st.last_dispatch = r.time
    if original is None:
        st.cycle_first = r.send_id
        st.backoff = LIFETIME
    _send(station_id, r.price, r.send_id)
    return r


def submit_desired_price(station_id, price):
    if station_id is None or isinstance(price, bool) or not isinstance(price, (int, float)):
        return "rejected"
    st = _stations.get(station_id)
    if st is None:
        st = _stations[station_id] = _Station()
    if st.version and st.price == price and st.settled is False:
        return "accepted"
    if st.version and st.price == price:
        return "accepted"
    now = _now()
    if st.settled:
        st.pending_start = now
        st.superseded_start = None
    elif st.superseded_start is None:
        st.superseded_start = now
    st.price = price
    st.version += 1
    if not st.open:
        _dispatch(station_id, st)
    return "accepted"


def on_acknowledgement(station_id, send_id, reported_price):
    global _unattributed
    r = _sends.get(send_id)
    if r is None or r.station_id != station_id or r.acked:
        _unattributed += 1
        return
    st = _stations[station_id]
    now = _now()
    r.acked = True
    r.resolution_time = now
    st.open.discard(send_id)
    if r.version == st.version:
        was_settled = st.settled
        r.outcome = "redundant" if was_settled else "effective"
        st.acked_price = r.price
        st.acked_version = r.version
        if not was_settled:
            _close_period(st, now)
    else:
        r.outcome = "superseded"
        if r.version > st.acked_version:
            st.acked_price = r.price
            st.acked_version = r.version
    if not st.settled and not st.open:
        _dispatch(station_id, st)


def _close_period(st, now):
    start = st.pending_start if st.pending_start is not None else now
    stale_start = st.superseded_start if st.superseded_start is not None else start
    if st.superseded_start is not None or now - start > STALE_GRACE:
        st.intervals.append((stale_start, now))
    st.pending_start = None
    st.superseded_start = None


def reconcile():
    now = _now()
    for sid, st in list(_stations.items()):
        if st.settled or not st.open:
            continue
        if now - st.last_dispatch >= st.backoff:
            st.backoff *= 2
            _dispatch(sid, st, original=st.cycle_first)


tick = None  # reconcile is the single entry point for timed resends


def get_station_state(station_id):
    st = _stations.get(station_id)
    if st is None:
        return StationState()
    return StationState(st.price, st.acked_price, st.settled, st.version)


# ---- reports -----------------------------------------------------------

def _classify(r, now):
    if r.outcome is not None:
        return r.outcome
    return "failed" if now - r.time >= LIFETIME else "pending"


def _send_cost(r):
    return 1 * UNIT_COST


def _event(r, now):
    return {
        "send_id": r.send_id, "station_id": r.station_id, "price": r.price,
        "version": r.version, "product": "price_update",
        "dispatch_time": r.time, "resolution_time": r.resolution_time,
        "outcome": r.outcome, "class": _classify(r, now),
        "original_send_id": r.original, "cost": _send_cost(r),
    }


def _resend_flags(sends):
    seen = set()
    flags = {}
    for r in _order:
        flags[r.send_id] = r.station_id in seen
        seen.add(r.station_id)
    return flags


def _summary(sends):
    now = _now()
    flags = _resend_flags(sends)
    out = {"sends": len(sends), "resends": sum(1 for r in sends if flags[r.send_id])}
    classes = {"superseded": 0.0, "effective": 0.0, "redundant": 0.0, "failed": 0.0, "pending": 0.0}
    total = 0.0
    for r in sends:
        c = _send_cost(r)
        total += c
        classes[_classify(r, now)] += c
    out["total_cost"] = total
    for k, v in classes.items():
        out[k + "_cost"] = v
    return out


def get_sending_cost_report(station_id=None):
    now = _now()
    sends = [r for r in _order if station_id is None or r.station_id == station_id]
    out = _summary(sends)
    out["unattributed_acks"] = _unattributed
    per = {}
    for sid in sorted({r.station_id for r in sends}, key=str):
        s = _summary([r for r in sends if r.station_id == sid])
        per[sid] = {"sends": s["sends"], "resends": s["resends"], "total_cost": s["total_cost"]}
    out["per_station"] = per
    out["events"] = [_event(r, now) for r in sends]
    return out


def get_cost_records():
    now = _now()
    res = []
    for r in _order:
        e = _event(r, now)
        e.update({
            "station": r.station_id, "generation": r.version,
            "message_count": 1, "payload_size": len(str(r.price)),
            "unit_cost": UNIT_COST,
        })
        res.append(e)
    return res


def get_cost_report(station_id=None, station=None, batch=None, batch_id=None,
                    start=None, end=None, window=None, time_window=None,
                    from_time=None, to_time=None):
    now = _now()
    if window is None:
        window = time_window
    if window is not None:
        start, end = window
    if from_time is not None:
        start = from_time
    if to_time is not None:
        end = to_time
    stations = None
    for v in (station_id, station, batch, batch_id):
        if v is not None:
            stations = set(v) if isinstance(v, (list, tuple, set, frozenset)) else {v}
            break
    sends = [r for r in _order
             if (stations is None or r.station_id in stations)
             and (start is None or r.time >= start)
             and (end is None or r.time <= end)]
    s = _summary(sends)
    resolved = [r for r in sends if r.acked]
    effective = [r for r in sends if r.outcome == "effective"]
    latencies = [r.resolution_time - r.time for r in resolved]
    return {
        "provisional": any(not r.acked for r in sends),
        "sends": s["sends"],
        "retries": s["resends"],
        "total_cost": s["total_cost"],
        "cost_per_delivery": (s["total_cost"] / len(effective)) if effective else 0.0,
        "latency": (sum(latencies) / len(latencies)) if latencies else 0.0,
        "classification": {k: s[k + "_cost"] for k in
                           ("superseded", "effective", "redundant", "failed", "pending")},
    }


def get_stale_cost_report():
    now = _now()
    stations = {}
    tp = td = 0
    for sid, st in _stations.items():
        ivs = list(st.intervals)
        if not st.settled and st.pending_start is not None:
            start = st.pending_start
            if st.superseded_start is not None or now - start > STALE_GRACE:
                ivs.append((st.superseded_start if st.superseded_start is not None else start, now))
        items = [{"start": a, "end": b, "duration": b - a, "cost": (b - a) * _rate} for a, b in ivs]
        dur = sum(i["duration"] for i in items)
        stations[sid] = {"stale_periods": len(items), "stale_duration": dur,
                         "stale_cost": dur * _rate, "intervals": items}
        tp += len(items)
        td += dur
    return {"stations": stations,
            "total": {"stale_periods": tp, "stale_duration": td, "stale_cost": td * _rate}}
