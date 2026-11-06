import sys
sys.path.insert(0, 'C:/_mh/mhbp_home-PostgreSQL-disk-storage/nrvv/GASV4ELMA/pyp/188/139/test-suite/nrvv/synthetic/gas-price-v4elma-pyp/test-suite/tests')
import app
from nrvv_env import Simulation

sim = Simulation(seed=1, server_factory=lambda d: app.Server(dispatch_update=d), stations=3)
for s in sim.station_ids:
    sim.force_reachable(s, 0.0)
st = sim.price_schedule[-1][1]
print('last', sim.price_schedule[-1])
print('same station', [x for x in sim.price_schedule if x[1] == st][-3:])
sim.run()
print([ (r.time, r.station, r.seq, r.price) for r in sim.trace if r.kind == 'dispatch' and r.station == st][-4:])
