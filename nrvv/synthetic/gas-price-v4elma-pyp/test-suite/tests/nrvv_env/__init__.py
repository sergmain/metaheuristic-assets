"""nrvv_env: deterministic simulated environment around the server side `app`.

Test side::

    import app
    from nrvv_env import Simulation, check

    sim = Simulation(seed=7, server_factory=lambda dispatch: app.Server(dispatch_update=dispatch))
    sim.run()                      # or sim.step() / sim.run_until(t)
    assert not any(check(sim).values())
"""
from .oracle import check
from .sim import ACK_DELAY, PRICES, UPDATE_DELAY, Record, Simulation, Station

__all__ = ['ACK_DELAY', 'PRICES', 'UPDATE_DELAY', 'Record', 'Simulation', 'Station', 'check']
