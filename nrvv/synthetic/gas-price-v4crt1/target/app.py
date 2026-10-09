# Price service for the stations (GASV4CRT1-20..23).
# Per station it keeps the desired, confirmed and in-flight price. An update is
# sent through the outbound port only when no update is in flight and the desired
# price differs from the confirmed price; an acknowledgement confirms the price
# only when it matches the in-flight one.


class _Station:
    # Price record kept for one station.

    def __init__(self):
        self.desired = None
        self.confirmed = None
        self.in_flight = None


class PriceService:

    def __init__(self, send_price_update):
        self._send_price_update = send_price_update
        self._stations = {}

    def set_desired_price(self, station, price):
        record = self._record(station)
        record.desired = price
        self._send_if_due(station, record)

    def receive_acknowledgement(self, station, price):
        record = self._record(station)
        if record.in_flight is None or price != record.in_flight:
            return
        record.confirmed = price
        record.in_flight = None
        self._send_if_due(station, record)

    def inspect_station(self, station):
        record = self._stations.get(station)
        if record is None:
            return (None, None, None)
        return (record.desired, record.confirmed, record.in_flight)

    def _record(self, station):
        if station not in self._stations:
            self._stations[station] = _Station()
        return self._stations[station]

    def _send_if_due(self, station, record):
        if record.in_flight is not None or record.desired is None or record.desired == record.confirmed:
            return
        # the in-flight slot is taken before the port runs, so the port sees it occupied
        record.in_flight = record.desired
        self._send_price_update(station, record.in_flight)
