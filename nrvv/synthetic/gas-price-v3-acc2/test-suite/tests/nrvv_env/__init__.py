"""nrvv_env: a seeded, deterministic simulation of the *environment* around the
server side `app` described by the GASV3ACC2 interface.

The server side (module `app`) is NOT implemented here. This package simulates
everything *outside* it:

  * the price-producing clients            (GASV3ACC2-20)
  * the server-to-station transport        (GASV3ACC2-21, GASV3ACC2-22)
  * the dumb stations                      (GASV3ACC2-24)
  * the observation surface for tests      (GASV3ACC2-23)

A test imports `app`, wires `app`'s outbound transmit port (GASV3ACC2-16) to a
`Simulation`, hands the server to the simulation, drives it step by step until
nothing is in flight, and observes the clients and the traffic.

This package never imports `app`; it only calls the inbound operations the
Interface names (submit-desired-price, acknowledgement-received,
get-station-state) and receives calls on the outbound transmit port.
"""

from .simulation import Simulation, Station, Update, build

__all__ = ["Simulation", "Station", "Update", "build"]
