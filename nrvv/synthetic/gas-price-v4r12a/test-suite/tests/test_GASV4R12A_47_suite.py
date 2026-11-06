'''GASV4R12A-18: an unacknowledged in-flight record expires after a tick timeout.'''
import app
import nrvv_env

STATION = 's1'
PRICE = 100
TIMEOUT = 3
ROUNDS = 3
SEEDS = (1, 2, 3)
TIMEOUT_KEYWORDS = ('timeout_ticks', 'ack_timeout_ticks', 'expiry_ticks', 'ack_timeout', 'timeout')


def _build(sim, timeout):
    '''Attach app.Server with the timeout configured; True if a timeout keyword was accepted.'''
    configured = []

    def factory(send):
        for name in TIMEOUT_KEYWORDS:
            try:
                server = app.Server(send_update=send, **{name: timeout})
            except TypeError:
                continue
            configured.append(name)
            return server
        return app.Server(send_update=send)

    sim.attach(factory)
    return bool(configured)


def _sends(sim):
    return [s for s in sim.sends if s.station == STATION]


def _last_status(sim):
    '''Status observed by the environment at the end of the latest tick (I3).'''
    return [q for q in sim.queries if q.station == STATION][-1].result


def _field(status, *names):
    for name in names:
        if isinstance(status, dict) and name in status:
            return status[name]
        if hasattr(status, name):
            return getattr(status, name)
    raise AssertionError('status has none of {}'.format(names))


def _in_flight_versions(status):
    if isinstance(status, dict):
        found = [v for k, v in status.items() if 'flight' in k]
    else:
        found = [getattr(status, k) for k in dir(status)
                 if 'flight' in k and not k.startswith('_') and not callable(getattr(status, k))]
    assert found, 'status exposes no in-flight records'
    return [r.get('version') if isinstance(r, dict) else getattr(r, 'version', r)
            for r in found[0]]


def _up_to_date(status):
    return _field(status, 'up_to_date', 'up_to_date_flag', 'is_up_to_date')


def _settle(sim, limit=50):
    '''Step until the station is up to date with nothing in flight.'''
    for _ in range(limit):
        status = _last_status(sim)
        if _up_to_date(status) and not _in_flight_versions(status):
            return
        sim.step()
    raise AssertionError('acknowledged version never left the in-flight state')


def test_unacked_version_expires_and_is_resent_once_per_timeout_interval():
    for seed in SEEDS:
        sim = nrvv_env.Simulation(seed, stations=(STATION,), stop_tick=1, fault_window=(0, 0),
                                  change_rate=0.0, max_delay=2)
        sim.source_schedule = {1: [(STATION, PRICE)]}
        configured = _build(sim, TIMEOUT)
        sim.set_reachable(STATION, False)  # updates are neither delivered nor acknowledged
        sim.step()
        assert len(_sends(sim)) == 1 and _sends(sim)[0].price == PRICE
        version = _sends(sim)[0].version
        assert _in_flight_versions(_last_status(sim)) == [version]
        expected = TIMEOUT if configured else None
        for _ in range(ROUNDS):
            before = len(_sends(sim))
            waited = 0
            while len(_sends(sim)) == before:
                sim.step()
                waited += 1
                assert _in_flight_versions(_last_status(sim)) == [version]
                assert waited <= (expected or 50), 'no expiry and resend within the timeout'
            if expected is None:
                expected = waited
            assert waited == expected, 'expiry after {} ticks, expected {}'.format(waited, expected)
            resend = _sends(sim)[-1]
            assert resend.tick == sim.now and resend.price == PRICE and resend.version == version
        sim.set_reachable(STATION, True)
        _settle(sim)
        assert sim.stations[STATION].displayed == PRICE
        stable = len(_sends(sim))
        sim.run(3 * expected)
        assert len(_sends(sim)) == stable, 'expiry continued after acknowledgement'
        status = _last_status(sim)
        assert _up_to_date(status) and _in_flight_versions(status) == []


def test_no_expiry_once_latest_version_is_acknowledged():
    for seed in SEEDS:
        sim = nrvv_env.Simulation(seed, stations=(STATION,), stop_tick=1, fault_window=(0, 0),
                                  change_rate=0.0, max_delay=2)
        sim.source_schedule = {1: [(STATION, PRICE)]}
        _build(sim, TIMEOUT)
        sim.set_reachable(STATION, False)
        sim.run(2 * TIMEOUT)
        assert len(_sends(sim)) >= 1
        sim.set_reachable(STATION, True)
        _settle(sim)
        assert sim.stations[STATION].displayed == PRICE
        stable = len(_sends(sim))
        sim.run(5 * TIMEOUT)
        assert len(_sends(sim)) == stable, 'expiry occurred after acknowledgement'
        status = _last_status(sim)
        assert _up_to_date(status) and _in_flight_versions(status) == []
