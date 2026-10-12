'''Central service: records each station's desired, confirmed and in-flight price.

Time is an explicit logical tick counter advanced only by clock_tick().
'''

DMAX = 5
# Longer than the longest update-to-acknowledgement round trip (2 * DMAX), so an
# expired update can never be acknowledged afterwards.
ACK_TIMEOUT = 3 * DMAX


class StationRecord:
    '''Price record of one station.'''

    def __init__(self):
        self.desired = None
        self.confirmed = None
        self.in_flight = None
        self.sent_at = None


class GasPriceService:
    '''Dispatches at most one update per station at a time and records confirmed prices.'''

    def __init__(self):
        self.now = 0
        self.anomaly_count = 0  # acknowledgements that arrived with no update in flight
        self.expired_count = 0  # in-flight updates that timed out
        self._stations = {}
        self._send_port = None

    def set_send_port(self, send_port):
        self._send_port = send_port

    def set_desired_price(self, station_id, price):
        self._record(station_id).desired = price
        self._dispatch(station_id)
        return True

    def get_station_status(self, station_id):
        record = self._stations.get(station_id)
        if record is None:
            return (None, None, None, None)
        return (record.desired, record.confirmed, record.in_flight, record.sent_at)

    def receive_acknowledgement(self, station_id):
        record = self._stations.get(station_id)
        if record is None or record.in_flight is None:
            self.anomaly_count += 1
            return
        record.confirmed = record.in_flight
        record.in_flight = None
        record.sent_at = None
        self._dispatch(station_id)

    def clock_tick(self):
        self.now += 1
        for record in self._stations.values():
            if record.in_flight is not None and self.now - record.sent_at >= ACK_TIMEOUT:
                record.in_flight = None
                record.sent_at = None
                self.expired_count += 1
        for station_id in list(self._stations):
            self._dispatch(station_id)

    def _record(self, station_id):
        record = self._stations.get(station_id)
        if record is None:
            record = self._stations[station_id] = StationRecord()
        return record

    def _dispatch(self, station_id):
        record = self._stations.get(station_id)
        if record is None or record.in_flight is not None:
            return
        if record.desired is None or record.desired == record.confirmed:
            return
        if self._send_port is None:
            raise RuntimeError('no send port attached')
        record.in_flight = record.desired
        record.sent_at = self.now
        self._send_port(station_id, record.desired)
