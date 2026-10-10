import app
import nrvv_env

STATION = 'S1'
PRICES = ('100', '105', '110')


def _make_server(send_update, send_pricing_notice):
    for name, value in vars(app).items():
        if isinstance(value, type) and 'Server' in name:
            return value(send_update, send_pricing_notice)
    raise AssertionError('app defines no server class taking the two ports')


def _confirmed_and_outstanding(state):
    if isinstance(state, dict):
        confirmed, outstanding = state['confirmed'], state['outstanding']
    elif hasattr(state, 'confirmed'):
        confirmed, outstanding = state.confirmed, state.outstanding
    else:
        confirmed, _desired, outstanding = state
    if not isinstance(outstanding, int):
        outstanding = len(outstanding)
    return confirmed, outstanding


def _deliver_next_update(sim):
    delivered = len(sim.delivered_updates)
    sim._deliver_update()
    assert len(sim.delivered_updates) == delivered + 1


def _deliver_next_ack(sim):
    delivered = len(sim.delivered_acks)
    sim._deliver_ack()
    assert len(sim.delivered_acks) == delivered + 1


def test_acks_retire_oldest_update_and_set_confirmed_price_in_arrival_order():
    sim = nrvv_env.Simulation(seed=52, make_server=_make_server, stations=[STATION], script=[])
    server = sim.server

    # Enqueue U1, U2, U3 in that order; each is delivered to the station at once,
    # so the station holds the acknowledgements in the same order.
    for index, price in enumerate(PRICES):
        server.set_desired_price(STATION, price)
        assert len(sim.sent) == index + 1, 'server did not send one update per desired price'
        _deliver_next_update(sim)

    update_ids = [update.update_id for update in sim.sent]
    assert [update.price for update in sim.sent] == list(PRICES)
    confirmed, outstanding = _confirmed_and_outstanding(sim.query(STATION))
    assert outstanding == 3

    # Handle acknowledgements one at a time, checking the state after each.
    expected_remaining = (2, 1, 0)
    for index, price in enumerate(PRICES):
        _deliver_next_ack(sim)
        ack = sim.delivered_acks[-1]
        assert ack.price == price
        assert ack.update_id == update_ids[index]

        confirmed, outstanding = _confirmed_and_outstanding(sim.query(STATION))
        assert confirmed == price
        assert outstanding == expected_remaining[index]

    assert [ack.price for ack in sim.delivered_acks] == list(PRICES)
    assert [ack.update_id for ack in sim.delivered_acks] == update_ids
