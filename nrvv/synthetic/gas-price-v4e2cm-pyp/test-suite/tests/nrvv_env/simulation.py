'''Deterministic simulated environment for the server side under test.

Only the Environment is simulated: the clients, the transport and the stations. The server side is
handed in as app and this module never imports it. app must provide:

- set_desired_price(station_id, price): SetDesiredPrice; returns the accepted result.
- get_station_status(station_id): GetStationStatus; read-only.
- clock_tick(): clock tick; the harness calls it once per tick, after the deliveries of that tick.
- receive_acknowledgement(station_id): acknowledgement receive port, called by the transport.
- connect_send_port(send): hands the price update send port to the service; the service calls
  send(station_id, price) for every update it dispatches.
'''
import random

DMAX = 5
OUTAGE_MAX = 4 * DMAX


class Station:
    '''Simulated station: displays the price of the last update it received and acknowledges it.'''

    def __init__(self, station_id):
        self.station_id = station_id
        self.displayed = None
        self.outages = []  # half-open tick intervals [start, end) during which updates are dropped
        self.received = []  # (time, price) of every delivered update, in arrival order
        self.acks_returned = 0

    def in_outage(self, now):
        return any(start <= now < end for start, end in self.outages)


class Simulation:
    '''One seeded run: seeded clients, transport and stations wired to app.'''

    def __init__(self, app, seed, stations=('S1', 'S2', 'S3'), loss=0.2, outage=0.2, horizon=100):
        self.app = app
        self.rng = random.Random(seed)
        self.now = 0
        self.stations = {}
        for station_id in stations:
            station = Station(station_id)
            if self.rng.random() < outage:
                start = self.rng.randrange(horizon)
                station.outages.append((start, start + self.rng.randint(1, OUTAGE_MAX)))
            self.stations[station_id] = station
        self.loss = loss
        self.sent = []  # every update sent, in send order; 'fate' is 'lost', 'outage' or 'delivered'
        self.desired_history = []  # (time, station, price) of every SetDesiredPrice call, before the call
        self.accepted = []  # (time, station, price, result) of every SetDesiredPrice call
        self.acks = []  # (time, station) of every acknowledgement delivered to the service
        self._updates = []  # in transit: (due, seq, entry)
        self._acks = []  # in transit: (due, seq, station_id)
        self._ack_floor = {station_id: 0 for station_id in stations}  # latest due time of acks per station
        self._seq = 0
        app.connect_send_port(self._send_port)

    def _next_seq(self):
        self._seq += 1
        return self._seq

    def _send_port(self, station_id, price):
        entry = {
            'time': self.now,
            'station': station_id,
            'price': price,
            'status_at_send': self.app.get_station_status(station_id),
            'fate': None,
        }
        self.sent.append(entry)
        if self.rng.random() < self.loss:
            entry['fate'] = 'lost'
            return
        due = self.now + self.rng.randint(1, DMAX)
        self._updates.append((due, self._next_seq(), entry))

    def tick(self):
        '''Advance logical time by one tick: deliver updates, return acks, then clock_tick on app.'''
        self.now += 1
        arrived = sorted(update for update in self._updates if update[0] <= self.now)
        self._updates = [update for update in self._updates if update[0] > self.now]
        for _, seq, entry in arrived:
            station = self.stations[entry['station']]
            if station.in_outage(self.now):
                entry['fate'] = 'outage'
                continue
            entry['fate'] = 'delivered'
            station.displayed = entry['price']
            station.received.append((self.now, entry['price']))
            station.acks_returned += 1
            floor = max(self.now + 1, self._ack_floor[station.station_id])
            due = self.rng.randint(floor, self.now + DMAX)
            self._ack_floor[station.station_id] = due
            self._acks.append((due, seq, station.station_id))
        ready = sorted(ack for ack in self._acks if ack[0] <= self.now)
        self._acks = [ack for ack in self._acks if ack[0] > self.now]
        for _, _, station_id in ready:
            self.acks.append((self.now, station_id))
            self.app.receive_acknowledgement(station_id)
        self.app.clock_tick()

    def set_desired_price(self, station_id, price):
        '''Client call SetDesiredPrice; records the call and the accepted result.'''
        self.desired_history.append((self.now, station_id, price))
        result = self.app.set_desired_price(station_id, price)
        self.accepted.append((self.now, station_id, price, result))
        return result

    def status(self, station_id):
        return self.app.get_station_status(station_id)

    def run_schedule(self, steps, prices=range(1, 100), change_prob=0.3, burst_max=4):
        '''Seeded schedule: each step may issue a burst of SetDesiredPrice calls, then one tick.'''
        prices = tuple(prices)
        station_ids = tuple(self.stations)
        for _ in range(steps):
            if self.rng.random() < change_prob:
                for _ in range(self.rng.randint(1, burst_max)):
                    self.set_desired_price(self.rng.choice(station_ids), self.rng.choice(prices))
            self.tick()

    def in_flight(self):
        return bool(self._updates or self._acks)

    def quiesce(self, bound=500, idle_ticks=2 * DMAX + 1):
        '''Tick until nothing is in flight and nothing was sent for idle_ticks ticks.

        Returns True on quiescence, False if bound ticks were not enough. Tests needing a longer quiet
        window (for example to observe the service's timeout) pass a larger idle_ticks.
        '''
        idle = 0
        for _ in range(bound):
            sent_before = len(self.sent)
            self.tick()
            if self.in_flight() or len(self.sent) != sent_before:
                idle = 0
            else:
                idle += 1
                if idle >= idle_ticks:
                    return True
        return False

    def displayed(self, station_id):
        return self.stations[station_id].displayed

    def last_delivered_price(self, station_id):
        received = self.stations[station_id].received
        return received[-1][1] if received else None

    def delivered(self):
        return [entry for entry in self.sent if entry['fate'] == 'delivered']

    def sent_to(self, station_id):
        return [entry for entry in self.sent if entry['station'] == station_id]

    def sends_per_station(self):
        counts = {station_id: 0 for station_id in self.stations}
        for entry in self.sent:
            counts[entry['station']] += 1
        return counts

    def acks_per_station(self):
        counts = {station_id: 0 for station_id in self.stations}
        for _, station_id in self.acks:
            counts[station_id] += 1
        return counts
