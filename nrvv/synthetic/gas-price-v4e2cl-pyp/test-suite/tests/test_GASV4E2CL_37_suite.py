import app
from nrvv_env import Simulation, price_at_send_violations, repeat_violations

STATION = 'S1'
SEEDS = (1, 2, 3, 4, 5)


def _server_factory(send_price_update):
    classes = [
        obj for obj in vars(app).values()
        if isinstance(obj, type) and callable(getattr(obj, 'set_desired_price', None))
    ]
    assert classes, 'app provides no class with set_desired_price'
    cls = classes[0]
    try:
        return cls(send_price_update)
    except TypeError:
        return cls(send_price_update=send_price_update)


def _superseded_scenario(seed):
    sim = Simulation(seed, _server_factory, stations=(STATION,), duration=0)
    sim.server.set_desired_price(STATION, '10')
    while not sim.sends and sim.step():
        pass
    assert sim.sends, 'no price update was sent for the first desired price'
    sim.server.set_desired_price(STATION, '100')
    sim.server.set_desired_price(STATION, '150')
    sim.run_until_idle()
    return sim


def test_superseded_price_is_never_transmitted():
    for seed in SEEDS:
        sim = _superseded_scenario(seed)
        sent = [s.price for s in sim.sends if s.station == STATION]
        assert '150' in sent, f'seed {seed}: 150 never transmitted, sent {sent}'
        assert '100' not in sent, f'seed {seed}: superseded 100 transmitted, sent {sent}'


def test_transmitted_price_equals_desired_price_at_send():
    for seed in SEEDS:
        sim = _superseded_scenario(seed)
        assert not price_at_send_violations(sim), f'seed {seed}: {price_at_send_violations(sim)}'
        assert not repeat_violations(sim), f'seed {seed}: {repeat_violations(sim)}'
