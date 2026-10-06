# N-1 - Gas stations settle on the latest price

The synthetic NEED of NRVV v2 (plan 043, decision 10): one NEED reduced from the interview "Situation" - the cost
framing dropped; in-flight updates, out-of-order delivery, in-order acknowledgements, dumb stations, the eventual latest
price and no unnecessary updates kept. A DEFINITION run on an RG project holding it is the gas-price run of plan 043,
Phase 13; the code that answers it lands under `target/` (module `app`, written by the implementation run) and the client
simulation under `test-suite/tests/nrvv_env/` (written by the test-author run).

Title: Gas stations settle on the latest price

Statement:

A central service publishes gas price updates to gas stations. A new desired price for a station can arrive while
earlier updates to that station are still in flight. Updates can reach a station out of order; acknowledgements come
back to the service in order. A station displays the last price it received and cannot be changed in any way. Every
station must end up displaying the latest desired price for it, and the service must avoid sending unnecessary updates.
