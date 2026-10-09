# Deterministic simulation of the Environment around the server side.
# Simulated: the stations, the update transport, the acknowledgement return path
# and the seeded schedule of desired-price changes. The server side is never
# imported here: build the service with sim.send_price_update as its outbound
# port, then call sim.connect(service).

import random
from dataclasses import dataclass


@dataclass(frozen=True)
class Desire:
    # A desired-price change issued to the service (SetDesiredPrice).
    step: int
    station: object
    price: object
    seq: int  # 0-based index of this change among the station's changes


@dataclass(frozen=True)
class Send:
    # An update sent through the outbound port (I2).
    step: int
    station: object
    price: object
    desired_at_send: object  # last desired price issued for the station, or None
    desire_seq_at_send: int  # desired changes issued for the station before this send
    confirmed_at_send: object  # confirmed price from inspect_station at send time
    outstanding_before: int  # updates sent for the station and not yet acknowledged
    index: int  # position in the global send log


@dataclass(frozen=True)
class Delivery:
    # An update delivered to a station; displayed is the price it shows afterwards.
    step: int
    station: object
    price: object
    displayed: object


@dataclass(frozen=True)
class AckDelivery:
    # An acknowledgement delivered to the service (I3).
    step: int
    station: object
    price: object


@dataclass(frozen=True)
class _Update:
    due: int
    seq: int
    station: object
    price: object


@dataclass(frozen=True)
class _Ack:
    due: int
    seq: int
    station: object
    price: object


class Station:
    # Displays the price of the last update it received; acknowledges every update.

    def __init__(self, station_id):
        self.station_id = station_id
        self.displayed = None

    def receive(self, price):
        self.displayed = price
        return self.displayed


def _in_order(items):
    return sorted(items, key=lambda item: (item.due, item.seq))


def _field(state, name, index):
    if state is None:
        return None
    if isinstance(state, dict):
        return state.get(name)
    if hasattr(state, name):
        return getattr(state, name)
    return state[index]


class Simulation:
    # Logical time is the step counter only. Every random draw comes from the
    # single random.Random(seed) instance, in a fixed order, so a seed fixes the run.

    def __init__(self, seed, stations, *, changes=20, horizon=40,
                 prices=(1, 2, 3, 4, 5), max_update_delay=4, max_ack_delay=4):
        if max_update_delay < 1 or max_ack_delay < 1:
            raise ValueError('delays must be at least one step')
        self._rng = random.Random(seed)
        self._stations = list(stations)
        self.clients = {sid: Station(sid) for sid in self._stations}
        self._max_update_delay = max_update_delay
        self._max_ack_delay = max_ack_delay
        self._service = None
        self.time = 0
        self._seq = 0
        self._updates = []
        self._acks = []
        self._last_ack_due = {sid: 0 for sid in self._stations}
        self._outstanding = {sid: 0 for sid in self._stations}
        self._desired = {sid: None for sid in self._stations}
        self._desire_count = {sid: 0 for sid in self._stations}
        self.desires = []
        self.sends = []
        self.deliveries = []
        self.acks = []
        # (step, {station: displayed price}) recorded at the end of every step
        self.history = []
        self._schedule = self._make_schedule(changes, horizon, prices)

    def _make_schedule(self, changes, horizon, prices):
        rng = self._rng
        issued = {sid: [] for sid in self._stations}
        plan = []
        for _ in range(changes):
            step = rng.randint(1, horizon)
            station = rng.choice(self._stations)
            past = issued[station]
            if past and rng.random() < 1 / 3:
                price = rng.choice(past)  # change back to an earlier value
            else:
                price = rng.choice(prices)
            past.append(price)
            plan.append((step, station, price))
        plan.sort(key=lambda item: item[0])  # stable: generation order within a step
        return plan

    def connect(self, service):
        self._service = service
        return self

    def _require_service(self):
        if self._service is None:
            raise RuntimeError('connect(service) before driving the simulation')

    def displayed(self, station):
        return self.clients[station].displayed

    def desired(self, station):
        return self._desired[station]

    def outstanding(self, station):
        # updates sent for the station and not yet acknowledged to the service
        return self._outstanding[station]

    def in_transit(self, station):
        # updates sent for the station and not yet delivered to it
        return sum(1 for u in self._updates if u.station == station)

    def pending(self):
        return bool(self._schedule or self._updates or self._acks)

    def quiescence_report(self):
        return {sid: {'displayed': self.clients[sid].displayed,
                      'desired': self._desired[sid],
                      'in_transit': self.in_transit(sid),
                      'outstanding': self._outstanding[sid]}
                for sid in self._stations}

    def issue_desired_price(self, station, price):
        # Driver: SetDesiredPrice at the current step. The state is set before the
        # call, because the service may send synchronously from inside it.
        self._require_service()
        self.desires.append(Desire(self.time, station, price, self._desire_count[station]))
        self._desire_count[station] += 1
        self._desired[station] = price
        self._service.set_desired_price(station, price)

    def send_price_update(self, station, price):
        # Outbound port I2, handed to the service.
        state = self._service.inspect_station(station) if self._service is not None else None
        self.sends.append(Send(
            step=self.time,
            station=station,
            price=price,
            desired_at_send=self._desired[station],
            desire_seq_at_send=self._desire_count[station],
            confirmed_at_send=_field(state, 'confirmed', 1),
            outstanding_before=self._outstanding[station],
            index=len(self.sends),
        ))
        self._outstanding[station] += 1
        self._seq += 1
        due = self.time + self._rng.randint(1, self._max_update_delay)
        self._updates.append(_Update(due, self._seq, station, price))

    def _queue_ack(self, station, price, now):
        # FIFO per station: due never precedes the station's previous acknowledgement.
        self._seq += 1
        due = max(now + self._rng.randint(1, self._max_ack_delay), self._last_ack_due[station])
        self._last_ack_due[station] = due
        self._acks.append(_Ack(due, self._seq, station, price))

    def step(self):
        self._require_service()
        self.time += 1
        now = self.time

        # 1. driver injects scheduled changes
        while self._schedule and self._schedule[0][0] <= now:
            _, station, price = self._schedule.pop(0)
            self.issue_desired_price(station, price)

        # 2. transport delivers due updates; each station acknowledges what it displays
        arriving = _in_order(u for u in self._updates if u.due <= now)
        self._updates = [u for u in self._updates if u.due > now]
        for update in arriving:
            displayed = self.clients[update.station].receive(update.price)
            self.deliveries.append(Delivery(now, update.station, update.price, displayed))
            self._queue_ack(update.station, displayed, now)

        # 3. return path delivers due acknowledgements, one at a time
        returning = _in_order(a for a in self._acks if a.due <= now)
        self._acks = [a for a in self._acks if a.due > now]
        for ack in returning:
            self._outstanding[ack.station] -= 1  # slot is clear before the service runs
            self.acks.append(AckDelivery(now, ack.station, ack.price))
            self._service.receive_acknowledgement(ack.station, ack.price)

        self.history.append((now, {sid: c.displayed for sid, c in self.clients.items()}))
        return self

    def run(self, max_steps=100000):
        self._require_service()
        for _ in range(max_steps):
            if not self.pending():
                return self
            self.step()
        raise RuntimeError('simulation did not quiesce within max_steps')
