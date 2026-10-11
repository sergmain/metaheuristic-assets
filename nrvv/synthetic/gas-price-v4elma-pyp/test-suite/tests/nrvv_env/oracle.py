"""Test oracle over the simulation trace: checks R4-R7 and the D8 bound (GASV4ELMA-29)."""


def check(sim, convergence_bound=10.0):
    """Return a dict of violation lists; every list empty means the run passes.

    Pass convergence_bound=6.0 for the D8 check. Convergence needs the clock to reach
    the deadline, or the queue to be empty, otherwise RuntimeError is raised.
    """
    trace = sim.trace
    return {
        'r6_latest_price': _r6(trace),
        'r4_r5_repeat': _repeats(trace),
        'r7_unreachable_dispatch': _unreachable(trace),
        'sequence': _sequence(trace),
        'set_result': [r for r in trace if r.kind == 'set' and r.detail != 'Accepted'],
        'convergence': _convergence(sim, convergence_bound),
    }


def _r6(trace):
    latest, out = {}, []
    for r in trace:
        if r.kind == 'set':
            latest[r.station] = r.price
        elif r.kind == 'dispatch' and latest.get(r.station) != r.price:
            out.append(r)
    return out


def _repeats(trace):
    latest, last_sent, nonlatest_ack, out = {}, {}, {}, []
    for r in trace:
        if r.kind == 'set':
            latest[r.station] = r.price
        elif r.kind == 'ack':
            if latest.get(r.station) != r.price:
                nonlatest_ack[r.station] = True
        elif r.kind == 'dispatch':
            sid = r.station
            if sid in last_sent and last_sent[sid] == r.price and not nonlatest_ack.get(sid):
                out.append(r)
            last_sent[sid] = r.price
            nonlatest_ack[sid] = False
    return out


def _unreachable(trace):
    reach, out = {}, []
    for r in trace:
        if r.kind == 'reach':
            reach[r.station] = r.detail
        elif r.kind == 'dispatch' and not reach.get(r.station, True):
            out.append(r)
    return out


def _sequence(trace):
    count, out = {}, []
    for r in trace:
        if r.kind == 'dispatch':
            n = count.get(r.station, 0) + 1
            if r.seq != n:
                out.append(r)
            count[r.station] = n
    return out


def _convergence(sim, bound):
    start = sim.convergence_start
    if start is None:
        return []
    deadline = start + bound
    if sim.now < deadline and not sim.quiescent:
        raise RuntimeError('advance to t=%s (now=%s) before checking convergence' % (deadline, sim.now))
    latest = {}
    for r in sim.trace:
        if r.kind == 'set':
            latest[r.station] = r.price
    out = []
    for sid, price in latest.items():
        reachable_at_start, dropped = True, False
        for r in sim.trace:
            if r.kind != 'reach' or r.station != sid:
                continue
            if r.time <= start:
                reachable_at_start = r.detail
            elif r.time <= deadline and not r.detail:
                dropped = True
        if not reachable_at_start or dropped:
            continue  # convergence is conditional on reachability
        shown = None
        for r in sim.trace:
            if r.kind == 'display' and r.station == sid and r.time <= deadline:
                shown = r.price
        if shown != price:
            out.append({'station': sid, 'latest': price, 'displayed': shown, 'deadline': deadline})
    return out
