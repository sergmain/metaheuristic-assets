# GASV4PRDA-40: acknowledgements are matched by station and sequence number, in arrival order.

import importlib

import app
from nrvv_env import Simulation

SEEDS = (1, 7, 42)


def _fresh_sim(seed):
    # Reload so that no state left by an earlier test reaches this one.
    importlib.reload(app)
    return Simulation(
        seed,
        server=app,
        stations=['S1', 'S2'],
        loss_rate=0.0,
        duplicate_rate=0.0,
        outages=False,
        change_rate=0.0,
    )


def test_matching_ack_empties_slot_and_triggers_rule_d4():
    for seed in SEEDS:
        sim = _fresh_sim(seed)
        app.desired_price_change('S1', 20)
        assert len(sim.send_calls) == 1
        first = sim.send_calls[0]
        assert (first.station_id, first.price) == ('S1', 20)
        n = first.sequence_number

        app.desired_price_change('S1', 30)  # slot is filled: no send
        assert len(sim.send_calls) == 1

        assert app.acknowledgement_received('S1', n) is None
        assert len(sim.send_calls) == 2  # rule of D4 sends the new desired price
        d4 = sim.send_calls[1]
        assert (d4.station_id, d4.price) == ('S1', 30)


def test_matching_ack_leaves_slot_empty_for_next_change():
    for seed in SEEDS:
        sim = _fresh_sim(seed)
        app.desired_price_change('S1', 20)
        n = sim.send_calls[0].sequence_number
        app.acknowledgement_received('S1', n)
        # desired equals the last sent price, so rule D4 sends nothing
        assert len(sim.send_calls) == 1

        app.desired_price_change('S1', 30)  # slot is empty: sent at once
        assert len(sim.send_calls) == 2
        assert (sim.send_calls[1].station_id, sim.send_calls[1].price) == ('S1', 30)


def test_earlier_sequence_ack_is_ignored_while_newer_update_outstanding():
    for seed in SEEDS:
        sim = _fresh_sim(seed)
        app.desired_price_change('S1', 20)
        n0 = sim.send_calls[0].sequence_number
        app.acknowledgement_received('S1', n0)

        app.desired_price_change('S1', 30)
        assert len(sim.send_calls) == 2
        n1 = sim.send_calls[1].sequence_number
        assert n1 != n0
        app.desired_price_change('S1', 40)  # slot filled by n1: no send
        assert len(sim.send_calls) == 2

        assert app.acknowledgement_received('S1', n0) is None  # duplicate of old update
        assert len(sim.send_calls) == 2

        app.desired_price_change('S1', 50)  # slot still filled by n1: no send
        assert len(sim.send_calls) == 2

        app.acknowledgement_received('S1', n1)
        assert len(sim.send_calls) == 3
        assert (sim.send_calls[2].station_id, sim.send_calls[2].price) == ('S1', 50)


def test_ack_from_other_station_is_ignored():
    for seed in SEEDS:
        sim = _fresh_sim(seed)
        app.desired_price_change('S1', 20)
        n = sim.send_calls[0].sequence_number

        assert app.acknowledgement_received('S2', n) is None
        assert len(sim.send_calls) == 1

        app.desired_price_change('S1', 30)  # slot still filled by S1: no send
        assert len(sim.send_calls) == 1

        app.acknowledgement_received('S1', n)
        assert len(sim.send_calls) == 2
        assert (sim.send_calls[1].station_id, sim.send_calls[1].price) == ('S1', 30)


def test_ack_with_later_sequence_number_is_ignored():
    for seed in SEEDS:
        sim = _fresh_sim(seed)
        app.desired_price_change('S1', 20)
        n = sim.send_calls[0].sequence_number

        assert app.acknowledgement_received('S1', n + 1) is None
        assert len(sim.send_calls) == 1

        app.desired_price_change('S1', 30)  # slot still filled by n: no send
        assert len(sim.send_calls) == 1

        app.acknowledgement_received('S1', n)
        assert len(sim.send_calls) == 2
        assert sim.send_calls[1].price == 30


def test_duplicate_ack_after_newer_update_acknowledged_is_ignored():
    for seed in SEEDS:
        sim = _fresh_sim(seed)
        app.desired_price_change('S1', 20)
        n0 = sim.send_calls[0].sequence_number
        app.acknowledgement_received('S1', n0)

        app.desired_price_change('S1', 30)
        assert len(sim.send_calls) == 2
        n1 = sim.send_calls[1].sequence_number
        app.desired_price_change('S1', 40)  # slot filled by n1: no send
        assert len(sim.send_calls) == 2

        app.acknowledgement_received('S1', n1)  # matches: D4 sends 40
        assert len(sim.send_calls) == 3
        assert sim.send_calls[2].price == 40
        n2 = sim.send_calls[2].sequence_number

        assert app.acknowledgement_received('S1', n1) is None  # duplicate, n2 outstanding
        assert len(sim.send_calls) == 3

        app.desired_price_change('S1', 50)  # slot filled by n2: no send
        assert len(sim.send_calls) == 3

        app.acknowledgement_received('S1', n2)
        assert len(sim.send_calls) == 4
        assert sim.send_calls[3].price == 50
