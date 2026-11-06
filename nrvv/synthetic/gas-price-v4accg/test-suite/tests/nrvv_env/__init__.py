import random


class Simulation:
    """Deterministic simulation environment for price distribution testing.
    
    Simulates transport behavior (out-of-order delivery, in-order acks per station)
    and station behavior (stateless, auto-ack). Tests drive the app and this
    simulation in parallel, with the simulation stepping through message delivery.
    """

    def __init__(self, seed):
        """Initialize simulation with a deterministic seed.
        
        Args:
            seed: Random seed for deterministic execution
        """
        self.rng = random.Random(seed)
        self.app = None

        # Track the latest published price
        self.latest_version = 0
        self.latest_price_value = None

        # Station state: {station_id: {'displayed_price': v, 'displayed_version': v, 'acked_version': v}}
        self.stations = {}

        # In-flight sends: [(station_id, price_value, version_number), ...]
        # Messages queued by SendPrice, not yet delivered to station
        self.pending_sends = []

        # In-flight acks per station (FIFO per station, arbitrary interleaving)
        # {station_id: [version_numbers, ...]}
        self.ack_queues = {}

        # Metrics
        self.transmission_cost = 0

    def set_app(self, app):
        """Register the server app for callback delivery.
        
        The app's ReceiveAcknowledgment method will be called when
        acks are delivered during step().
        """
        self.app = app

    def get_transport(self):
        """Return a transport interface for the app to use.
        
        The app calls transport.send_price(...) to queue price sends.
        This maintains the separation: nrvv_env doesn't import app,
        but app can use this interface.
        """
        return _Transport(self)

    def send_price(self, station_id, price_value, version_number):
        """Queue a price for delivery to a station (GASV4ACCG-10).
        
        This is called either by the app via transport, or by tests
        that manually drive SendPrice. The message may be delivered
        out of order relative to other messages to the same station.
        
        Args:
            station_id: Target station
            price_value: Price value to deliver
            version_number: Version assigned by PublishPrice
        """
        # Initialize station if first message to it
        if station_id not in self.stations:
            self.stations[station_id] = {
                'displayed_price': None,
                'displayed_version': None,
                'acked_version': 0
            }

        # Queue for delivery (may be out of order)
        self.pending_sends.append((station_id, price_value, version_number))
        self.transmission_cost += 1

    def step(self):
        """Execute one simulation step: deliver a message or process an ack.
        
        Randomly chooses to:
        - Deliver a pending SendPrice (to any station, in any order - GASV4ACCG-13)
        - Deliver the oldest pending ack from some station (GASV4ACCG-14: FIFO per station)
        
        Returns:
            True if a message was delivered, False if idle
        """
        # Check if anything is in flight
        has_pending_sends = bool(self.pending_sends)
        has_pending_acks = any(self.ack_queues.values())

        if not has_pending_sends and not has_pending_acks:
            return False

        # Randomly choose action
        choices = []
        if has_pending_sends:
            choices.append('send')
        if has_pending_acks:
            choices.append('ack')

        action = self.rng.choice(choices)

        if action == 'send':
            # Deliver a random pending send (out-of-order delivery per GASV4ACCG-13)
            idx = self.rng.randint(0, len(self.pending_sends) - 1)
            station_id, price_value, version_number = self.pending_sends.pop(idx)

            # Station receives and immediately displays (GASV4ACCG-15)
            self.stations[station_id]['displayed_price'] = price_value
            self.stations[station_id]['displayed_version'] = version_number

            # Station queues ack back (GASV4ACCG-15)
            if station_id not in self.ack_queues:
                self.ack_queues[station_id] = []
            self.ack_queues[station_id].append(version_number)

        elif action == 'ack':
            # Deliver the oldest ack from a station with pending acks (GASV4ACCG-14)
            stations_with_acks = [
                sid for sid, acks in self.ack_queues.items() if acks
            ]
            station_id = self.rng.choice(stations_with_acks)
            version_number = self.ack_queues[station_id].pop(0)

            # Deliver to app (GASV4ACCG-11)
            if self.app is not None:
                self.app.ReceiveAcknowledgment(station_id, version_number)

            # Update tracking
            self.stations[station_id]['acked_version'] = version_number

        return True

    def step_until_idle(self):
        """Run steps until all in-flight messages are delivered."""
        while self.step():
            pass

    def get_station_state(self, station_id):
        """Get the current state of a station.
        
        Returns:
            {'displayed_price': value, 'displayed_version': version, 'acked_version': version}
            or None if station has not been initialized
        """
        if station_id not in self.stations:
            return None
        return self.stations[station_id].copy()

    def get_all_station_states(self):
        """Get states of all stations that have received messages.
        
        Returns:
            {station_id: {'displayed_price': ..., 'displayed_version': ..., 'acked_version': ...}, ...}
        """
        return {sid: state.copy() for sid, state in self.stations.items()}

    def get_transmission_cost(self):
        """Get total transmission cost (number of SendPrice calls).
        
        Per GASV4ACCG-17, tracks the cost incurred by sends.
        """
        return self.transmission_cost

    def get_in_flight_sends(self):
        """Get pending sends (for observation).
        
        Returns:
            [(station_id, price_value, version_number), ...]
        """
        return list(self.pending_sends)

    def get_in_flight_acks(self):
        """Get pending acks per station (for observation).
        
        Returns:
            {station_id: [version_numbers, ...]}
        """
        return {sid: list(acks) for sid, acks in self.ack_queues.items()}


class _Transport:
    """Transport interface provided to the app.
    
    The app calls send_price(...) on this object to queue price sends
    without the app or transport knowing about each other's implementation.
    This maintains the separation required by the test architecture.
    """

    def __init__(self, simulation):
        self.simulation = simulation

    def send_price(self, station_id, price_value, version_number):
        """Called by app to send a price to a station.
        
        Args:
            station_id: Target station
            price_value: Price to send
            version_number: Version from PublishPrice
        """
        self.simulation.send_price(station_id, price_value, version_number)
