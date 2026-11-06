import app
from nrvv_env import Simulation, price_at_send_violations

SEEDS = (0, 1, 2, 3, 4)
STATION = 'S1'


def _server_factory(send_price_update):
    for value in vars(app).values():
        if isinstance(value, type) and hasattr(value, 'set_desired_price'):
            return value(send_price_update)
    raise AssertionError('app defines no server class with set_desired_price')


def test_superseded_price_is_never_sent():
    for seed in SEEDS:
        # duration=0: no random central price changes, so only the scripted ones below happen
        sim = Simulation(seed, _server_factory, duration=0)
        server = sim.server

        # P0 occupies the in-flight slot for the station, so P1 stays pending
        server.set_desired_price(STATION, 'P0')
        server.set_desired_price(STATION, 'P1')
        # P1 is replaced by a newer desired price before any update carrying it is sent
        server.set_desired_price(STATION, 'P2')

        # the acknowledgement of P0 triggers the send step for the station
        sim.run_until_idle()

        sent = [s.price for s in sim.sends if s.station == STATION]
        assert 'P1' not in sent, f'seed {seed}: superseded price P1 was sent, sends={sent}'
        assert 'P2' in sent, f'seed {seed}: newer price P2 was never sent, sends={sent}'
        assert not price_at_send_violations(sim), f'seed {seed}: price at send mismatch'
