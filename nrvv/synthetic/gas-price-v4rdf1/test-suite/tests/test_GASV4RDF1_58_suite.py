# Tests for GASV4RDF1-58: list of stations not yet showing their latest price.
import random

import app
from nrvv_env import Simulation


def _station_id(entry):
    if isinstance(entry, dict):
        return entry.get('station_id', entry.get('id'))
    if isinstance(entry, str):
        return entry
    return entry.station_id


def _ids(result):
    return sorted(_station_id(e) for e in result)


def _entry(result, station_id):
    for e in result:
        if _station_id(e) == station_id:
            return e
    return None


def _field_values(entry):
    if isinstance(entry, dict):
        return list(entry.values())
    return list(vars(entry).values())


def _build(seed, desired):
    # every station starts with a desired price that it has confirmed
    sim = Simulation(seed, app)
    for sid, price in desired.items():
        sim.add_station(sid)
        sim.set_desired_price(sid, price)
    for sid in desired:
        sim.acknowledge(sid)
    sim.run_until_idle()
    return sim


def _snapshot(sim):
    return (
        len(sim.traffic),
        repr(sim.in_flight()),
        repr([sim.stations[k] for k in sorted(sim.stations)]),
        len(sim.notices),
        sim.now,
    )


def test_lists_exactly_stations_whose_confirmed_price_differs_from_desired():
    sim = _build(1, {'s1': 100, 's2': 200, 's3': 300, 's4': 400})
    sim.set_desired_price('s2', 250)
    sim.set_desired_price('s4', 450)
    assert _ids(sim.list_unacknowledged()) == ['s2', 's4']


def test_pending_acknowledgement_keeps_station_listed_until_delivered():
    sim = _build(2, {'s1': 100, 's2': 200, 's3': 300})
    sim.set_desired_price('s1', 150)
    sim.set_desired_price('s3', 350)
    sim.acknowledge('s1')
    assert _ids(sim.list_unacknowledged()) == ['s1', 's3']
    sim.run_until_idle()
    assert _ids(sim.list_unacknowledged()) == ['s3']


def test_confirmed_station_is_omitted_on_next_call():
    sim = _build(3, {'a': 10, 'b': 20, 'c': 30})
    sim.set_desired_price('a', 11)
    sim.set_desired_price('c', 31)
    assert _ids(sim.list_unacknowledged()) == ['a', 'c']
    sim.acknowledge('a')
    sim.run_until_idle()
    assert _ids(sim.list_unacknowledged()) == ['c']


def test_new_desired_price_makes_station_listed_on_next_call():
    sim = _build(4, {'s1': 100, 's2': 200, 's3': 300})
    assert _ids(sim.list_unacknowledged()) == []
    sim.set_desired_price('s2', 999)
    assert _ids(sim.list_unacknowledged()) == ['s2']
    sim.set_desired_price('s3', 888)
    assert _ids(sim.list_unacknowledged()) == ['s2', 's3']


def test_empty_result_when_every_confirmed_price_matches_desired():
    sim = _build(5, {'s1': 100, 's2': 200})
    assert list(sim.list_unacknowledged()) == []


def test_listing_changes_no_state_and_is_repeatable():
    sim = _build(6, {'s1': 100, 's2': 200, 's3': 300})
    sim.set_desired_price('s1', 150)
    before = _snapshot(sim)
    first = _ids(sim.list_unacknowledged())
    second = _ids(sim.list_unacknowledged())
    assert first == second == ['s1']
    assert _snapshot(sim) == before


def test_entries_carry_desired_and_confirmed_price():
    sim = _build(7, {'s1': 100, 's2': 200})
    sim.set_desired_price('s1', 150)
    entry = _entry(sim.list_unacknowledged(), 's1')
    assert entry is not None
    values = _field_values(entry)
    assert 150 in values
    assert 100 in values


def test_reverting_desired_to_confirmed_price_omits_station():
    sim = _build(8, {'s1': 100, 's2': 200})
    sim.set_desired_price('s1', 150)
    assert _ids(sim.list_unacknowledged()) == ['s1']
    sim.set_desired_price('s1', 100)
    assert _ids(sim.list_unacknowledged()) == []


def test_random_scenarios_match_definition_across_seeds():
    for seed in range(10):
        rng = random.Random(seed)
        ids = ['s%d' % i for i in range(8)]
        base = {sid: 100 + 10 * i for i, sid in enumerate(ids)}
        sim = _build(seed, base)
        changed = set(sid for sid in ids if rng.random() < 0.5)
        for sid in sorted(changed):
            sim.set_desired_price(sid, base[sid] + 7)
        acked = set(sid for sid in sorted(changed) if rng.random() < 0.5)
        for sid in sorted(acked):
            sim.acknowledge(sid)
        assert _ids(sim.list_unacknowledged()) == sorted(changed)
        sim.run_until_idle()
        assert _ids(sim.list_unacknowledged()) == sorted(changed - acked)
