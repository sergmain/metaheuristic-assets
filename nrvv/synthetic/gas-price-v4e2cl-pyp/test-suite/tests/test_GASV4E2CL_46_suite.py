'''GASV4E2CL-11: dispatch the current desired price whenever it differs from the last sent.'''
import app
from nrvv_env import (
    Simulation, price_at_send_violations, repeat_violations, message_form_violations,
)

STATION = 'S1'
SEEDS = (1, 2, 3, 4, 5)


def _server(send_price_update):
    # The server reaches the transport only through the port GASV4E2CL-19, which the environment provides.
    if hasattr(app, 'Server'):
        return app.Server(send_price_update)
    if hasattr(app, 'make_server'):
        return app.make_server(send_price_update)
    app.send_price_update = send_price_update
    return app


def _quiet_sim(seed):
    # duration=0 schedules no central price changes; each test makes its own changes.
    return Simulation(seed, _server, duration=0)


def test_idle_station_change_sends_one_update_with_next_identifier():
    for seed in SEEDS:
        sim = _quiet_sim(seed)
        sim.server.set_desired_price(STATION, 5)
        sim.run_until_idle()
        assert len(sim.sends) == 1
        assert sim.in_flight() == 0
        previous = sim.sends[-1]

        sim.server.set_desired_price(STATION, 9)
        assert len(sim.sends) == 2
        sent = sim.sends[-1]
        assert sent.station == STATION
        assert sent.price == 9
        assert sent.update_id == previous.update_id + 1
        assert sim.in_flight() == 1

        sim.run_until_idle()
        assert len(sim.sends) == 2
        assert repeat_violations(sim) == []
        assert price_at_send_violations(sim) == []


def test_acknowledgement_dispatches_price_stored_while_update_in_flight():
    for seed in SEEDS:
        sim = _quiet_sim(seed)
        sim.server.set_desired_price(STATION, 5)
        sim.server.set_desired_price(STATION, 7)
        assert len(sim.sends) == 1

        sim.run_until_idle()
        assert [s.price for s in sim.sends] == [5, 7]
        assert sim.sends[1].update_id == sim.sends[0].update_id + 1
        assert sim.sends[1].station == STATION
        assert repeat_violations(sim) == []
        assert price_at_send_violations(sim) == []


def test_equal_price_change_or_acknowledgement_sends_nothing():
    for seed in SEEDS:
        sim = _quiet_sim(seed)
        sim.server.set_desired_price(STATION, 5)
        sim.run_until_idle()
        assert len(sim.sends) == 1

        sim.server.set_desired_price(STATION, 5)
        assert len(sim.sends) == 1
        assert sim.in_flight() == 0
        sim.run_until_idle()
        assert len(sim.sends) == 1
        assert sim.in_flight() == 0

        sim.server.set_desired_price(STATION, 5)
        sim.server.set_desired_price(STATION, 5)
        sim.run_until_idle()
        assert len(sim.sends) == 1
        assert sim.in_flight() == 0


def test_change_while_update_in_flight_waits_for_acknowledgement():
    for seed in SEEDS:
        sim = _quiet_sim(seed)
        sim.server.set_desired_price(STATION, 5)
        sim.server.set_desired_price(STATION, 7)
        sim.server.set_desired_price(STATION, 8)
        assert len(sim.sends) == 1
        assert sim.in_flight() == 1

        sim.run_until_idle()
        assert [s.price for s in sim.sends] == [5, 8]
        assert repeat_violations(sim) == []
        assert price_at_send_violations(sim) == []


def test_random_runs_never_send_stale_price_or_overlap_updates():
    for seed in range(1, 11):
        sim = Simulation(seed, _server)
        sim.run_until_idle()
        assert sim.changes
        assert price_at_send_violations(sim) == []
        assert repeat_violations(sim) == []
        assert message_form_violations(sim) == []


def test_random_runs_update_identifiers_increase_by_one_per_station():
    for seed in range(1, 11):
        sim = Simulation(seed, _server)
        sim.run_until_idle()
        for station in sim.stations:
            ids = [s.update_id for s in sim.sends if s.station == station]
            assert all(b == a + 1 for a, b in zip(ids, ids[1:]))
