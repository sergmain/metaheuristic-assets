"""Test suite for GASV3ACC2-38.

Criterion: with a station whose latest desired price is fixed, acknowledging an
outstanding update triggers exactly one new outstanding update carrying the
latest desired price whenever that price differs from the last acknowledged
value, and sends nothing (stays idle) when the latest desired price equals the
last acknowledged value. Feeding the sent value back as each acknowledgement,
the sequence of sent updates converges so the acknowledged value becomes equal
to the latest desired price and no further update is sent, leaving the station
settled on the latest price.

Every test drives `app` only through `nrvv_env`.
"""

import app
import nrvv_env


# --------------------------------------------------------------------------
# Wiring / observation helpers (not tests -- names do not start with test_).
# --------------------------------------------------------------------------

def make_server(sim):
    """Build the server, wiring its outbound transmit port to `sim.transmit`.

    The interface's outbound port (GASV3ACC2-16) is injected into the server.
    We accept the natural factory shapes so the contract is not brittle about
    the exact spelling of the constructor/wiring entry point.
    """
    for name in ('Server', 'create_server', 'make_server', 'build_server',
                 'new_server'):
        factory = getattr(app, name, None)
        if factory is not None:
            return sim.connect(factory)
    # Module-level API variant: wire the port then drive `app` itself.
    for name in ('set_transmit', 'bind', 'configure', 'init', 'set_port',
                 'wire', 'connect'):
        fn = getattr(app, name, None)
        if callable(fn):
            fn(sim.transmit)
            sim.bind(app)
            return app
    if hasattr(app, 'submit_desired_price'):
        try:
            app.transmit = sim.transmit
        except Exception:
            pass
        sim.bind(app)
        return app
    raise RuntimeError('no way to construct/wire the server on module app')


def read_state(st):
    """Extract (latest_desired, last_acknowledged, outstanding) from whatever
    shape get-station-state (GASV3ACC2-19) returns: dict, object, namedtuple
    or a positional 3-tuple ordered as the interface lists them.
    """
    def pick(candidates):
        if isinstance(st, dict):
            for c in candidates:
                if c in st:
                    return st[c]
        for c in candidates:
            if hasattr(st, c):
                return getattr(st, c)
        raise KeyError(candidates)

    try:
        desired = pick(['latest_desired', 'latest_desired_price', 'desired',
                        'desired_price', 'latest', 'latest_price'])
        ack = pick(['last_acknowledged', 'last_acknowledged_price',
                    'last_acked', 'last_ack', 'acknowledged', 'acked',
                    'last_acknowledged_value'])
        outstanding = pick(['outstanding', 'outstanding_flag',
                            'has_outstanding', 'in_flight', 'pending'])
        return desired, ack, outstanding
    except KeyError:
        if isinstance(st, (tuple, list)) and len(st) == 3:
            return st[0], st[1], st[2]
        raise


def _drive_checking_ack_invariant(seed):
    """Drive a single-station run and check, at every acknowledgement, the
    ack-clocked re-send rule. Returns the number of re-sends triggered.
    """
    sim = nrvv_env.Simulation.from_seed(seed, num_stations=1, num_events=40)
    make_server(sim)

    latest = {}      # station -> latest desired price, tracked from submits
    resends = 0
    while True:
        before = len(sim.sent)
        action = sim.step()
        if action is None:
            break
        kind = action[0]
        if kind == 'submit':
            _, s, p = action
            latest[s] = p
        elif kind == 'ack':
            u = action[1]
            s = u.station
            delta = len(sim.sent) - before
            outstanding_for_s = [x for x in sim.in_flight if x.station == s]
            desired = latest[s]
            # The ack advanced last-acknowledged to the outstanding value u.price.
            if desired != u.price:
                # Diverged: exactly one new outstanding, carrying the latest
                # desired price and nothing else.
                assert delta == 1, (seed, 'expected one re-send', delta)
                assert sim.sent[-1] == (s, desired), (seed, sim.sent[-1], desired)
                assert len(outstanding_for_s) == 1, (seed, outstanding_for_s)
                assert outstanding_for_s[0].price == desired
                resends += 1
            else:
                # Converged: stay idle, send nothing, leave no outstanding.
                assert delta == 0, (seed, 'expected idle', delta)
                assert outstanding_for_s == [], (seed, outstanding_for_s)
    assert sim.quiescent()
    return resends


# --------------------------------------------------------------------------
# Tests.
# --------------------------------------------------------------------------

def test_single_submit_settles_in_one_round():
    # One desired price, nothing diverged afterwards: a single update is sent,
    # and once its ack arrives the station is settled with nothing more sent.
    sim = nrvv_env.Simulation([('A', 50)])
    make_server(sim)
    sim.run()

    assert sim.sent == [('A', 50)]          # exactly one update emitted
    assert sim.delivered == [('A', 50)]
    assert sim.acknowledged == [('A', 50)]
    assert sim.in_flight == []
    assert sim.applied('A') == 50

    desired, ack, outstanding = read_state(sim.get_station_state('A'))
    assert desired == 50
    assert ack == 50
    assert not outstanding


def test_ack_resends_latest_when_diverged_and_idle_when_converged():
    # Across many orderings, every acknowledgement either re-sends exactly the
    # latest desired price (when it differs from the newly acknowledged value)
    # or stays idle (when they are equal). Aggregate across seeds must include
    # real re-sends so the property is not vacuously satisfied.
    total_resends = 0
    for seed in [1, 2, 3, 5, 8, 13, 21]:
        total_resends += _drive_checking_ack_invariant(seed)
    assert total_resends > 0


def test_run_converges_and_settles_on_latest_price():
    # Driving to quiescence, the acknowledged value converges to the latest
    # desired price and no update remains outstanding.
    for seed in [1, 2, 3, 7, 42]:
        sim = nrvv_env.Simulation.from_seed(seed, num_stations=1, num_events=25)
        make_server(sim)
        events = list(sim.pending_events)       # full producer sequence
        sim.run()

        assert sim.quiescent()
        assert sim.in_flight == []

        finals = {}
        for s, p in events:
            finals[s] = p                       # last desired per station

        for s, final_price in finals.items():
            desired, ack, outstanding = read_state(sim.get_station_state(s))
            assert desired == final_price
            assert ack == final_price            # acknowledged caught up
            assert not outstanding               # no further update in flight
            assert sim.applied(s) == final_price # station settled on latest
            assert sim.acknowledged[-1] == (s, final_price)


def test_multi_station_runs_settle_on_latest_price():
    # The same convergence holds independently per station when several share
    # the transport.
    for seed in [4, 11, 99]:
        sim = nrvv_env.Simulation.from_seed(seed, num_stations=3, num_events=40)
        make_server(sim)
        events = list(sim.pending_events)
        sim.run()

        assert sim.quiescent()
        assert sim.in_flight == []

        finals = {}
        for s, p in events:
            finals[s] = p

        for s, final_price in finals.items():
            desired, ack, outstanding = read_state(sim.get_station_state(s))
            assert desired == final_price
            assert ack == final_price
            assert not outstanding
            assert sim.applied(s) == final_price
