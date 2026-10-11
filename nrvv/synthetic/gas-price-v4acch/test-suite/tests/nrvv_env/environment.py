import random
from .station import Station


class Environment:
    """Simulates the network environment for testing the price broadcast service.
    
    Provides deterministic simulation of:
    - Out-of-order message delivery to stations
    - In-order acknowledgment delivery (monotonic message_ids per station)
    - Station behavior (apply latest message, acknowledge it)
    - Test observation of clients and traffic
    """

    def __init__(self, seed):
        """Initialize the environment with a deterministic seed."""
        self.rng = random.Random(seed)
        self.app = None
        self.stations = {}  # station_id -> Station
        self.time = 0
        self.events = []  # [(time, event_type, data), ...] sorted by time
        
        # Logs for test observation
        self._sent_log = []
        self._delivered_log = []
        self._acked_log = []

    def set_app(self, app):
        """Register the app instance to be driven by this environment."""
        self.app = app

    def send_price_message(self, station_id, message_id, price):
        """Called by the app to send a message to a station.
        
        The message is scheduled for delivery with a random delay, allowing
        out-of-order arrival relative to other messages.
        """
        self._sent_log.append((self.time, station_id, message_id, price))
        
        # Ensure station exists
        if station_id not in self.stations:
            self.stations[station_id] = Station(station_id)
        
        # Schedule delivery with random delay (causes out-of-order delivery)
        delay = self.rng.randint(1, 10)
        delivery_time = self.time + delay
        self.events.append((delivery_time, 'msg_deliver', (station_id, message_id, price)))
        self.events.sort()

    def new_price_available(self, price):
        """Called by the test to inject a new price into the service.
        
        Drives the app with the new price and processes all resulting events
        until the system becomes idle.
        """
        self.app.new_price_available(price)
        self.run_until_idle()

    def step(self):
        """Process the next pending event.
        
        Returns True if an event was processed, False if no events are pending.
        """
        if not self.events:
            return False
        
        event_time, event_type, data = self.events.pop(0)
        self.time = event_time
        
        if event_type == 'msg_deliver':
            self._process_message_delivery(data)
        elif event_type == 'ack_deliver':
            self._process_ack_delivery(data)
        
        return True

    def run_until_idle(self):
        """Process all pending events until none remain."""
        while self.step():
            pass

    def _process_message_delivery(self, data):
        """A message has been delivered to a station."""
        station_id, message_id, price = data
        station = self.stations[station_id]
        
        # Station applies the message immediately
        station.last_price = price
        station.received_messages[message_id] = price
        
        self._delivered_log.append((self.time, station_id, message_id, price))
        
        # Try to schedule ack delivery
        self._maybe_schedule_ack(station_id)

    def _process_ack_delivery(self, data):
        """An acknowledgment is being delivered to the app.
        
        Only delivers the ack if it is the next in sequence (maintains
        monotonic message_ids).
        """
        station_id, = data
        station = self.stations[station_id]
        
        # Only deliver if this is the next expected ack
        if station.next_ack_message_id in station.received_messages:
            message_id = station.next_ack_message_id
            del station.received_messages[message_id]
            station.next_ack_message_id += 1
            
            # Deliver ack to app
            self.app.receive_ack(station_id, message_id)
            self._acked_log.append((self.time, station_id, message_id))
            
            # Try to schedule next ack
            self._maybe_schedule_ack(station_id)

    def _maybe_schedule_ack(self, station_id):
        """Schedule delivery of the next pending ack for a station, if ready.
        
        An ack is ready when its message has been received. Multiple acks
        for a station are delivered one at a time, in order of message_id.
        """
        station = self.stations[station_id]
        
        # Check if the next ack is available to deliver
        if station.next_ack_message_id in station.received_messages:
            # Check if there's already an ack event scheduled for this station
            has_ack_scheduled = any(
                e[1] == 'ack_deliver' and e[2] == (station_id,)
                for e in self.events
            )
            
            if not has_ack_scheduled:
                # Schedule ack with random delay
                delay = self.rng.randint(1, 5)
                ack_time = self.time + delay
                self.events.append((ack_time, 'ack_deliver', (station_id,)))
                self.events.sort()

    # Observation methods for tests

    def get_station_price(self, station_id):
        """Get the current price applied at a station."""
        if station_id in self.stations:
            return self.stations[station_id].last_price
        return None

    def get_sent_messages(self):
        """Get log of all send_price_message calls.
        
        Returns list of (time, station_id, message_id, price) tuples.
        """
        return self._sent_log.copy()

    def get_delivered_messages(self):
        """Get log of all messages delivered to stations.
        
        Returns list of (time, station_id, message_id, price) tuples.
        """
        return self._delivered_log.copy()

    def get_delivered_acks(self):
        """Get log of all acknowledgments delivered to the app.
        
        Returns list of (time, station_id, message_id) tuples in order.
        """
        return self._acked_log.copy()
