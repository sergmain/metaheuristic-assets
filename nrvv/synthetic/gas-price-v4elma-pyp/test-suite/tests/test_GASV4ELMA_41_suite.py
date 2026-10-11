# GASV4ELMA-41: a repeated price is not resent; a changed price is sent once.
import app
from nrvv_env import Simulation

STATION = 'station-1'
SEEDS = (1, 7, 42)


def _quiet_simulation(seed):
    sim = Simulation(seed=seed, server_factory=lambda dispatch: app.Server(dispatch_update=dispatch),
                     stations=1, stop_time=0.0)
    sim.force_reachable(STATION, 0.0)
    sim.run_until(0.0)
    return sim


def _sends(sim):
    return [r for r in sim.trace if r.kind == 'dispatch' and r.station == STATION]


def test_repeated_price_is_not_resent_and_changed_price_is_sent_once():
    for seed in SEEDS:
        sim = _quiet_simulation(seed)
        assert sim.app.set_desired_price(STATION, '1.499') == 'Accepted'
        sim.run()
        acks = [r for r in sim.trace if r.kind == 'ack' and r.station == STATION]
        assert acks and acks[-1].price == '1.499'
        sent = _sends(sim)
        assert sent and sent[-1].price == '1.499'
        before = len(sent)

        assert sim.app.set_desired_price(STATION, '1.499') == 'Accepted'
        sim.run()
        assert len(_sends(sim)) == before

        assert sim.app.set_desired_price(STATION, '1.529') == 'Accepted'
        sim.run()
        new = _sends(sim)[before:]
        assert len(new) == 1 and new[0].price == '1.529'
