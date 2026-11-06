"""Price-update service (server side).

Implements the TMPGASDF1 interface: set-desired-price, send-update (outbound),
receive-acknowledgement and inspect. Per station the service keeps the latest
desired price, the known displayed price (advanced only by acknowledgement), and
at most one outstanding (sent-but-unacknowledged) update. On each evaluation it
sends exactly one update when a desired price is set, nothing is outstanding, and
that desired price differs from the known displayed price.
"""


class _StationState:
    __slots__ = ("latest_desired", "known_displayed",
                 "outstanding_price", "outstanding_id", "next_id")

    def __init__(self):
        self.latest_desired = None
        self.known_displayed = None
        self.outstanding_price = None
        self.outstanding_id = None
        self.next_id = 1


class Service:
    def __init__(self, send_update):
        self._send_update = send_update
        self._stations = {}

    def _state(self, station):
        st = self._stations.get(station)
        if st is None:
            st = _StationState()
            self._stations[station] = st
        return st

    def set_desired_price(self, station, price):
        st = self._state(station)
        st.latest_desired = price
        self._evaluate(station, st)

    def receive_acknowledgement(self, station, update_id):
        st = self._state(station)
        # Defensively ignore acknowledgements that do not match the outstanding
        # update (stale or duplicate).
        if st.outstanding_id is None or update_id != st.outstanding_id:
            return
        st.known_displayed = st.outstanding_price
        st.outstanding_price = None
        st.outstanding_id = None
        self._evaluate(station, st)

    def _evaluate(self, station, st):
        if st.latest_desired is None:
            return
        if st.outstanding_id is not None:
            return
        if st.latest_desired == st.known_displayed:
            return
        update_id = st.next_id
        st.next_id += 1
        price = st.latest_desired
        st.outstanding_price = price
        st.outstanding_id = update_id
        self._send_update(station, update_id, price)

    def inspect(self, station):
        st = self._state(station)
        return {
            "latest_desired": st.latest_desired,
            "known_displayed": st.known_displayed,
            "outstanding": st.outstanding_price,
        }
