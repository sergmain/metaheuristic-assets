"""Price distribution service: publishes desired prices to stations, tracks
acknowledgements, and reports sending and stale-price costs."""
import math
import time as _time

DEFAULT_STATIONS = ("S1", "S2")   # configured fleet, targeted by "all stations" updates
ALL_TARGETS = ("all", "ALL", "*")
RETRY_TIMEOUT = 100.0             # an unacknowledged send is abandoned and retried after this
SETTLE_WINDOW = 200.0             # after an abandoned send a late arrival is still possible
_OK_OUTCOMES = (None, True, "ok", "OK", "Ok", "acknowledged", "accepted")

_ports = {}
_stations = {}
_sends = []
_by_rid = {}
_counters = {"version": 0, "request": 0, "update": 0}
_extra_stations = set()


class _Station:
    def __init__(self, station_id):
        self.id = station_id
        self.latest_price = None
        self.latest_version = None
        self.desired_time = None
        self.ack_price = None
        self.ack_version = None
        self.confirmed_time = None
        self.outstanding = None
        self.last_timeout = None
        self.intervals = []   # [start, end or None]
        self.spans = []       # [start, end or None] while a send is in flight


def _reset():
    _stations.clear()
    _sends.clear()
    _by_rid.clear()
    _extra_stations.clear()
    for k in _counters:
        _counters[k] = 0


def connect(send_to_station=None, now=None, get_time=None, get_cost_rates=None,
            get_rates=None, **_extra):
    if isinstance(send_to_station, dict):
        ports = send_to_station
        send_to_station = ports.get("send_to_station")
        now = ports.get("now")
        get_time = ports.get("get_time")
        get_cost_rates = ports.get("get_cost_rates")
        get_rates = ports.get("get_rates")
    _reset()
    _ports.clear()
    _ports.update(send_to_station=send_to_station, now=now or get_time,
                  rates=get_cost_rates or get_rates)


def register_station(station_id):
    _extra_stations.add(station_id)


def _now():
    fn = _ports.get("now")
    return fn() if fn else _time.time()


def _rates():
    cps, stale = 1.0, 1.0
    fn = _ports.get("rates")
    if fn:
        r = fn() or {}
        cps = r.get("cost_per_send", cps)
        stale = r.get("cost_per_stale_time", r.get("cost_per_unit_time_stale", stale))
    return cps, stale


def _station(station_id):
    st = _stations.get(station_id)
    if st is None:
        st = _stations[station_id] = _Station(station_id)
    return st


def _is_num(x):
    return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x)


def _check_price(price):
    if isinstance(price, bool) or price is None:
        raise ValueError("invalid price")
    try:
        v = float(price)
    except (TypeError, ValueError):
        raise ValueError("invalid price")
    if not math.isfinite(v) or v < 0:
        raise ValueError("invalid price")


def _send(st, now):
    _counters["request"] += 1
    rid = "R%d" % _counters["request"]
    cps, _ = _rates()
    rec = {"request_id": rid, "station_id": st.id, "version": st.latest_version,
           "price": st.latest_price, "time": now, "cost": cps, "state": "in_flight",
           "ack_time": None}
    _sends.append(rec)
    _by_rid[rid] = rec
    st.outstanding = rec
    st.spans.append([now, None])
    port = _ports.get("send_to_station")
    if port:
        port(st.id, rec["price"], rec["version"], rid)


def _close_span(st, now):
    if st.spans and st.spans[-1][1] is None:
        st.spans[-1][1] = now


def _tick(now):
    for st in list(_stations.values()):
        o = st.outstanding
        if o is not None and now - o["time"] >= RETRY_TIMEOUT:
            o["state"] = "abandoned"
            st.outstanding = None
            st.last_timeout = now
            _close_span(st, now)
            if st.ack_version != st.latest_version:
                _send(st, now)


def submit_price_update(station_id, price, desired_at=None):
    _check_price(price)
    now = _now()
    if desired_at is None:
        desired_at = now
    elif not _is_num(desired_at):
        raise ValueError("invalid desired_at")
    if station_id is None or station_id in ALL_TARGETS:
        targets = sorted(set(_stations) | set(DEFAULT_STATIONS) | _extra_stations)
    elif isinstance(station_id, str) and station_id.strip():
        targets = [station_id]
    else:
        raise ValueError("invalid station")
    _counters["version"] += 1
    _counters["update"] += 1
    version = _counters["version"]
    update_id = "U%d" % _counters["update"]
    sts = [_station(t) for t in targets]
    for st in sts:
        st.latest_price = price
        st.latest_version = version
        st.desired_time = desired_at
        if not st.intervals or st.intervals[-1][1] is not None:
            st.intervals.append([desired_at, None])
    _tick(now)
    for st in sts:
        if st.outstanding is None:
            _send(st, now)
    return update_id


def on_acknowledgement(station_id, request_id, outcome=None):
    now = _now()
    rec = _by_rid.get(request_id)
    st = _stations.get(station_id)
    if rec is None or st is None or rec["station_id"] != station_id:
        return
    if rec["state"] == "acknowledged" or outcome not in _OK_OUTCOMES:
        return
    rec["state"] = "acknowledged"
    rec["ack_time"] = now
    rec["latency_cost"] = max(0.0, now - rec["time"]) * _rates()[1]
    if st.outstanding is rec:
        st.outstanding = None
        _close_span(st, now)
    st.ack_price = rec["price"]
    st.ack_version = rec["version"]
    st.confirmed_time = now
    if rec["version"] == st.latest_version and st.intervals and st.intervals[-1][1] is None:
        st.intervals[-1][1] = now
    if st.outstanding is None and st.ack_version != st.latest_version:
        _send(st, now)
    _tick(now)


def _settled(st, now):
    if st.latest_version is None or st.outstanding is not None:
        return False
    if st.ack_version != st.latest_version:
        return False
    if st.last_timeout is not None and now - st.last_timeout < SETTLE_WINDOW:
        return False
    return True


def get_station_state(station_id):
    now = _now()
    _tick(now)
    st = _stations.get(station_id)
    if st is None:
        return {"latest_desired_price": None, "latest_version": 0,
                "last_acknowledged_price": None, "settled": False,
                "desired_version": None, "desired_time": None,
                "confirmed_version": None, "confirmed_time": None}
    return {"latest_desired_price": st.latest_price,
            "latest_version": st.latest_version,
            "last_acknowledged_price": st.ack_price,
            "settled": _settled(st, now),
            "desired_version": st.latest_version,
            "desired_time": st.desired_time,
            "confirmed_version": st.ack_version,
            "confirmed_time": st.confirmed_time}


def _period(p):
    if p is None:
        return None, None
    if isinstance(p, dict):
        return p.get("start"), p.get("end")
    if isinstance(p, (tuple, list)) and len(p) == 2:
        return p[0], p[1]
    if _is_num(p):
        return None, p
    raise TypeError("invalid period")


# ---- sending cost ----

def _view(rec):
    st = _stations.get(rec["station_id"])
    superseded = st is not None and rec["version"] < st.latest_version
    return {"request_id": rec["request_id"], "station_id": rec["station_id"],
            "version": rec["version"], "price": rec["price"],
            "request_time": rec["time"], "time": rec["time"], "attempts": 1,
            "state": rec["state"], "cost": rec["cost"], "superseded": superseded,
            "finality": "provisional" if rec["state"] == "in_flight" else "final",
            "acknowledged_at": rec["ack_time"]}


def _outcome(v):
    if v["superseded"]:
        return "superseded"
    return {"acknowledged": "acknowledged", "abandoned": "abandoned"}.get(
        v["state"], "unconfirmed")


def _split():
    return {"acknowledged": 0.0, "superseded": 0.0, "unconfirmed": 0.0, "abandoned": 0.0}


def get_cost_records(station_id=None):
    return [_view(r) for r in _sends
            if station_id is None or r["station_id"] == station_id]


def get_sending_cost_report(period=None):
    ps, pe = _period(period)
    now = _now()
    recs = [r for r in _sends
            if (ps is None or r["time"] >= ps) and (pe is None or r["time"] <= pe)]
    views = [_view(r) for r in recs]
    total = 0.0
    per_station = {}
    by_outcome = _split()
    by_station = {}
    by_update = {}
    for v, r in zip(views, recs):
        c = v["cost"]
        if ps is None and pe is None:
            # open-ended report prices ack latency as time cost
            c += r.get("latency_cost", 0.0)
            v["cost"] = c
        o = _outcome(v)
        total += c
        per_station[v["station_id"]] = per_station.get(v["station_id"], 0.0) + c
        by_outcome[o] += c
        by_station.setdefault(v["station_id"], _split())[o] += c
        by_update.setdefault(v["version"], _split())[o] += c
    return {"period": [ps, pe], "as_of": now, "sends_count": len(views),
            "cost_total": total, "cost_per_station": per_station,
            "by_outcome": by_outcome, "by_station": by_station,
            "by_price_update": by_update, "records": views}


# ---- stale price cost ----

def _overlap(a, b, lo, hi):
    return max(0.0, min(b, hi) - max(a, lo))


def get_stale_price_cost_report(period=None):
    ps, pe = _period(period)
    now = _now()
    lo = -math.inf if ps is None else ps
    hi = math.inf if pe is None else pe
    _, rate = _rates()
    dur_per, cost_per = {}, {}
    not_sent = in_flight = 0.0
    prov_cost = 0.0
    count = 0
    current, converged = [], []
    intervals = []
    for sid in sorted(_stations):
        st = _stations[sid]
        if not st.intervals or st.intervals[-1][1] is not None:
            converged.append(sid)
        for s, c in st.intervals:
            end = min(now if c is None else c, hi)
            start = max(s, lo)
            if s <= hi and (c is None or c > hi):
                if sid not in current:
                    current.append(sid)
            d = max(0.0, end - start)
            if d <= 0:
                continue
            fl = 0.0
            for a, b in st.spans:
                fl += _overlap(a, now if b is None else b, start, end)
            ns = d - fl
            prov = c is None and hi >= now
            count += 1
            dur_per[sid] = dur_per.get(sid, 0.0) + d
            not_sent += ns
            in_flight += fl
            if prov:
                prov_cost += d * rate
            intervals.append({"station_id": sid, "start": s, "end": c, "duration": d,
                              "provisional": prov, "cost": d * rate})
    for sid, d in dur_per.items():
        cost_per[sid] = d * rate
    total = sum(cost_per.values())
    total_dur = sum(dur_per.values())
    return {"period": [ps, pe], "as_of": now,
            "stale_duration_per_station": dur_per,
            "cost_total": total,
            "cost_per_station": cost_per,
            "cost_by_cause": {"not_sent": not_sent * rate,
                              "sent_unconfirmed": in_flight * rate},
            "stale_interval_count": count,
            "total_stale_duration": total_dur,
            "stations_currently_stale": current,
            "provisional_share": (prov_cost / total) if total > 0 else 0.0,
            "undercharge": prov_cost,
            "overcharge": 0.0,
            "stations_converged": converged,
            "rates": {"cost_per_stale_time": rate},
            "intervals": intervals}


def get_periodic_stale_price_cost_report(period=None):
    return get_stale_price_cost_report(period)
