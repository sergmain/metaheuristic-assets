"""Server side of the GASV3ACC2 gas-price reconciliation system.

The server holds, per station, three values: the latest desired price, a mirror
of the price most recently acknowledged by that station, and an outstanding
flag. All reconciliation state lives here; stations are dumb appliers.

A send is permissible for a station exactly when it has no outstanding update
and its latest desired price differs from its last acknowledged value. At most
one update per station is outstanding at any time, so prices that arrive while
an update is in flight simply overwrite the latest-desired slot (coalescing).
"""


class _StationState(object):
    """Per-station reconciliation record."""

    __slots__ = ("latest_desired", "last_acknowledged", "outstanding",
                 "_outstanding_value")

    def __init__(self):
        self.latest_desired = None
        self.last_acknowledged = None     # sentinel: nothing acknowledged yet
        self.outstanding = False
        self._outstanding_value = None


class Server(object):
    """Reconciliation server wired to an outbound transmit port."""

    def __init__(self, transmit):
        self._transmit = transmit
        self._stations = {}

    def _state(self, station):
        st = self._stations.get(station)
        if st is None:
            st = _StationState()
            self._stations[station] = st
        return st

    def _maybe_emit(self, station, st):
        """Emit the latest desired price if a send is permissible."""
        if st.outstanding:
            return
        if st.latest_desired == st.last_acknowledged:
            return
        st.outstanding = True
        st._outstanding_value = st.latest_desired
        self._transmit(station, st.latest_desired)

    def submit_desired_price(self, station, price):
        st = self._state(station)
        st.latest_desired = price
        self._maybe_emit(station, st)

    def acknowledgement_received(self, station):
        st = self._state(station)
        if st.outstanding:
            st.last_acknowledged = st._outstanding_value
            st.outstanding = False
            st._outstanding_value = None
        self._maybe_emit(station, st)

    def get_station_state(self, station):
        st = self._state(station)
        return {
            "latest_desired": st.latest_desired,
            "last_acknowledged": st.last_acknowledged,
            "outstanding": st.outstanding,
        }
