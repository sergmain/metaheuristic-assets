"""Server side of the station price update service (GASV4ELMA-19 .. GASV4ELMA-23)."""

from dataclasses import dataclass, field
from typing import Any, List, Optional

ACCEPTED = "Accepted"


@dataclass
class StationState:
    """Observable state of one station (GASV4ELMA-23)."""

    latest_desired: Optional[Any] = None
    last_sent_price: Optional[Any] = None
    last_sent_seq: Optional[int] = None
    outstanding: List[int] = field(default_factory=list)
    reachable: bool = True


class _Station:
    """Per-station record: single desired-price slot plus sent and acknowledged history."""

    def __init__(self):
        self.latest_desired = None
        self.last_sent_price = None
        self.last_sent_seq = None
        self.next_seq = 1
        self.outstanding = []
        self.last_acked_price = None
        self.reachable = True


class PriceServer:
    """Keeps the latest desired price per station and sends it through dispatch_update."""

    def __init__(self, dispatch_update):
        self._dispatch_update = dispatch_update
        self._stations = {}

    def _station(self, station_id):
        if station_id not in self._stations:
            self._stations[station_id] = _Station()
        return self._stations[station_id]

    def _send_if_needed(self, station_id):
        """Send the latest desired price when reachable and it differs from the last sent price."""
        st = self._station(station_id)
        if not st.reachable or st.latest_desired is None:
            return
        if st.latest_desired == st.last_sent_price and st.last_sent_seq is not None:
            return
        seq = st.next_seq
        st.next_seq += 1
        st.last_sent_price = st.latest_desired
        st.last_sent_seq = seq
        st.outstanding.append(seq)
        self._dispatch_update(station_id, seq, st.latest_desired)

    def set_desired_price(self, station_id, price):
        """GASV4ELMA-19: always accepted, regardless of outstanding updates."""
        self._station(station_id).latest_desired = price
        self._send_if_needed(station_id)
        return ACCEPTED

    def acknowledgement_received(self, station_id, sequence, price):
        """GASV4ELMA-21: record the echoed acknowledgement and trigger D6."""
        st = self._station(station_id)
        if sequence in st.outstanding:
            st.outstanding.remove(sequence)
        st.last_acked_price = price
        self._send_if_needed(station_id)

    def reachability_changed(self, station_id, reachable):
        """GASV4ELMA-22: record the transition and trigger D7."""
        st = self._station(station_id)
        st.reachable = bool(reachable)
        self._send_if_needed(station_id)

    def station_state(self, station_id):
        """GASV4ELMA-23: read-only view of the station record."""
        st = self._station(station_id)
        return StationState(
            latest_desired=st.latest_desired,
            last_sent_price=st.last_sent_price,
            last_sent_seq=st.last_sent_seq,
            outstanding=sorted(st.outstanding),
            reachable=st.reachable,
        )

    def stations_not_confirming_latest(self):
        """Stations whose last acknowledged price is not their latest desired price."""
        return [
            station_id
            for station_id, st in self._stations.items()
            if st.latest_desired is not None and st.last_acked_price != st.latest_desired
        ]
