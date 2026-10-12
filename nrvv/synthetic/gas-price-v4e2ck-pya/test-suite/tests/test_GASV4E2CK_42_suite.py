import app
from nrvv_env import Simulation

SERVER_OPS = ('set_desired_price', 'receive_ack', 'advance_time', 'query_station')


def _server_factory(send_update):
    if all(callable(getattr(app, m, None)) for m in SERVER_OPS):
        return app
    for name in sorted(vars(app)):
        cls = getattr(app, name)
        if isinstance(cls, type) and all(callable(getattr(cls, m, None)) for m in SERVER_OPS):
            try:
                return cls(send_update)
            except TypeError:
                return cls()
    raise AssertionError('app provides no server with the four operations')


def _simulation(changes=()):
    # Downlink loss 1.0: no update reaches a station, so no automatic acknowledgement
    # is produced and the test alone decides when each acknowledgement is sent.
    # Transmissions are still recorded in sim.transmissions.
    return Simulation(
        seed=42, server=_server_factory, stations=['S1', 'S2'],
        changes=list(changes), loss_downlink=1.0, loss_uplink=0.0,
    )


def _outstanding(sim, station):
    count = sim.outstanding(station)
    assert count is not None, 'QueryStation result has no recognisable outstanding count'
    return count


def _sent_prices(sim, station, start):
    # The 30-second check retransmits each outstanding record in queue order, so the
    # prices retransmitted reveal which records remain and in what order.
    return [tx.price for tx in sim.transmissions[start:] if tx.station == station]


def test_ack_pops_oldest_record_fifo_and_ignores_unknown_station():
    sim = _simulation(changes=[(1, 'S1', 1), (1, 'S1', 2), (1, 'S1', 3)])
    sim.run(1)
    assert _outstanding(sim, 'S1') == 3

    sim.server.receive_ack('S1')
    assert _outstanding(sim, 'S1') == 2
    mark = len(sim.transmissions)
    sim.run(35)
    assert _sent_prices(sim, 'S1', mark) == [2, 3]

    sim.server.receive_ack('S1')
    assert _outstanding(sim, 'S1') == 1
    mark = len(sim.transmissions)
    sim.run(35)
    assert _sent_prices(sim, 'S1', mark) == [3]

    sim.server.receive_ack('S2')  # S2 has no outstanding records: ignored
    assert _outstanding(sim, 'S2') == 0
    assert _outstanding(sim, 'S1') == 1


def test_ack_with_no_outstanding_record_is_ignored_and_not_banked():
    sim = _simulation(changes=[(1, 'S1', 1), (1, 'S1', 2), (1, 'S1', 3)])
    sim.server.receive_ack('S1')  # nothing outstanding yet: ignored
    assert _outstanding(sim, 'S1') == 0

    sim.run(1)
    assert _outstanding(sim, 'S1') == 3

    sim.server.receive_ack('S1')
    assert _outstanding(sim, 'S1') == 2
    mark = len(sim.transmissions)
    sim.run(35)
    assert _sent_prices(sim, 'S1', mark) == [2, 3]
