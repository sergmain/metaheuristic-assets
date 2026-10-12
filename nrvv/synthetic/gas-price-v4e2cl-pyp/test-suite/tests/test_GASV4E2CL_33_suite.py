'''GASV4E2CL-3: the service sends each station every change of its desired price.'''
import app
from nrvv_env import (
    Simulation, price_at_send_violations, message_form_violations,
    unsent_change_violations, convergence_violations,
)

STATION = 'S1'
SEEDS = (1, 2, 3, 4, 5)


def _server_factory(send_price_update):
    # The server is the price-update server of app, handed the transport port.
    for name in dir(app):
        candidate = getattr(app, name)
        if isinstance(candidate, type) and callable(getattr(candidate, 'set_desired_price', None)):
            return candidate(send_price_update)
    return app


def _simulation(seed):
    # No scheduled central changes: each test schedules exactly the changes it checks.
    return Simulation(seed, _server_factory, stations=(STATION,), duration=0)


def _schedule_change(sim, time, value):
    # Central price source (GASV4E2CL-22): a desired-price change for the station at a virtual time.
    sim._push(time, 'price', (STATION, value))


def _sends_since(sim, mark):
    return [s for s in sim.sends[mark:] if s.station == STATION]


def test_each_desired_price_change_sends_exactly_one_update_with_new_price():
    for seed in SEEDS:
        sim = _simulation(seed)
        _schedule_change(sim, 1, 100)
        sim.run_until_idle()
        assert sim.desired_price(STATION) == 100, f'seed {seed}: setup did not store the known price'

        for value in (200, 300):
            mark = len(sim.sends)
            changed_at = sim.now + 10
            _schedule_change(sim, changed_at, value)
            sim.run_until_idle()
            sent = _sends_since(sim, mark)
            assert len(sent) == 1, f'seed {seed}: change to {value} produced {len(sent)} updates'
            assert sent[0].price == value, f'seed {seed}: update carried {sent[0].price}, expected {value}'
            assert sent[0].time >= changed_at, f'seed {seed}: update sent before the change'
            assert sim.desired_price(STATION) == value

        assert price_at_send_violations(sim) == []
        assert unsent_change_violations(sim) == []
        assert message_form_violations(sim) == []


def test_station_displays_each_new_desired_price_after_change():
    for seed in SEEDS:
        sim = _simulation(seed)
        _schedule_change(sim, 1, 100)
        sim.run_until_idle()

        for value in (200, 300):
            _schedule_change(sim, sim.now + 10, value)
            sim.run_until_idle()
            assert sim.stations[STATION].displayed_price == value, f'seed {seed}: station shows wrong price'

        assert convergence_violations(sim) == []


def test_change_during_station_outage_still_sends_one_update():
    for seed in SEEDS:
        sim = _simulation(seed)
        _schedule_change(sim, 1, 100)
        sim.run_until_idle()

        # First outage window of the station that starts after the setup has finished.
        start, _ = next(w for w in sim.outages(STATION, until=20000) if w[0] > sim.now)
        mark = len(sim.sends)
        _schedule_change(sim, start + 1, 200)
        sim.run_until_idle()

        sent = _sends_since(sim, mark)
        assert len(sent) == 1, f'seed {seed}: change during outage produced {len(sent)} updates'
        assert sent[0].price == 200, f'seed {seed}: update carried {sent[0].price}, expected 200'
        assert sim.stations[STATION].displayed_price == 200, f'seed {seed}: station did not get the new price'
