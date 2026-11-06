import inspect

import app
import nrvv_env

STATIONS = ('S1', 'S2')
SEEDS = (1, 2, 3, 4, 5)


def _service_class():
    for name in dir(app):
        obj = getattr(app, name)
        if name[:1].isupper() and inspect.isclass(obj) and all(
                hasattr(obj, m) for m in ('set_desired_price', 'inspect_station', 'receive_acknowledgement')):
            return obj
    raise AssertionError('app has no service class with the Interface operations')


def _build_service(sim):
    cls = _service_class()
    attempts = (
        lambda: cls(sim.send_price_update),
        lambda: cls(send_price_update=sim.send_price_update),
        lambda: cls(sim.send_price_update, list(STATIONS)),
        lambda: cls(list(STATIONS), sim.send_price_update),
        lambda: cls(stations=list(STATIONS), send_price_update=sim.send_price_update),
        lambda: cls(list(STATIONS), outbound=sim.send_price_update),
        lambda: cls(outbound_port=sim.send_price_update, stations=list(STATIONS)),
        lambda: cls(stations=list(STATIONS), outbound_port=sim.send_price_update),
    )
    for attempt in attempts:
        try:
            return attempt()
        except TypeError:
            continue
    raise AssertionError('app service class does not accept the outbound port')


def _make(seed):
    sim = nrvv_env.Simulation(seed, STATIONS, changes=0)
    service = _build_service(sim)
    sim.connect(service)
    return sim, service


def _confirmed(service, station):
    state = service.inspect_station(station)
    if state is None:
        return None
    if isinstance(state, dict):
        return state.get('confirmed')
    if hasattr(state, 'confirmed'):
        return getattr(state, 'confirmed')
    return state[1]


def _confirm(sim, station, price):
    sim.issue_desired_price(station, price)
    sim.run()


def test_same_price_as_confirmed_sends_nothing():
    for seed in SEEDS:
        sim, service = _make(seed)
        _confirm(sim, 'S1', '100')
        assert _confirmed(service, 'S1') == '100'
        sends_before = len(sim.sends)
        sim.issue_desired_price('S1', '100')
        sim.run()
        assert len(sim.sends) == sends_before
        assert sim.in_transit('S1') == 0
        assert sim.outstanding('S1') == 0
        assert sim.displayed('S1') == '100'


def test_desired_changed_away_and_back_during_flight_sends_nothing():
    for seed in SEEDS:
        sim, service = _make(seed)
        sim.issue_desired_price('S1', '100')
        assert sim.outstanding('S1') == 1
        sim.issue_desired_price('S1', '120')
        sim.issue_desired_price('S1', '100')
        sim.run()
        assert [s.price for s in sim.sends] == ['100']
        assert _confirmed(service, 'S1') == '100'
        assert sim.displayed('S1') == '100'
        assert sim.outstanding('S1') == 0


def test_changed_price_sends_exactly_one_update():
    for seed in SEEDS:
        sim, service = _make(seed)
        _confirm(sim, 'S1', '100')
        assert _confirmed(service, 'S1') == '100'
        sends_before = len(sim.sends)
        sim.issue_desired_price('S1', '120')
        sim.run()
        new_sends = sim.sends[sends_before:]
        assert len(new_sends) == 1
        assert new_sends[0].price == '120'
        assert new_sends[0].confirmed_at_send == '100'
        assert sim.displayed('S1') == '120'
        assert _confirmed(service, 'S1') == '120'
