import app
from nrvv_env import Simulation

STATION = 's1'
SEEDS = (1, 2, 3, 4, 5)
_MISSING = object()


def _field(obj, *names):
    for name in names:
        if isinstance(obj, dict) and name in obj:
            return obj[name]
        if not isinstance(obj, dict) and hasattr(obj, name):
            return getattr(obj, name)
    return _MISSING


def _new_sim(seed, loss=0.0, fault_window=(0, 0)):
    sim = Simulation(seed, stations=(STATION,), stop_tick=20, fault_window=fault_window,
                     loss=loss, change_rate=0.0)
    sim.attach(lambda send: app.Server(send_update=send))
    return sim


def _assert_success(outcome):
    assert outcome is not None and outcome is not False, 'refused: {!r}'.format(outcome)
    accepted = _field(outcome, 'accepted', 'success', 'ok')
    if accepted is not _MISSING:
        assert accepted is True, 'not accepted: {!r}'.format(outcome)
    error = _field(outcome, 'error', 'errors', 'refusal', 'reason')
    assert error in (_MISSING, None, '', []), 'errored or refused: {!r}'.format(outcome)
    status = _field(outcome, 'status', 'outcome')
    if isinstance(status, str):
        assert status.lower() in ('accepted', 'ok', 'success', 'succeeded'), \
            'non-success status: {!r}'.format(outcome)


def _version_of(outcome):
    if isinstance(outcome, (int, str)) and not isinstance(outcome, bool):
        return outcome
    return _field(outcome, 'version', 'desired_version')


def _assert_first_unacknowledged(sim):
    assert sim.acks == [], 'first update was acknowledged; scenario invalid'
    assert sim.stations[STATION].displayed is None


def test_second_price_accepted_while_first_is_unacknowledged():
    for seed in SEEDS:
        sim = _new_sim(seed, loss=1.0, fault_window=(0, 10))
        _assert_success(sim.server.accept_desired_price(STATION, 100))
        sim.run(3)
        _assert_first_unacknowledged(sim)
        _assert_success(sim.server.accept_desired_price(STATION, 200))


def test_second_accept_assigns_new_desired_version():
    for seed in SEEDS:
        sim = _new_sim(seed, loss=1.0, fault_window=(0, 10))
        first = sim.server.accept_desired_price(STATION, 100)
        _assert_success(first)
        sim.run(2)
        _assert_first_unacknowledged(sim)
        second = sim.server.accept_desired_price(STATION, 200)
        _assert_success(second)
        v1 = _version_of(first)
        v2 = _version_of(second)
        assert v2 is not None and v2 is not _MISSING, 'no desired version in outcome'
        if v1 is not _MISSING:
            assert v2 != v1, 'second accept did not assign a new version'


def test_status_shows_second_desired_price_while_first_unacknowledged():
    for seed in SEEDS:
        sim = _new_sim(seed, loss=1.0, fault_window=(0, 10))
        _assert_success(sim.server.accept_desired_price(STATION, 100))
        sim.run(2)
        _assert_first_unacknowledged(sim)
        _assert_success(sim.server.accept_desired_price(STATION, 200))
        status = sim.server.query_station_status(STATION)
        desired = _field(status, 'desired_price', 'desired')
        assert desired == 200, 'desired price not updated: {!r}'.format(desired)
        up = _field(status, 'up_to_date', 'up_to_date_flag', 'is_up_to_date')
        assert up is not _MISSING and not up


def test_second_price_not_refused_across_ticks_with_first_unacknowledged():
    for seed in SEEDS:
        sim = _new_sim(seed, loss=1.0, fault_window=(0, 10))
        _assert_success(sim.server.accept_desired_price(STATION, 100))
        sim.run(1)
        _assert_success(sim.server.accept_desired_price(STATION, 200))
        sim.run(5)
        _assert_first_unacknowledged(sim)
        _assert_success(sim.server.accept_desired_price(STATION, 300))
        status = sim.server.query_station_status(STATION)
        assert _field(status, 'desired_price', 'desired') == 300


def test_successive_changes_all_accepted_while_unacknowledged():
    for seed in SEEDS:
        sim = _new_sim(seed, loss=1.0, fault_window=(0, 10))
        prices = (100, 200, 300, 400)
        for price in prices:
            _assert_success(sim.server.accept_desired_price(STATION, price))
        status = sim.server.query_station_status(STATION)
        assert _field(status, 'desired_price', 'desired') == prices[-1]


def test_second_price_reaches_station_after_first_is_released():
    for seed in SEEDS:
        sim = _new_sim(seed)
        sim.set_reachable(STATION, False)
        _assert_success(sim.server.accept_desired_price(STATION, 100))
        sim.run(2)
        _assert_first_unacknowledged(sim)
        _assert_success(sim.server.accept_desired_price(STATION, 200))
        sim.run(2)
        assert sim.acks == []
        sim.set_reachable(STATION, True)
        sim.run(60)
        assert sim.stations[STATION].displayed == 200, \
            'station shows {!r}, expected 200'.format(sim.stations[STATION].displayed)
        status = sim.server.query_station_status(STATION)
        up = _field(status, 'up_to_date', 'up_to_date_flag', 'is_up_to_date')
        assert up is not _MISSING and up
