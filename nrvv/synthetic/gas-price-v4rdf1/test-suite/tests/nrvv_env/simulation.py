"""Deterministic simulation of the clients and transport around the server side ``app``.

Nothing here implements the server side. The server side is reached only through the
operations and ports the Interface names; the clients and the transport are simulated.
Logical time is an integer that moves only when a test advances it. The only randomness
is the delivery delay, drawn from random.Random(seed).
"""
import random

NOTICE_BOUND = 60  # one minute of logical time (GASV4RDF1-32)

ACK_CHANNEL = "ack"        # station -> server side
NOTICE_CHANNEL = "notice"  # server side -> pricing team


class Message:
    """A message handed to the transport."""

    def __init__(self, seq, channel, payload, sent_at, deliver_at):
        self.seq = seq
        self.channel = channel
        self.payload = payload
        self.sent_at = sent_at
        self.deliver_at = deliver_at

    def __repr__(self):
        return (f"Message(seq={self.seq}, channel={self.channel!r}, sent_at={self.sent_at}, "
                f"deliver_at={self.deliver_at}, payload={self.payload!r})")


class Transport:
    """Ordered, lossless, non-duplicating delivery in logical time.

    Each message is delivered after a delay drawn from the seeded generator. Delivery
    times never decrease within a channel, so messages on one channel arrive in the order
    they were sent. Messages due at the same instant are handed over in send order.
    """

    def __init__(self, rng, min_delay, max_delay):
        if not 0 <= min_delay <= max_delay:
            raise ValueError("need 0 <= min_delay <= max_delay")
        self._rng = rng
        self._min_delay = min_delay
        self._max_delay = max_delay
        self.now = 0
        self._seq = 0
        self._in_flight = []
        self._last_deliver_at = {}

    def send(self, channel, payload):
        delay = self._rng.randint(self._min_delay, self._max_delay)
        deliver_at = max(self.now + delay, self._last_deliver_at.get(channel, 0))
        self._last_deliver_at[channel] = deliver_at
        msg = Message(self._seq, channel, payload, self.now, deliver_at)
        self._seq += 1
        self._in_flight.append(msg)
        return msg

    def in_flight(self):
        return sorted(self._in_flight, key=lambda m: (m.deliver_at, m.seq))

    def next_delivery_time(self):
        return min((m.deliver_at for m in self._in_flight), default=None)

    def deliver_next(self, handler):
        """Move time to the next delivery and hand every message due then to handler.

        Returns False when nothing is in flight.
        """
        t = self.next_delivery_time()
        if t is None:
            return False
        self.now = max(self.now, t)
        due = [m for m in self.in_flight() if m.deliver_at <= self.now]
        self._in_flight = [m for m in self._in_flight if m.deliver_at > self.now]
        for msg in due:
            handler(msg)
        return True

    def advance(self, dt, handler):
        """Advance logical time by dt, delivering everything due on the way."""
        if dt < 0:
            raise ValueError("cannot move logical time backwards")
        target = self.now + dt
        while True:
            t = self.next_delivery_time()
            if t is None or t > target:
                break
            self.deliver_next(handler)
        self.now = target


class Station:
    """Station client: the price set for it, and the price it currently displays."""

    def __init__(self, station_id):
        self.station_id = station_id
        self.desired_price = None
        self.displayed_price = None

    def __repr__(self):
        return (f"Station({self.station_id!r}, desired_price={self.desired_price!r}, "
                f"displayed_price={self.displayed_price!r})")


class PricingTeam:
    """Pricing-team client: a recorder of notices with their logical arrival time."""

    def __init__(self):
        self.received = []

    def receive(self, arrival_time, notice):
        notice["arrived_at"] = arrival_time
        self.received.append(notice)


class Simulation:
    """Wires the simulated clients and transport to the server side ``app``.

    The simulation installs the pricing-notice port on ``app`` as the attribute
    ``send_pricing_team_notice``, and delivers each acknowledgement to ``app`` by calling
    ``app.receive_acknowledgement(station_id, price)`` when the transport delivers it.
    The pricing team reads through ``app.list_stations_not_acknowledging_latest_price()``.
    """

    def __init__(self, seed, app, min_delay=0, max_delay=5):
        self.seed = seed
        self.app = app
        self._rng = random.Random(seed)
        self.transport = Transport(self._rng, min_delay, max_delay)
        self.stations = {}
        self.pricing = PricingTeam()
        self.traffic = []   # every send and delivery, in the order they happened
        self.notices = []   # every notice sent through the notice port
        self._handling_ack = None
        app.send_pricing_team_notice = self._notice_port

    @property
    def now(self):
        return self.transport.now

    def add_station(self, station_id):
        if station_id in self.stations:
            raise ValueError(f"station {station_id!r} already exists")
        station = Station(station_id)
        self.stations[station_id] = station
        return station

    def set_desired_price(self, station_id, price):
        self.stations[station_id].desired_price = price

    def acknowledge(self, station_id):
        """Station displays its desired price and sends the acknowledgement over the transport."""
        station = self.stations[station_id]
        if station.desired_price is None:
            raise ValueError(f"station {station_id!r} has no desired price to acknowledge")
        station.displayed_price = station.desired_price
        payload = {"station_id": station_id, "price": station.displayed_price}
        msg = self.transport.send(ACK_CHANNEL, payload)
        self._record("sent", msg)
        return msg

    def list_unacknowledged(self):
        """Pricing team's read-only query. Changes no state and sends nothing."""
        return self.app.list_stations_not_acknowledging_latest_price()

    def in_flight(self):
        return self.transport.in_flight()

    def step(self):
        """Deliver the next due batch of messages. Returns False when nothing is in flight."""
        return self.transport.deliver_next(self._deliver)

    def run_until_idle(self, max_steps=100000):
        """Step until nothing is in flight. Returns the number of steps taken."""
        steps = 0
        while self.transport.in_flight():
            if steps >= max_steps:
                raise RuntimeError("transport still busy after max_steps steps")
            self.step()
            steps += 1
        return steps

    def advance_time(self, dt):
        self.transport.advance(dt, self._deliver)

    def late_notices(self):
        """Notices not delivered within NOTICE_BOUND of the acknowledgement that caused them.

        A notice still in flight counts as late once the bound has passed at the current time.
        Notices sent outside handling of an acknowledgement have no cause and are not checked.
        """
        late = []
        for notice in self.notices:
            if notice["ack_sent_at"] is None:
                continue
            end = notice["arrived_at"] if notice["arrived_at"] is not None else self.now
            if end - notice["ack_sent_at"] > NOTICE_BOUND:
                late.append(notice)
        return late

    def _deliver(self, msg):
        self._record("delivered", msg)
        if msg.channel == ACK_CHANNEL:
            self._handling_ack = msg
            try:
                self.app.receive_acknowledgement(msg.payload["station_id"], msg.payload["price"])
            finally:
                self._handling_ack = None
        elif msg.channel == NOTICE_CHANNEL:
            self.pricing.receive(self.now, msg.payload)

    def _notice_port(self, station_id, price):
        ack = self._handling_ack
        notice = {
            "station_id": station_id,
            "price": price,
            "sent_at": self.now,
            "ack_sent_at": ack.sent_at if ack is not None else None,
            "arrived_at": None,
        }
        self.notices.append(notice)
        msg = self.transport.send(NOTICE_CHANNEL, notice)
        self._record("sent", msg)

    def _record(self, event, msg):
        self.traffic.append({
            "t": self.now,
            "event": event,
            "channel": msg.channel,
            "seq": msg.seq,
            "payload": msg.payload,
        })
