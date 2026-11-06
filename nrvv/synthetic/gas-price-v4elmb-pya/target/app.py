'''Server side of the desired-price protocol.

Each station has at most one update in flight: the latest one sent. An update
is acknowledged once its own acknowledgement and an acknowledgement of an
earlier update have both been received, so an acknowledgement alone for the
later update does not clear it. Unacknowledged updates are retransmitted with
the same sequence number and price, on a doubling timeout measured in ticks.
'''

BASE_TIMEOUT = 4    # ticks before the first retransmission
MAX_TIMEOUT = 32    # ceiling for the doubling timeout


class _Station:
    def __init__(self):
        self.desired = None
        self.shown = None           # price of the last acknowledged update
        self.next_seq = 1
        self.in_flight = False
        self.sent_seq = None        # sequence number of the latest update sent
        self.sent_price = None
        self.sent_at = 0            # tick of the latest transmission
        self.timeout = BASE_TIMEOUT
        self.latest_acked = False   # acknowledgement of sent_seq received
        self.earlier_acked = False  # acknowledgement of a lower sequence received


class Service:
    def __init__(self, send_price_update):
        self._send = send_price_update
        self._stations = {}
        self._now = 0

    def _state(self, station):
        if station not in self._stations:
            self._stations[station] = _Station()
        return self._stations[station]

    def set_desired_price(self, station, price):
        st = self._state(station)
        st.desired = price
        if st.in_flight:
            if price == st.sent_price:
                return
        elif price == st.shown:
            return
        self._send_update(station, st, price)

    def _send_update(self, station, st, price):
        # Acknowledgements received for the previous update count as earlier ones for the new one.
        st.earlier_acked = (st.earlier_acked or st.latest_acked) if st.in_flight else False
        st.latest_acked = False
        st.in_flight = True
        st.sent_seq = st.next_seq
        st.next_seq += 1
        st.sent_price = price
        st.sent_at = self._now
        st.timeout = BASE_TIMEOUT
        self._send(station, st.sent_seq, price)

    def ack_received(self, station, seq):
        st = self._state(station)
        if not st.in_flight:
            return
        if seq == st.sent_seq:
            st.latest_acked = True
        elif seq < st.sent_seq:
            st.earlier_acked = True
        if st.latest_acked and st.earlier_acked:
            st.shown = st.sent_price
            st.in_flight = False
            st.timeout = BASE_TIMEOUT

    def tick(self, now):
        self._now = now
        for station, st in list(self._stations.items()):
            if st.in_flight and now - st.sent_at >= st.timeout:
                st.sent_at = now
                st.timeout = min(2 * st.timeout, MAX_TIMEOUT)
                self._send(station, st.sent_seq, st.sent_price)

    def query_station_state(self, station):
        st = self._stations.get(station, _Station())
        return {
            'desired_price': st.desired,
            'shown_price': st.shown,
            'in_flight_seq': st.sent_seq if st.in_flight else None,
            'in_flight_price': st.sent_price if st.in_flight else None,
            'pending': st.in_flight,
            'timeout': st.timeout,
        }
