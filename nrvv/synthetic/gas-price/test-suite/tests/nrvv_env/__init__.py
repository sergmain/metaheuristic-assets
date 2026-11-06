"""nrvv_env: a deterministic simulated Environment for the price-update service.

The system under test is the server side, the Python module ``app``. This package
never imports ``app``; a test imports ``app``, builds the server, and wires it to a
:class:`Simulation` instance.

Typical use::

    import app
    from nrvv_env import Simulation

    sim = Simulation(seed=1234)
    server = app.Service(sim.send_update)   # wire our outbound port into app
    sim.connect(server)                     # register the inbound operations
    sim.run()                               # drive until nothing is in flight

    # observe
    sim.send_log        # ordered send-update invocations
    sim.delivery_log    # updates delivered to stations
    sim.ack_log         # acknowledgements fed back to the service
    sim.displayed('S0') # a station's current displayed price
    server.inspect('S0')# the service's own view (read-only)
"""
from .simulation import (
    Simulation,
    Station,
    SendRecord,
    DeliveryRecord,
    AckRecord,
    InputRecord,
)

__all__ = [
    "Simulation",
    "Station",
    "SendRecord",
    "DeliveryRecord",
    "AckRecord",
    "InputRecord",
]
