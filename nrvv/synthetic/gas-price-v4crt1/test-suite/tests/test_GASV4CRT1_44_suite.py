import app
from nrvv_env import Simulation

SEEDS = (0, 1, 2, 3, 4, 5, 6, 7, 8, 9)


def _service_class():
    found = [value for value in vars(app).values()
             if isinstance(value, type) and value.__module__.startswith(app.__name__)
             and all(hasattr(value, m) for m in ('set_desired_price', 'receive_acknowledgement', 'inspect_station'))]
    assert len(found) == 1, f'expected one service class in app, found {found}'
    return found[0]


def _build(seed, stations, **kwargs):
    sim = Simulation(seed, stations, **kwargs)
    service = _service_class()(sim.send_price_update)
    sim.connect(service)
    return sim, service


def _state_field(state, name, index):
    if isinstance(state, dict):
        return state.get(name)
    if hasattr(state, name):
        return getattr(state, name)
    return state[index]


def _confirmed_price(service, station):
    return _state_field(service.inspect_station(station), 'confirmed', 1)


def _in_flight_price(service, station):
    return _state_field(service.inspect_station(station), 'in_flight', 2)


def test_price_only_update_is_displayed_by_station():
    sim, _ = _build(1, ['S1'], changes=0)
    sim.issue_desired_price('S1', 3)
    sim.run()
    assert [(s.station, s.price) for s in sim.sends] == [('S1', 3)]
    assert [(d.station, d.price, d.displayed) for d in sim.deliveries] == [('S1', 3, 3)]
    assert sim.displayed('S1') == 3


def test_service_completes_update_on_acknowledgement_alone():
    sim, service = _build(2, ['S1'], changes=0)
    sim.issue_desired_price('S1', 4)
    sim.run()
    assert len(sim.sends) == 1
    assert [(a.station, a.price) for a in sim.acks] == [('S1', 4)]
    assert _confirmed_price(service, 'S1') == 4
    assert _in_flight_price(service, 'S1') is None
    assert sim.outstanding('S1') == 0


def test_no_update_is_sent_while_one_is_unacknowledged():
    for seed in SEEDS:
        sim, _ = _build(seed, ['A', 'B'], changes=30)
        sim.run()
        assert sim.sends, f'seed {seed}: no updates were sent'
        for send in sim.sends:
            assert send.outstanding_before == 0, f'seed {seed}: {send}'


def test_next_update_follows_the_acknowledgement_it_waits_for():
    for seed in SEEDS:
        stations = ['A', 'B', 'C']
        sim, _ = _build(seed, stations, changes=30)
        sim.run()
        for station in stations:
            sends = [s for s in sim.sends if s.station == station]
            acks = [a for a in sim.acks if a.station == station]
            assert len(acks) == len(sends), f'seed {seed}, station {station}'
            for k in range(1, len(sends)):
                assert sends[k].step >= acks[k - 1].step, f'seed {seed}, station {station}, send {k}'


def test_station_gets_only_price_updates_and_acks_echo_the_price():
    for seed in SEEDS:
        stations = ['A', 'B']
        sim, _ = _build(seed, stations, changes=25)
        sim.run()
        for station in stations:
            sends = [s for s in sim.sends if s.station == station]
            deliveries = [d for d in sim.deliveries if d.station == station]
            acks = [a for a in sim.acks if a.station == station]
            assert [d.price for d in deliveries] == [s.price for s in sends], f'seed {seed}, station {station}'
            assert [a.price for a in acks] == [d.displayed for d in deliveries], f'seed {seed}, station {station}'
            assert all(s.price == s.desired_at_send for s in sends), f'seed {seed}, station {station}'


def test_service_converges_on_each_desired_price_with_acknowledgements_only():
    checked = 0
    for seed in SEEDS:
        stations = ['A', 'B', 'C']
        sim, service = _build(seed, stations, changes=20)
        sim.run()
        for station in stations:
            desired = sim.desired(station)
            if desired is None:
                continue
            checked += 1
            assert sim.displayed(station) == desired, f'seed {seed}, station {station}'
            assert _confirmed_price(service, station) == desired, f'seed {seed}, station {station}'
            assert _in_flight_price(service, station) is None, f'seed {seed}, station {station}'
            assert sim.in_transit(station) == 0
            assert sim.outstanding(station) == 0
    assert checked > 0
