"""Suite for GASV3ACC2-37.

Criterion: given registered gas stations and a gas price update processed by
the service, the service delivers that price update to *every* one of the
registered stations; if any station does not receive it, the condition fails.

These tests drive the server (`app`) only through the simulated environment
(`nrvv_env`): the environment generates/injects desired prices via
submit-desired-price, carries the server's transmit-port emissions to the dumb
stations, returns acknowledgements, and exposes the stations and the traffic for
observation. Delivery to a station is observed on the environment's station
models (`sim.applied`, `Station.received_count`) and its delivery log
(`sim.delivered`) -- i.e. on what each station actually received, not on server
internals.
"""

from collections import Counter

import app
import nrvv_env


def _build_server(transmit):
    """Construct the server with its outbound transmit port wired to `transmit`.

    The server is a CapWords class of `app` exposing the inbound Interface
    operations; it is created here so the simulation can drive it.
    """
    cls = getattr(app, "Server", None)
    if isinstance(cls, type):
        return cls(transmit)
    for name in dir(app):
        obj = getattr(app, name)
        if isinstance(obj, type) and all(
            callable(getattr(obj, m, None))
            for m in (
                "submit_desired_price",
                "acknowledgement_received",
                "get_station_state",
            )
        ):
            return obj(transmit)
    raise AssertionError(
        "app does not expose a server class wired to the transmit port"
    )


def _latest_desired(events):
    """Map each station to the last price submitted for it (latest desired)."""
    latest = {}
    for station, price in events:
        latest[station] = price
    return latest


def test_each_registered_station_receives_its_update():
    """One distinct price per registered station -> each station receives it."""
    stations = ["A", "B", "C", "D", "E"]
    events = [(s, 10 + i) for i, s in enumerate(stations)]
    for seed in (1, 2, 3, 7, 42):
        sim = nrvv_env.Simulation(list(events), seed=seed)
        sim.connect(_build_server)
        sim.run(max_steps=100000)
        assert sim.quiescent(), (
            "service did not settle; some update was never delivered/acked"
        )
        expected = _latest_desired(events)
        received = {s for (s, _p) in sim.delivered}
        for s in stations:
            assert s in received, "station %r never received an update" % (s,)
            assert sim.station(s).received_count >= 1
            assert sim.applied(s) == expected[s]


def test_same_price_reaches_every_station():
    """The same price value submitted to every station reaches all of them."""
    stations = ["n1", "n2", "n3", "n4", "n5", "n6"]
    price = 57
    events = [(s, price) for s in stations]
    for seed in (3, 11, 21, 101):
        sim = nrvv_env.Simulation(list(events), seed=seed)
        sim.connect(_build_server)
        sim.run(max_steps=100000)
        assert sim.quiescent()
        for s in stations:
            assert (s, price) in sim.delivered, (
                "station %r did not receive the transmitted price" % (s,)
            )
            assert sim.applied(s) == price


def test_every_transmitted_update_is_delivered():
    """No transmitted update is lost: delivered log equals transmitted log."""
    for seed in (0, 1, 5, 13, 99):
        sim = nrvv_env.Simulation.from_seed(
            seed, num_stations=4, num_events=25
        )
        sim.connect(_build_server)
        sim.run(max_steps=200000)
        assert sim.quiescent()
        assert len(sim.sent) >= 1
        assert Counter(sim.delivered) == Counter(sim.sent), (
            "a transmitted price update did not reach its station"
        )


def test_no_registered_station_is_skipped():
    """Per-station delivery count matches per-station transmission count."""
    for seed in (6, 17, 23, 55):
        sim = nrvv_env.Simulation.from_seed(
            seed, num_stations=4, num_events=30
        )
        sim.connect(_build_server)
        sim.run(max_steps=300000)
        assert sim.quiescent()
        sent_by = Counter(s for (s, _p) in sim.sent)
        delivered_by = Counter(s for (s, _p) in sim.delivered)
        assert sent_by == delivered_by
        for s, n in sent_by.items():
            assert sim.station(s).received_count == n, (
                "station %r received %d of %d transmitted updates"
                % (s, sim.station(s).received_count, n)
            )


def test_all_stations_converge_to_latest_desired():
    """Across out-of-order delivery, every registered station ends up holding
    the latest price transmitted to it (none left without its update)."""
    for seed in (2, 4, 8, 16, 32):
        sim = nrvv_env.Simulation.from_seed(
            seed, num_stations=5, num_events=40, price_min=1, price_max=20
        )
        events = list(sim.pending_events)
        sim.connect(_build_server)
        sim.run(max_steps=500000)
        assert sim.quiescent()
        expected = _latest_desired(events)
        delivered_stations = {s for (s, _p) in sim.delivered}
        for s, p in expected.items():
            assert s in delivered_stations, (
                "registered station %r received no update" % (s,)
            )
            assert sim.applied(s) == p
