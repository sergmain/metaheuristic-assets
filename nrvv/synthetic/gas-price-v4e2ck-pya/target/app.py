'''Server side of the desired-price synchronisation (GASV4E2CK-20..24).

Every desired-price change is sent to its station at once and kept in that station's queue of
outstanding records. An acknowledgement from a station clears the oldest record of that station
(acknowledgements carry no identifier). A record still outstanding 30 logical seconds after its
last transmission is retransmitted, in queue order, by AdvanceTime.
'''

from collections import deque
from typing import NamedTuple

RETRANSMIT_TIMEOUT = 30


class StationState(NamedTuple):
    desired_price: object = None
    last_sent_price: object = None
    outstanding: int = 0
    stale: bool = False
    up_to_date: bool = True


class Server:
    '''The four server operations; send_update is the SendUpdate port (GASV4E2CK-21).'''

    def __init__(self, send_update=None):
        self.send_update = send_update
        self._now = 0
        self._queues = {}     # station -> deque of [price, last transmission time], oldest first
        self._desired = {}    # station -> latest desired price
        self._last_sent = {}  # station -> price of the most recent transmission
        self._acked = {}      # station -> price of the most recently acknowledged record

    def bind_send_update(self, send_update):
        self.send_update = send_update

    def set_desired_price(self, station, price):
        self._desired[station] = price
        record = [price, self._now]
        self._queues.setdefault(station, deque()).append(record)
        self._transmit(station, record)

    def receive_ack(self, station):
        queue = self._queues.get(station)
        if not queue:
            return  # nothing outstanding: the acknowledgement is ignored, not banked
        price, _ = queue.popleft()
        self._acked[station] = price

    def advance_time(self, now):
        self._now = now
        for station, queue in self._queues.items():
            for record in queue:
                if now - record[1] >= RETRANSMIT_TIMEOUT:
                    self._transmit(station, record)

    def query_station(self, station):
        desired = self._desired.get(station)
        outstanding = len(self._queues.get(station, ()))
        stale = desired is not None and self._acked.get(station) != desired
        return StationState(desired, self._last_sent.get(station), outstanding, stale,
                            outstanding == 0 and not stale)

    def _transmit(self, station, record):
        self.send_update(station, record[0])
        record[1] = self._now
        self._last_sent[station] = record[0]


# Module-level operations, for use with the module itself as the server.
_server = Server()


def bind_send_update(send_update):
    global _server
    _server = Server(send_update)


def set_desired_price(station, price):
    _server.set_desired_price(station, price)


def receive_ack(station):
    _server.receive_ack(station)


def advance_time(now):
    _server.advance_time(now)


def query_station(station):
    return _server.query_station(station)
