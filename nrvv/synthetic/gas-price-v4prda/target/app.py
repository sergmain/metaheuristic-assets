"""Server side of the desired-price protocol (GASV4PRDA-22..25).

Each station has one desired-price register and one outstanding-update slot.
A fresh update is sent only into an empty slot and only if its price differs
from the most recently sent price; the slot is emptied by the matching
acknowledgement, and an outstanding update is resent unchanged every 30 s.
"""

RESEND_PERIOD = 30

# Send port (GASV4PRDA-25), attached by the environment for each simulation.
send_price_update = None


class Update:
    """The outstanding update of a station: its sequence number, price and last send time."""

    def __init__(self, sequence_number, price, sent_at):
        self.sequence_number = sequence_number
        self.price = price
        self.sent_at = sent_at


class StationState:
    """Everything the server knows about one station."""

    def __init__(self):
        self.desired = None  # D1: latest desired price
        self.last_sent = None  # price of the most recently sent update (D5)
        self.next_sequence = 1
        self.outstanding = None  # Update in the slot, or None when the slot is empty


_bound_port = None
_now = -1  # last time given to advance_time; events before the first call belong to time 0
_stations = {}


def _attach():
    """Start a fresh server when the environment binds a new send port (one binding per simulation)."""
    global _bound_port, _now, _stations
    if send_price_update is not _bound_port:
        _bound_port = send_price_update
        _now = -1
        _stations = {}


def _station(station_id):
    _attach()
    state = _stations.get(station_id)
    if state is None:
        state = _stations[station_id] = StationState()
    return state


def _send_fresh(station_id, state):
    # Events between two advance_time calls happen in the following second.
    update = Update(state.next_sequence, state.desired, _now + 1)
    state.next_sequence += 1
    state.outstanding = update
    state.last_sent = update.price
    send_price_update(station_id, update.sequence_number, update.price)


def desired_price_change(station_id, price):
    """GASV4PRDA-22: overwrite the desired price; send it at once if the slot is empty and the price is new."""
    state = _station(station_id)
    state.desired = price
    if state.outstanding is None and price != state.last_sent:
        _send_fresh(station_id, state)


def acknowledgement_received(station_id, sequence_number):
    """GASV4PRDA-23: a matching acknowledgement empties the slot; then the rule of D4 applies."""
    state = _station(station_id)
    if state.outstanding is None or state.outstanding.sequence_number != sequence_number:
        return None
    state.outstanding = None
    if state.desired != state.last_sent:
        _send_fresh(station_id, state)
    return None


def advance_time(t):
    """GASV4PRDA-24: resend every outstanding update that was last sent 30 s or more ago."""
    global _now
    _attach()
    _now = t
    for station_id, state in list(_stations.items()):
        update = state.outstanding
        if update is not None and t - update.sent_at >= RESEND_PERIOD:
            update.sent_at = t
            send_price_update(station_id, update.sequence_number, update.price)
