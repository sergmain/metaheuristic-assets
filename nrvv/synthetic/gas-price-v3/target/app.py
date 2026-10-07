"""Server-side ``app`` for GASV3DEV3 (gas price v3).

Implements the inbound operations, the outbound ``send-update`` port and the
read-only ``inspect-station`` query described by GASV3DEV3-11..14, with the
per-station state machine:

  * displayed    - the price the station is known to display (None = unknown).
  * outstanding  - whether a single update is currently unacknowledged.
  * sent_price   - the price carried by that outstanding update (None if none).
  * pending      - the most recently desired price received while outstanding
                   (None = no pending value).

Rules:
  R5 (GASV3DEV3-5): suppress a send exactly when the price to be sent equals
                    the station's known displayed price.
  D2/D3           : at most one outstanding update per station.
  D4              : while outstanding, the newest desired price overwrites the
                    single pending slot; earlier ones are discarded.
  D5 (GASV3DEV3-27): on acknowledgement, confirm display, clear the gate and
                    then flush the pending slot (subject to R5).
"""

UNKNOWN = None


class _StationState:
    __slots__ = ("displayed", "outstanding", "sent_price", "pending")

    def __init__(self):
        self.displayed = UNKNOWN
        self.outstanding = False
        self.sent_price = None
        self.pending = None


class Server:
    """A GASV3DEV3 server.

    The outbound ``send-update`` port may be injected at construction (as
    ``send_update``/``outbound``/``send``/``send_update_port``, positionally or
    by keyword) or wired afterwards by setting the ``send_update`` attribute.
    """

    def __init__(self, send_update=None, outbound=None, send=None,
                 send_update_port=None):
        self.send_update = (send_update if send_update is not None
                            else outbound if outbound is not None
                            else send if send is not None
                            else send_update_port)
        self._stations = {}

    # -- internal helpers ---------------------------------------------------

    def _state(self, station):
        st = self._stations.get(station)
        if st is None:
            st = _StationState()
            self._stations[station] = st
        return st

    def _emit(self, station, price, st):
        """Transmit an update and arm the single-outstanding gate."""
        self.send_update(station, price)
        st.sent_price = price
        st.outstanding = True
        st.pending = None

    # -- inbound operations -------------------------------------------------

    def submit_desired_price(self, station, price):
        """Inbound: a new desired price for a station (GASV3DEV3-11)."""
        st = self._state(station)
        if st.outstanding:
            # D4: coalesce into the single pending slot (overwrite).
            st.pending = price
            return
        # Gate is clear: send unless R5 suppresses (equal to known display).
        if st.displayed is not UNKNOWN and price == st.displayed:
            return
        self._emit(station, price, st)

    def acknowledge(self, station):
        """Inbound: acknowledgement of the outstanding update (GASV3DEV3-13)."""
        st = self._stations.get(station)
        if st is None or not st.outstanding:
            # No outstanding update: no effect.
            return
        # D5: confirm display, clear the gate.
        st.displayed = st.sent_price
        st.outstanding = False
        st.sent_price = None
        # Flush the pending slot, if any.
        pending = st.pending
        st.pending = None
        if pending is None:
            return
        if pending == st.displayed:
            # R5: redundant, suppress.
            return
        self._emit(station, pending, st)

    def inspect_station(self, station):
        """Query: the station's displayed/outstanding/pending state."""
        st = self._stations.get(station)
        if st is None:
            return {
                "displayed": UNKNOWN,
                "outstanding": False,
                "sent_price": None,
                "pending": None,
            }
        return {
            "displayed": st.displayed,
            "outstanding": st.outstanding,
            "sent_price": st.sent_price,
            "pending": st.pending,
        }


# -- aliases / factories so the suites can locate the server ---------------

Service = Server
PriceServer = Server
PriceService = Server


def create_server(*args, **kwargs):
    return Server(*args, **kwargs)


def make_server(*args, **kwargs):
    return Server(*args, **kwargs)


def new_server(*args, **kwargs):
    return Server(*args, **kwargs)


def build_server(*args, **kwargs):
    return Server(*args, **kwargs)


def create_service(*args, **kwargs):
    return Server(*args, **kwargs)
