"""Server side of the gas-price update service.

Keeps one desired price per station and sends a station only the latest price,
only while the station is reachable, and never a price it already holds.
"""
from dataclasses import dataclass, field
from typing import Any, Callable, Optional, Set

ACCEPTED = 'Accepted'


@dataclass
class StationState:
    """Observable state of one station (GASV4ELMA-23)."""
    latest_desired: Any = None
    last_sent_price: Any = None
    last_sent_seq: Optional[int] = None
    outstanding: Set[int] = field(default_factory=set)
    reachable: bool = False


class _Station:
    def __init__(self):
        self.latest_desired = None
        self.last_sent_price = None
        self.last_sent_seq = None
        self.next_seq = 1
        self.outstanding = set()
        self.reachable = False
        # Until the first ReachabilityChanged the station is presumed reachable.
        self.reachability_known = False

    def may_send(self):
        return self.reachable or not self.reachability_known

    def snapshot(self):
        return StationState(
            latest_desired=self.latest_desired,
            last_sent_price=self.last_sent_price,
            last_sent_seq=self.last_sent_seq,
            outstanding=set(self.outstanding),
            reachable=self.reachable,
        )


class Server:
    """Send decision (D3, D6, D7) over the DispatchUpdate outbound port."""

    def __init__(self, dispatch_update: Callable[[Any, int, Any], None]):
        self._dispatch_update = dispatch_update
        self._stations = {}

    def _station(self, station_id):
        if station_id not in self._stations:
            self._stations[station_id] = _Station()
        return self._stations[station_id]

    def set_desired_price(self, station_id, price):
        """SetDesiredPrice (GASV4ELMA-19): always accepted; replaces the single desired-price slot."""
        st = self._station(station_id)
        st.latest_desired = price
        if st.latest_desired != st.last_sent_price:
            self._send(station_id, st)
        return ACCEPTED

    def acknowledgement_received(self, station_id, sequence, price):
        """AcknowledgementReceived (GASV4ELMA-21): a stale acknowledgement triggers one resend (D6)."""
        st = self._station(station_id)
        st.outstanding.discard(sequence)
        if price != st.latest_desired:
            self._send(station_id, st)

    def reachability_changed(self, station_id, reachable):
        """ReachabilityChanged (GASV4ELMA-22): on becoming reachable, send the latest price if needed (D7)."""
        st = self._station(station_id)
        st.reachable = bool(reachable)
        st.reachability_known = True
        if st.reachable and st.latest_desired is not None and st.latest_desired != st.last_sent_price:
            self._send(station_id, st)

    def station_state(self, station_id):
        """StationState (GASV4ELMA-23): read-only snapshot."""
        return self._station(station_id).snapshot()

    def _send(self, station_id, st):
        if st.latest_desired is None or not st.may_send():
            return
        seq = st.next_seq
        st.next_seq += 1
        st.last_sent_price = st.latest_desired
        st.last_sent_seq = seq
        st.outstanding.add(seq)
        self._dispatch_update(station_id, seq, st.latest_desired)
