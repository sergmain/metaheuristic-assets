import app
import nrvv_env


def _settle(sim):
    """Drive the environment until every event is submitted and nothing is in
    flight, then assert the run really did come to rest."""
    sim.run()
    assert sim.quiescent()


def test_resubmitting_equal_price_emits_a_single_update():
    # Latest desired equals most-recently-acknowledged after the first update
    # settles; every further submit of the same value must be suppressed.
    # Holds for every transport ordering the seeds produce.
    for seed in (0, 1, 2, 7, 13, 99):
        events = [("S0", 42), ("S0", 42), ("S0", 42)]
        sim = nrvv_env.Simulation(events, seed=seed)
        sim.connect(app.Server)
        _settle(sim)
        assert sim.sent == [("S0", 42)]


def test_divergence_emits_exactly_one_update_with_latest_desired():
    # A station settled at 10 then asked for 20 is diverged: the server must
    # emit exactly one update carrying the latest desired value (20).
    for seed in (0, 1, 2, 7, 13, 99):
        events = [("S0", 10), ("S0", 20)]
        sim = nrvv_env.Simulation(events, seed=seed)
        sim.connect(app.Server)
        _settle(sim)
        carrying_latest = [p for (s, p) in sim.sent if s == "S0" and p == 20]
        assert carrying_latest == [20]        # exactly one, carrying 20
        assert sim.sent[-1] == ("S0", 20)      # the latest desired is what lands
        assert sim.applied("S0") == 20


def test_resubmitting_a_settled_changed_price_is_suppressed():
    # After converging to 20, re-submitting 20 (now equal to the acknowledged
    # value) emits nothing extra: still exactly one send carries 20.
    for seed in (0, 1, 2, 7, 13, 99):
        events = [("S0", 10), ("S0", 20), ("S0", 20)]
        sim = nrvv_env.Simulation(events, seed=seed)
        sim.connect(app.Server)
        _settle(sim)
        prices = [p for (s, p) in sim.sent if s == "S0"]
        assert prices.count(20) == 1
        assert sim.sent[-1] == ("S0", 20)
        for a, b in zip(prices, prices[1:]):
            assert a != b


def test_equal_then_new_value_resumes_emission():
    # The duplicate 10 is suppressed (equal to desired/acked) while a genuinely
    # new value 20 still triggers exactly one emission: send log is [10, 20].
    for seed in (0, 1, 2, 5, 8, 21):
        events = [("S0", 10), ("S0", 10), ("S0", 20)]
        sim = nrvv_env.Simulation(events, seed=seed)
        sim.connect(app.Server)
        _settle(sim)
        assert [p for (s, p) in sim.sent if s == "S0"] == [10, 20]


def test_no_station_ever_receives_two_consecutive_equal_prices():
    # General property across rich, seeded runs. Because at most one update per
    # station is outstanding and an emission requires desired != last-acked,
    # every re-emission for a station must differ from the value it most
    # recently acknowledged (== its previous emitted-and-acked value). A small
    # price range forces frequent collisions that must be suppressed.
    for seed in range(12):
        sim = nrvv_env.Simulation.from_seed(
            seed, num_stations=3, num_events=25, price_min=1, price_max=4
        )
        sim.connect(app.Server)
        _settle(sim)
        per_station = {}
        for s, p in sim.sent:
            per_station.setdefault(s, []).append(p)
        for s, prices in per_station.items():
            for a, b in zip(prices, prices[1:]):
                assert a != b, (seed, s, prices)
