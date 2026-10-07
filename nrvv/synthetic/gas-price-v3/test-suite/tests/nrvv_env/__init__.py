"""nrvv_env: a deterministic simulation of the Environment for the server-side
``app`` described by GASV3DEV3-11..18.

This package simulates only the ENVIRONMENT (the scripted clients and the
transport between them and the server). It never imports ``app``. A test
imports ``app``, hands the server object (and the outbound ``send-update``
port) to this package, and drives the simulation step by step.

Ports, as named by the Interface:
  * outbound ``send-update(station, price)``  -> ``Simulation.outbound``
       (the server invokes this; we observe and enqueue toward the station)
  * inbound ``submit-desired-price(station, price)`` -> we call it on the server
  * inbound ``acknowledge(station)``           -> we call it on the server
  * query  ``inspect-station(station)``        -> ``Simulation.inspect``
"""

from .environment import (
    Simulation,
    Update,
    Ack,
    random_script,
    UNKNOWN,
)

__all__ = [
    "Simulation",
    "Update",
    "Ack",
    "random_script",
    "UNKNOWN",
]
