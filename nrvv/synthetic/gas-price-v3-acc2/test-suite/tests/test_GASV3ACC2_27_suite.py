"""Suite for TEST_CASE GASV3ACC2-27 (requirement GASV3ACC2-2).

Criterion: for a given station, once the latest desired price has been
established and no newer desired price is subsequently produced, the system is
allowed to reach its settled end state; the price value last applied by that
station must then equal that latest desired price, regardless of any earlier
intermediate values that were applied.

Each test drives `app` only through `nrvv_env`:
  * wire the outbound transmit port (GASV3ACC2-16) to the simulation,
  * feed desired prices through submit-desired-price (GASV3ACC2-17),
  * let the transport deliver/acknowledge (GASV3ACC2-18) until quiescent,
  * then observe the station's last applied value (GASV3ACC2-23/-19).

All nondeterminism flows through one seeded RNG, so every run is reproducible.
"""

import nrvv_env


# --------------------------------------------------------------------------
# Wiring / observation helpers (drive `app` only through nrvv_env).
# --------------------------------------------------------------------------

def _build(sim):
    """Construct the server with its transmit port wired to `sim`, and bind it.

    The documented convention is ``app.Server(sim.transmit)`` (see the
    nrvv_env docstring). A few tolerant fallbacks are tried so the suite pins
    the behaviour under test rather than one exact constructor spelling.
    """
    import app

    # Preferred: a factory/class taking the transmit callable positionally.
    for name in ("Server", "PriceServer", "ReconciliationServer", "Service",
                 "create_server", "make_server", "build_server", "new_server",
                 "server"):
        factory = getattr(app, name, None)
        if factory is None:
            continue
        try:
            return sim.connect(factory)
        except TypeError:
            pass
        # Try no-arg construction + explicit wiring of the outbound port.
        try:
            obj = factory()
        except Exception:
            continue
        if _wire(obj, sim.transmit):
            sim.bind(obj)
            return obj

    raise AssertionError("could not construct the `app` server with a "
                         "transmit port wired to the simulation")


def _wire(obj, transmit):
    for name in ("transmit", "transmit_port", "outbound", "send", "emit",
                 "on_transmit", "transmit_update"):
        if hasattr(obj, name):
            try:
                setattr(obj, name, transmit)
                return True
            except Exception:
                pass
    for name in ("set_transmit", "bind_transmit", "set_outbound", "set_port",
                 "wire", "connect"):
        fn = getattr(obj, name, None)
        if callable(fn):
            try:
                fn(transmit)
                return True
            except Exception:
                pass
    return False


def _latest_desired(events):
    """The last desired price submitted per station (the latest desired)."""
    latest = {}
    for station, price in events:
        latest[station] = price
    return latest


def _settle(sim):
    """Drive the environment to its settled end state and assert it reached it.

    A generous step bound guards against a server that never settles (e.g. one
    that re-emits forever): the run stops and the quiescence assertion then
    surfaces the failure instead of hanging.
    """
    sim.run(max_steps=200000)
    assert sim.quiescent(), (
        "environment did not reach a settled end state: "
        "pending=%r in_flight=%r" % (sim.pending_events, sim.in_flight))


def _assert_each_station_settled_on_latest(sim, events):
    latest = _latest_desired(events)
    for station, price in latest.items():
        assert sim.applied(station) == price, (
            "station %r last applied %r but latest desired was %r"
            % (station, sim.applied(station), price))


# Fixed seeds drive transport interleaving; several per property.
SEEDS = (0, 1, 2, 3, 5, 7, 13, 42)


# --------------------------------------------------------------------------
# Tests -- every one checks the GASV3ACC2-27 criterion.
# --------------------------------------------------------------------------

def test_single_station_last_applied_equals_latest_desired():
    events = [("S0", 11), ("S0", 22), ("S0", 33), ("S0", 44)]
    for seed in SEEDS:
        sim = nrvv_env.Simulation(events, seed=seed)
        _build(sim)
        _settle(sim)
        assert sim.applied("S0") == 44


def test_each_station_settles_on_its_own_latest_desired():
    events = [
        ("A", 10), ("B", 5), ("A", 20), ("C", 7),
        ("B", 50), ("A", 30), ("C", 70), ("B", 60),
        ("A", 99), ("C", 71),
    ]
    for seed in SEEDS:
        sim = nrvv_env.Simulation(events, seed=seed)
        _build(sim)
        _settle(sim)
        # Latest desired: A->99, B->60, C->71.
        assert sim.applied("A") == 99
        assert sim.applied("B") == 60
        assert sim.applied("C") == 71
        _assert_each_station_settled_on_latest(sim, events)


def test_latest_wins_over_earlier_intermediate_applied_values():
    # A burst to one station so that, depending on interleaving, one or more
    # earlier (intermediate) values may be applied before the latest. The end
    # state must still be the latest desired regardless.
    events = [("X", 1), ("X", 2), ("X", 3), ("X", 4), ("X", 5), ("X", 6)]
    observed_intermediate = False
    for seed in SEEDS:
        sim = nrvv_env.Simulation(events, seed=seed)
        _build(sim)
        _settle(sim)
        assert sim.applied("X") == 6
        # The modeled station overwrites its slot on every delivery; more than
        # one delivery means an intermediate value was applied at some point.
        if sim.station("X").received_count > 1:
            observed_intermediate = True
    # Across the seeds at least one run applies an intermediate before settling,
    # confirming "regardless of earlier intermediate values" is exercised.
    assert observed_intermediate


def test_repeated_final_price_still_settles_on_latest():
    # The latest desired coincides with an earlier value; settlement must still
    # land on that value and nothing must remain in flight.
    events = [("S", 40), ("S", 80), ("S", 40), ("T", 9), ("T", 9)]
    for seed in SEEDS:
        sim = nrvv_env.Simulation(events, seed=seed)
        _build(sim)
        _settle(sim)
        assert sim.applied("S") == 40
        assert sim.applied("T") == 9


def test_generated_sequences_settle_on_latest_desired():
    for seed in (1, 2, 3, 7, 11, 42):
        sim = nrvv_env.Simulation.from_seed(seed, num_stations=3, num_events=25)
        events = list(sim.pending_events)   # full producer sequence, pre-run
        _build(sim)
        _settle(sim)
        _assert_each_station_settled_on_latest(sim, events)


def test_server_state_reports_settled_latest():
    # Cross-check the server's own observation surface (GASV3ACC2-19): at the
    # settled end state the last-acknowledged mirror equals the latest desired
    # and nothing is outstanding -- consistent with the station's applied value.
    events = [
        ("A", 15), ("B", 3), ("A", 25), ("B", 33),
        ("A", 35), ("B", 44), ("A", 55),
    ]
    for seed in SEEDS:
        sim = nrvv_env.Simulation(events, seed=seed)
        server = _build(sim)
        _settle(sim)
        latest = _latest_desired(events)
        for station, price in latest.items():
            assert sim.applied(station) == price
            state = server.get_station_state(station)
            desired, last_ack, outstanding = _state_fields(state)
            assert last_ack == price
            assert desired == price
            assert not outstanding


def _state_fields(state):
    """Extract (latest-desired, last-acknowledged, outstanding) tolerantly.

    GASV3ACC2-19 returns {latest desired, last acknowledged, outstanding flag}.
    Accept a dict, an attribute-bearing object / namedtuple, or a positional
    triple in the interface's listed order.
    """
    desired_names = ("latest_desired", "latest_desired_price", "desired",
                     "desired_price", "latest")
    ack_names = ("last_acknowledged", "last_acknowledged_price", "last_ack",
                 "acknowledged", "last_applied", "applied", "ack")
    out_names = ("outstanding", "outstanding_flag", "in_flight", "pending",
                 "has_outstanding", "inflight")

    def pick(names):
        if isinstance(state, dict):
            for n in names:
                if n in state:
                    return state[n], True
        for n in names:
            if hasattr(state, n):
                return getattr(state, n), True
        return None, False

    desired, ok_d = pick(desired_names)
    last_ack, ok_a = pick(ack_names)
    outstanding, ok_o = pick(out_names)
    if ok_d and ok_a and ok_o:
        return desired, last_ack, outstanding

    # Positional fallback: listed order is desired, last-acknowledged, flag.
    try:
        seq = list(state)
    except TypeError:
        seq = None
    if seq is not None and len(seq) >= 3:
        return seq[0], seq[1], seq[2]

    raise AssertionError(
        "get_station_state returned an unreadable shape: %r" % (state,))
