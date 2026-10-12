'''Simulated environment for the price-update service under test.

The test imports the server side as ``app`` and passes it in through a factory
that receives the SendPriceUpdate port::

    sim = Simulation(seed, lambda send: app.Service(send))
    sim.run()

The oracles in ``oracles`` take a finished or running ``Simulation`` and return
lists of violations; an empty list means the check passed.
'''
from .simulation import (
    MAX_DELAY,
    AckDelivery,
    AckRecord,
    ChangeRecord,
    Delivery,
    ScriptedChange,
    SendRecord,
    Simulation,
    Station,
)
from .oracles import (
    change_trigger_violations,
    check_all,
    default_view,
    final_display_violations,
    redundant_send_violations,
    service_record_violations,
    superseded_send_violations,
)

__all__ = [
    'MAX_DELAY',
    'AckDelivery',
    'AckRecord',
    'ChangeRecord',
    'Delivery',
    'ScriptedChange',
    'SendRecord',
    'Simulation',
    'Station',
    'change_trigger_violations',
    'check_all',
    'default_view',
    'final_display_violations',
    'redundant_send_violations',
    'service_record_violations',
    'superseded_send_violations',
]
