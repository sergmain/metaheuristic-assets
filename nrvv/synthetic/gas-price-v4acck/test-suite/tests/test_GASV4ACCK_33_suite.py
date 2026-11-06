import app
import nrvv_env
from nrvv_env import Simulation

STATION = 'S-1'
NEWER = '1.99'
OLDER = '1.89'
SEEDS = (1, 2, 3, 4, 5)


def _make_server():
    candidates = [
        cls for cls in vars(app).values()
        if isinstance(cls, type)
        and all(hasattr(cls, m) for m in ('tick', 'set_latest_price', 'acknowledgement_received', 'get_station_view'))
    ]
    assert len(candidates) == 1, candidates
    return candidates[0]()


def _field(view, *names):
    for name in names:
        if isinstance(view, dict) and name in view:
            return view[name]
        if hasattr(view, name):
            return getattr(view, name)
    raise AssertionError(f'station view has none of {names}: {view!r}')


def test_latest_price_wins_when_older_price_arrives_last():
    for seed in SEEDS:
        sim = Simulation(seed, [STATION], changes_per_station=(1, 1))
        server = sim.bind(_make_server())
        sim._heap.clear()  # drop the seeded random change; this test sets the sequence itself
        sim._push(1, 'change', (STATION, NEWER))
        sim._push(2, 'change', (STATION, OLDER))
        sim.run_to_end()
        assert [c.price for c in sim.changes] == [NEWER, OLDER]
        latest = _field(server.get_station_view(STATION), 'latest_price', 'latest')
        assert latest == NEWER, f'seed {seed}: latest price {latest!r}'
        assert latest != OLDER
