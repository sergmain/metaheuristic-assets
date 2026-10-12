'''GASV4E2CL-45: a station unreachable while the price changes, then reconnected without any recovery action.

After reconnection the station must show the settled price within three one-way delays plus two
acknowledgement delays, and no update may be sent without a price change or an acknowledgement as trigger,
nor repeat an unchanged price, nor overlap an update in flight.
'''
import inspect
from functools import lru_cache

import app
from nrvv_env import (
    Simulation, STATIONS, DURATION, MAX_DELAY,
    price_at_send_violations, repeat_violations, message_form_violations,
    convergence_violations,
)

BOUND = 3 * MAX_DELAY + 2 * MAX_DELAY    # three one-way delays plus two acknowledgement delays
WANTED_CHANGES = 3                       # 'several' price changes inside one outage
SCENARIOS_WANTED = 3
SEARCH_SEEDS = range(2000)


def _make_server(send_price_update):
    classes = [cls for _, cls in inspect.getmembers(app, inspect.isclass)
               if callable(getattr(cls, 'set_desired_price', None))]
    assert classes, 'app provides no class with set_desired_price'
    classes.sort(key=lambda cls: cls.__module__ != app.__name__)
    cls = classes[0]
    required = [p for p in inspect.signature(cls).parameters.values()
                if p.default is inspect.Parameter.empty
                and p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD)]
    if len(required) == 1:
        return cls(send_price_update)
    return cls(send_price_update=send_price_update)


def _simulation(seed):
    return Simulation(seed, _make_server)


def _outage_hit(plan):
    '''First (station, outage start, outage end, settled price) whose outage holds several changes
    and is followed by no change of that station, with room left for the settle window.'''
    for sid in STATIONS:
        own = [c for c in plan.changes if c.station == sid]
        for start, end in plan.outages(sid, until=DURATION):
            if end + BOUND > DURATION:
                continue
            inside = [c for c in own if start <= c.time < end]
            if len(inside) >= WANTED_CHANGES and not any(c.time >= end for c in own):
                return sid, start, end, inside[-1].value
    return None


@lru_cache(maxsize=None)
def _scenarios():
    # The environment's outages and price changes depend only on the seed, not on the server,
    # so a planning run finds the scenarios; the test then replays the same seed.
    found = []
    for seed in SEARCH_SEEDS:
        hit = _outage_hit(_planned(seed))
        if hit:
            found.append((seed,) + hit)
        if len(found) == SCENARIOS_WANTED:
            break
    assert found, 'no seed gives an outage holding several price changes'
    return tuple(found)


def _planned(seed):
    plan = _simulation(seed)
    plan.run_until_idle()
    return plan


def _unexplained_sends(sim):
    '''Sends not triggered by a price change or an acknowledgement of the same station at that time.'''
    triggers = {(c.station, c.time) for c in sim.changes}
    triggers |= {(m.station, m.delivered_at) for m in sim.from_station if m.delivered_at is not None}
    return [s for s in sim.sends if (s.station, s.time) not in triggers]


def test_settled_price_shown_within_bound_after_reconnect():
    for seed, sid, start, end, settled in _scenarios():
        sim = _simulation(seed)
        sim.run_until(end + BOUND)
        assert sim.reachable(sid), f'seed {seed}: {sid} unreachable at t={sim.now}'
        assert sim.desired_price(sid) == settled, f'seed {seed}: server holds {sim.desired_price(sid)}, settled {settled}'
        shown = sim.stations[sid].displayed_price
        assert shown == settled, (
            f'seed {seed}: {sid} shows {shown} at t={sim.now}, settled {settled} (reconnected t={end})')
        assert convergence_violations(sim) == [], f'seed {seed}: {convergence_violations(sim)}'


def test_price_changes_land_while_station_unreachable():
    for seed, sid, start, end, settled in _scenarios():
        sim = _simulation(seed)
        sim.run_until(end)
        changes = [c for c in sim.changes if c.station == sid and start <= c.time < end]
        assert len(changes) >= WANTED_CHANGES, f'seed {seed}: only {len(changes)} changes in outage'
        assert all(not sim.reachable(sid, c.time) for c in changes), f'seed {seed}: station reachable in outage'
        assert sim.reachable(sid, end), f'seed {seed}: station not restored at t={end}'


def test_at_most_one_update_sent_during_outage():
    for seed, sid, start, end, settled in _scenarios():
        sim = _simulation(seed)
        sim.run_until(end)
        sent = [s for s in sim.sends if s.station == sid and start <= s.time < end]
        assert len(sent) <= 1, f'seed {seed}: {len(sent)} updates sent to {sid} while unreachable'


def test_every_update_follows_a_price_change_or_ack():
    for seed, sid, start, end, settled in _scenarios():
        sim = _simulation(seed)
        sim.run_until_idle()
        unexplained = _unexplained_sends(sim)
        assert not unexplained, f'seed {seed}: sends with no triggering change or ack: {unexplained}'


def test_no_repeat_price_or_overlapping_update():
    for seed, sid, start, end, settled in _scenarios():
        sim = _simulation(seed)
        sim.run_until_idle()
        assert repeat_violations(sim) == [], f'seed {seed}: {repeat_violations(sim)}'
        assert price_at_send_violations(sim) == [], f'seed {seed}: {price_at_send_violations(sim)}'
        assert message_form_violations(sim) == [], f'seed {seed}: {message_form_violations(sim)}'
