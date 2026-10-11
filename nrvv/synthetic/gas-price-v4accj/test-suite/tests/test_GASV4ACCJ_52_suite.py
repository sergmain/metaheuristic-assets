import app
from nrvv_env import Simulation

# GASV4ACCJ-48: a notification announcing a newly held desired price must be
# delivered within 60 seconds of the acknowledgement (GASV4ACCJ-52 criterion).
NOTIFY_WINDOW = 60
RUN_UNTIL = 2400
SEEDS = (1, 2, 3, 4, 5, 6)


def _make_server(ports):
    # Give the simulation the server side of the app, wired to the ports it provides.
    if hasattr(app, 'set_desired_price'):
        connect = getattr(app, 'connect', None)
        if connect is not None:
            connect(ports)
        return app
    for name in sorted(dir(app)):
        candidate = getattr(app, name)
        if name[:1].isupper() and isinstance(candidate, type) and hasattr(candidate, 'set_desired_price'):
            try:
                return candidate(ports)
            except TypeError:
                server = candidate()
                connect = getattr(server, 'connect', None)
                if connect is not None:
                    connect(ports)
                return server
    raise AssertionError('app provides no set_desired_price operation')


def _run(seed, **kwargs):
    sim = Simulation(seed, _make_server, **kwargs)
    sim.advance_to(RUN_UNTIL)
    return sim


def _held_price_acks(sim):
    # Acknowledgements (received at time T) stating a station holds the desired price
    # that was current at T. Only acks whose full 60 s window was simulated are used.
    cutoff = RUN_UNTIL - NOTIFY_WINDOW
    found = []
    for sid, station in sim.stations.items():
        for _change_time, price, converged_at in sim.convergence(sid):
            if converged_at is None:
                continue
            matches = [
                s for s in sim.sends
                if s.station_id == sid and s.price == price
                and s.outcome == 'delivered' and s.delivery_at == converged_at
            ]
            if not matches:
                continue
            ack_time = min(s.ack_at for s in matches)
            if ack_time > cutoff:
                continue
            desired_at_ack = [p for t, p in station.desired_history if t <= ack_time][-1]
            if desired_at_ack != price:
                continue
            found.append((sid, price, ack_time))
    return found


def _check_notices(sim, seed):
    acks = _held_price_acks(sim)
    for sid, price, ack_time in acks:
        notices = [
            n for n in sim.notifications
            if n.station_id == sid and n.price == price and n.ack_time == ack_time and n.accepted
        ]
        assert notices, (
            'seed %d: station %s price %s acknowledged at %d was never notified'
            % (seed, sid, price, ack_time)
        )
        delivered_at = min(n.time for n in notices)
        assert delivered_at - ack_time <= NOTIFY_WINDOW, (
            'seed %d: station %s price %s acknowledged at %d notified at %d (more than 60 s later)'
            % (seed, sid, price, ack_time, delivered_at)
        )
    return len(acks)


def test_notice_within_one_minute_of_ack_without_loss():
    checked = 0
    for seed in SEEDS:
        sim = _run(seed, loss_rate=0.0)
        checked += _check_notices(sim, seed)
    assert checked > 0, 'no held-price acknowledgement occurred to check'


def test_notice_within_one_minute_of_ack_with_loss_and_unreachable_stations():
    checked = 0
    for seed in SEEDS:
        sim = _run(seed)
        checked += _check_notices(sim, seed)
    assert checked > 0, 'no held-price acknowledgement occurred to check'


def test_notice_within_one_minute_with_more_stations():
    stations = ('A', 'B', 'C', 'D', 'E')
    checked = 0
    for seed in SEEDS:
        sim = _run(seed, station_ids=stations, loss_rate=0.0)
        checked += _check_notices(sim, seed)
    assert checked > 0, 'no held-price acknowledgement occurred to check'
