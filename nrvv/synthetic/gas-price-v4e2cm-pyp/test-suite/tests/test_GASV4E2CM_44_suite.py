import app
from nrvv_env import Simulation

SEEDS = range(6)


def _status_field(status, names):
    for name in names:
        if isinstance(status, dict):
            if name in status:
                return status[name]
        elif hasattr(status, name):
            return getattr(status, name)
    raise AssertionError('status has none of %s: %r' % (names, status))


def _confirmed(sim, station_id):
    return _status_field(sim.status(station_id), ('confirmed_price', 'confirmed'))


def _in_flight(sim, station_id):
    return _status_field(sim.status(station_id), ('in_flight_price', 'in_flight'))


def _desired(sim, station_id):
    return _status_field(sim.status(station_id), ('desired_price', 'desired'))


def _last_desired(sim, station_id):
    prices = [price for _, sid, price in sim.desired_history if sid == station_id]
    return prices[-1] if prices else None


def test_price_update_carries_only_station_and_price():
    for seed in SEEDS:
        sim = Simulation(app, seed, loss=0.0, outage=0.0)
        sim.set_desired_price('S1', 42)
        assert sim.quiesce(bound=500, idle_ticks=50)
        updates = sim.sent_to('S1')
        assert len(updates) == 1
        assert updates[0]['station'] == 'S1'
        assert updates[0]['price'] == 42


def test_price_update_price_is_a_value_set_for_its_station():
    for seed in SEEDS:
        sim = Simulation(app, seed)
        sim.run_schedule(steps=60)
        for entry in sim.sent:
            assert entry['station'] in sim.stations
            set_prices = [p for _, sid, p in sim.desired_history if sid == entry['station']]
            assert entry['price'] in set_prices


def test_no_message_beyond_the_single_price_update():
    sim = Simulation(app, 7, loss=0.0, outage=0.0)
    sim.set_desired_price('S1', 42)
    assert sim.quiesce(bound=500, idle_ticks=50)
    assert len(sim.sent) == 1
    assert sim.sends_per_station() == {'S1': 1, 'S2': 0, 'S3': 0}
    received = sim.stations['S1'].received
    assert len(received) == 1
    assert received[0][1] == 42


def test_quiet_service_sends_no_message():
    sim = Simulation(app, 3, loss=0.0, outage=0.0)
    for _ in range(40):
        sim.tick()
    assert sim.sent == []
    assert sim.acks == []


def test_acknowledgement_carries_only_station_id():
    sim = Simulation(app, 5, loss=0.0, outage=0.0)
    sim.set_desired_price('S2', 17)
    assert sim.quiesce(bound=500, idle_ticks=50)
    assert [station_id for _, station_id in sim.acks] == ['S2']
    assert sim.acks_per_station() == {'S1': 0, 'S2': 1, 'S3': 0}
    assert sim.stations['S2'].acks_returned == 1


def test_acknowledgement_confirms_price_update_without_sequence_number():
    sim = Simulation(app, 9, loss=0.0, outage=0.0)
    sim.set_desired_price('S1', 42)
    assert sim.quiesce(bound=500, idle_ticks=50)
    assert _confirmed(sim, 'S1') == 42
    assert _in_flight(sim, 'S1') is None
    assert _desired(sim, 'S1') == 42
    assert len(sim.sent_to('S1')) == 1


def test_acknowledgements_confirm_last_desired_price_over_seeds():
    for seed in SEEDS:
        sim = Simulation(app, seed)
        sim.run_schedule(steps=60)
        assert sim.quiesce(bound=2000, idle_ticks=100)
        for station_id in sim.stations:
            desired = _last_desired(sim, station_id)
            if desired is None:
                continue
            assert _desired(sim, station_id) == desired
            assert _confirmed(sim, station_id) == desired
            assert _in_flight(sim, station_id) is None
