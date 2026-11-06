'''Oracles over a Simulation. Each returns a list of violations; an empty list means the check passed.

A station state is whatever the service's ``query_station_state`` returns.
``view`` maps it to a dict with the keys desired_price, shown_price,
in_flight_seq, in_flight_price, pending and timeout. The default view reads
those names from a mapping or from attributes of the same name.
'''
from collections.abc import Mapping

FIELDS = ('desired_price', 'shown_price', 'in_flight_seq', 'in_flight_price', 'pending', 'timeout')


def default_view(state):
    view = {}
    for name in FIELDS:
        if isinstance(state, Mapping):
            view[name] = state.get(name)
        else:
            view[name] = getattr(state, name, None)
    return view


def desired_in_effect(sim, station, tick):
    price = None
    for change in sim.script:
        if change.station == station and change.tick <= tick:
            price = change.price
    return price


def redundant_send_violations(sim, view=default_view):
    violations = []
    for send in sim.sends:
        state = view(send.state_before.get(send.station))
        if state['shown_price'] is not None and send.price == state['shown_price']:
            violations.append(('equals-shown-price', send))
        if state['desired_price'] == state['shown_price'] and state['in_flight_seq'] is None:
            violations.append(('idle-and-already-shown', send))
    return violations


def superseded_send_violations(sim):
    violations = []
    for send in sim.sends:
        if desired_in_effect(sim, send.station, send.tick) != send.price:
            violations.append(('not-desired-at-send', send))
    return violations


def change_trigger_violations(sim, view=default_view):
    violations = []
    sent = {(s.tick, s.station) for s in sim.sends}
    for change in sim.changes:
        state = view(change.state_before.get(change.station))
        if state['in_flight_seq'] is not None:
            continue
        if change.price == state['shown_price']:
            continue
        if (change.tick, change.station) not in sent:
            violations.append(('no-send-on-idle-change', change))
    return violations


def final_display_violations(sim):
    violations = []
    for station in sim.station_ids:
        if not sim.reachable_at_end(station):
            continue
        if sim.stations[station].price != sim.final_desired(station):
            violations.append(('station-not-at-desired', station))
    return violations


def service_record_violations(sim, view=default_view):
    violations = []
    for station in sim.station_ids:
        if not sim.reachable_at_end(station):
            continue
        state = view(sim.query(station))
        if state['shown_price'] != sim.final_desired(station):
            violations.append(('service-record-not-at-desired', station))
    return violations


def check_all(sim, view=default_view):
    return {
        'redundant': redundant_send_violations(sim, view),
        'superseded': superseded_send_violations(sim),
        'change_trigger': change_trigger_violations(sim, view),
        'final_display': final_display_violations(sim),
        'service_record': service_record_violations(sim, view),
    }
