import app
from nrvv_env import Simulation

SEEDS = (1, 2, 3, 4, 5, 6)
MAX_STEPS = 2000

LIST_OPERATION_NAMES = (
    'list_stations_not_acknowledging_latest_price',
    'list_stations_not_yet_acknowledging_latest_price',
    'list_stations_not_showing_latest_price',
    'list_unacknowledged_stations',
    'list_stations_not_acknowledging_latest',
    'stations_not_acknowledging_latest_price',
)


def _list_operation():
    for name in LIST_OPERATION_NAMES:
        operation = getattr(app, name, None)
        if callable(operation):
            return operation
    names = sorted(
        name for name in dir(app)
        if not name.startswith('_') and 'station' in name
        and any(word in name for word in ('ack', 'latest', 'stale', 'pending', 'unack', 'not'))
        and callable(getattr(app, name))
    )
    assert names, 'app has no operation listing stations not yet acknowledging the latest price'
    return getattr(app, names[0])


def _station_names(result, known):
    if result is None:
        return set()
    if isinstance(result, dict) and set(result) <= set(known):
        return set(result)
    items = result.values() if isinstance(result, dict) else result
    names = set()
    for item in items:
        if isinstance(item, str):
            names.add(item)
        elif isinstance(item, dict):
            names.add(item.get('station', item.get('name')))
        elif isinstance(item, (tuple, list)):
            names.add(item[0])
        else:
            names.add(getattr(item, 'station'))
    return names


def _sim(seed, tag, calls=15):
    names = tuple('%s-%d-S%d' % (tag, seed, i) for i in range(1, 4))
    return Simulation(app, seed, stations=names, calls=calls)


def _acked_stations(sim):
    return [s for s in sim.desired if sim.last_ack_price(s) is not None]


def _check(sim, listed):
    # Stations never acknowledged have no confirmed price yet, so they are not compared.
    got = _station_names(listed(), sim.stations)
    acked = _acked_stations(sim)
    expected = {s for s in acked if sim.last_ack_price(s) != sim.desired[s]}
    assert got <= set(sim.desired), 'listed a station with no desired price: %s' % sorted(got)
    assert got & set(acked) == expected, (
        'listed %s, expected %s, desired=%s, confirmed=%s'
        % (sorted(got), sorted(expected), sim.desired,
           {s: sim.last_ack_price(s) for s in sim.desired}))
    return expected


def test_list_returns_exactly_stations_whose_confirmed_price_differs_from_desired():
    listed = _list_operation()
    checked = mismatched = 0
    for seed in SEEDS:
        sim = _sim(seed, 'mismatch')
        for _ in range(MAX_STEPS):
            if not sim.step():
                break
            expected = _check(sim, listed)
            checked += 1
            mismatched += bool(expected)
    assert checked > 0
    assert mismatched > 0


def test_list_is_empty_when_every_station_shows_its_desired_price():
    listed = _list_operation()
    for seed in SEEDS:
        sim = _sim(seed, 'quiet')
        sim.run(MAX_STEPS)
        assert sim.is_quiet()
        assert _check(sim, listed) == set()


def test_station_is_omitted_from_next_listing_after_it_confirms_desired_price():
    listed = _list_operation()
    confirmations = 0
    for seed in SEEDS:
        sim = _sim(seed, 'confirm')
        for _ in range(MAX_STEPS):
            if not sim.step():
                break
            if sim.ack_log and sim.ack_log[-1].step == sim.step_no:
                ack = sim.ack_log[-1]
                if ack.price == sim.desired[ack.station]:
                    got = _station_names(listed(), sim.stations)
                    assert ack.station not in got, (
                        'station %s confirmed its desired price %s but is still listed'
                        % (ack.station, ack.price))
                    confirmations += 1
    assert confirmations > 0


def test_station_is_listed_again_after_a_new_desired_price_is_set():
    listed = _list_operation()
    new_prices = 0
    for seed in SEEDS:
        sim = _sim(seed, 'newprice')
        for _ in range(MAX_STEPS):
            if not sim.step():
                break
            if sim.call_log and sim.call_log[-1].step == sim.step_no:
                call = sim.call_log[-1]
                confirmed = sim.last_ack_price(call.station)
                if confirmed is not None and confirmed != call.price:
                    got = _station_names(listed(), sim.stations)
                    assert call.station in got, (
                        'station %s got new desired price %s (confirmed %s) but is not listed'
                        % (call.station, call.price, confirmed))
                    new_prices += 1
    assert new_prices > 0


def test_listing_changes_no_state():
    listed = _list_operation()
    for seed in SEEDS[:3]:
        sim = _sim(seed, 'readonly')
        for _ in range(MAX_STEPS):
            queries_before = {s: sim.query(s) for s in sim.stations}
            before = (sim.in_flight(), sim.pending_acks(), len(sim.sent_log),
                      len(sim.notices), len(sim.ack_log))
            first = _station_names(listed(), sim.stations)
            second = _station_names(listed(), sim.stations)
            assert first == second
            assert {s: sim.query(s) for s in sim.stations} == queries_before
            after = (sim.in_flight(), sim.pending_acks(), len(sim.sent_log),
                     len(sim.notices), len(sim.ack_log))
            assert after == before
            if not sim.step():
                break
