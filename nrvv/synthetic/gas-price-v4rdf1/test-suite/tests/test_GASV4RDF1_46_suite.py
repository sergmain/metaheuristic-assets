import inspect
import app as app_module
import nrvv_env

STATIONS = ['A', 'B', 'C']
SEEDS = (1, 2, 3, 4, 5)
MAX_STEPS = 100000


def _make_server(send_update, send_pricing_notice):
    servers = [obj for obj in vars(app_module).values()
               if inspect.isclass(obj) and callable(getattr(obj, 'set_desired_price', None))]
    assert servers, 'app has no server class with set_desired_price'
    return servers[0](send_update, send_pricing_notice)


def _run(seed, script=None):
    sim = nrvv_env.Simulation(seed, _make_server, STATIONS, script=script)
    sim.run(max_steps=MAX_STEPS)
    return sim


def test_every_update_sent_carries_the_current_desired_price():
    for seed in SEEDS:
        sim = _run(seed)
        assert sim.sent
        for sent in sim.sent:
            assert isinstance(sent.price, int)
            assert sent.price == sim.desired_at(sent.station, sent.step)


def test_every_acknowledgement_read_carries_a_price():
    for seed in SEEDS:
        sim = _run(seed)
        assert sim.delivered_acks
        sent_by_id = {sent.update_id: sent for sent in sim.sent}
        for ack in sim.delivered_acks:
            assert isinstance(ack.price, int)
            assert ack.price == sent_by_id[ack.update_id].price


def test_stations_accept_every_update_and_display_its_price():
    for seed in SEEDS:
        sim = _run(seed)
        assert len(sim.delivered_updates) == len(sim.sent)
        assert (sorted(u.update_id for u in sim.delivered_updates)
                == sorted(s.update_id for s in sim.sent))
        for name in STATIONS:
            delivered = [u for u in sim.delivered_updates if u.station == name]
            if delivered:
                assert sim.displayed(name) == delivered[-1].price


def test_acks_are_read_in_the_order_the_station_produced_them():
    for seed in SEEDS:
        sim = _run(seed)
        for name in STATIONS:
            produced = [u.update_id for u in sim.delivered_updates if u.station == name]
            read = [a.update_id for a in sim.delivered_acks if a.station == name]
            assert read == produced


def test_server_adds_no_extra_fields_to_station_traffic():
    for seed in SEEDS:
        sim = _run(seed)
        assert sim.quiet
        for sent in sim.sent:
            assert sent.station in STATIONS
            assert isinstance(sent.price, int)


def test_repeated_desired_prices_on_one_station_are_each_priced():
    script = [[('A', 10), ('A', 20), ('A', 30)], [('A', 40)]]
    sim = _run(1, script=script)
    assert sim.sent
    for sent in sim.sent:
        assert isinstance(sent.price, int)
        assert sent.price in {10, 20, 30, 40}
    assert sim.displayed('A') == sim.delivered_updates[-1].price


def test_same_seed_gives_identical_traffic():
    for seed in SEEDS[:3]:
        first = _run(seed)
        second = _run(seed)
        assert first.sent == second.sent
        assert first.delivered_acks == second.delivered_acks
