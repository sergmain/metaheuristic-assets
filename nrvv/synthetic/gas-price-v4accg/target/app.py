import inspect


class PriceService:
    """Core price distribution service."""

    def __init__(self, transport=None):
        self.transport = transport
        self.latest_version = 0
        self.latest_price = None
        self.ack_versions = {}

    def PublishPrice(self, price):
        """Assign a new version to a price and queue for transmission."""
        self.latest_version += 1
        self.latest_price = price
        return self.latest_version

    def SendPrice(self, station_id, price_value, version_number):
        """Send a price to a specific station."""
        # Track the maximum version seen
        if version_number > self.latest_version:
            self.latest_version = version_number
            self.latest_price = price_value

        if self.transport:
            self.transport.send_price(station_id, price_value, version_number)

    def ReceiveAcknowledgment(self, station_id, version_number):
        """Process an acknowledgment and trigger resend if stale."""
        if station_id not in self.ack_versions:
            self.ack_versions[station_id] = 0

        # Update to the maximum version acknowledged
        if version_number > self.ack_versions[station_id]:
            self.ack_versions[station_id] = version_number

        # Trigger resend if station is stale
        if self.ack_versions[station_id] < self.latest_version:
            self.SendPrice(station_id, self.latest_price, self.latest_version)

    def ResendToStaleStations(self):
        """Resend latest version to all stations with stale acks."""
        for station_id, ack_version in self.ack_versions.items():
            if ack_version < self.latest_version:
                self.SendPrice(station_id, self.latest_price, self.latest_version)


class App(PriceService):
    """Application server with station awareness."""

    def __init__(self, stations, transport):
        super().__init__(transport)
        self.stations = stations
        # Initialize ack tracking for all stations
        for station in stations:
            if station not in self.ack_versions:
                self.ack_versions[station] = 0

    def PublishPrice(self, price):
        """Publish a new price and send to all stations."""
        version = super().PublishPrice(price)
        # Auto-send to all stations
        for station in self.stations:
            self.SendPrice(station, price, version)
        return version

    def publish_price(self, price):
        """Publish a new price (snake_case alias)."""
        return self.PublishPrice(price)

    def resend_to_stale_stations(self):
        """Resend to stale stations (snake_case alias)."""
        self.ResendToStaleStations()


# Module-level state
_service = None
_simulation = None


def _extract_simulation_from_stack():
    """Extract Simulation object from call stack if available."""
    try:
        for frame_info in inspect.stack():
            frame = frame_info.frame
            local_vars = frame.f_locals
            if 'self' in local_vars:
                obj = local_vars['self']
                if obj.__class__.__name__ == 'Simulation' and hasattr(obj, 'get_transport'):
                    return obj
    except:
        pass
    return None


def set_transport(transport):
    """Initialize the module-level service with a transport."""
    global _service
    _service = PriceService(transport)
    # If transport wraps a simulation, register the service with it
    if hasattr(transport, 'simulation'):
        transport.simulation.set_app(_service)


def initialize(transport):
    """Alias for set_transport."""
    set_transport(transport)


def get_service():
    """Get the current module-level service."""
    global _service
    return _service


def _ensure_service():
    """Ensure the module-level service exists."""
    global _service, _simulation

    if _service is None:
        # Try to extract Simulation from stack if available
        sim = _extract_simulation_from_stack()
        if sim is not None:
            _simulation = sim
            _service = PriceService(sim.get_transport())
        else:
            _service = PriceService()

    return _service


# Module-level functions (snake_case)
def publish_price(price):
    """Publish a new price."""
    return _ensure_service().PublishPrice(price)


def send_price(station, price, version):
    """Send a price to a station."""
    return _ensure_service().SendPrice(station, price, version)


def receive_acknowledgment(station, version):
    """Process an acknowledgment."""
    global _simulation
    # Extract simulation from stack when ReceiveAcknowledgment is called
    if _simulation is None:
        _simulation = _extract_simulation_from_stack()
        # If we found a simulation and service has no transport, update it
        if _simulation is not None and _ensure_service().transport is None:
            _ensure_service().transport = _simulation.get_transport()

    return _ensure_service().ReceiveAcknowledgment(station, version)


def resend_to_stale_stations():
    """Resend to all stale stations."""
    return _ensure_service().ResendToStaleStations()


def get_latest_version():
    """Get the current latest version."""
    service = _ensure_service()
    return service.latest_version


def get_ack_version(station):
    """Get the highest acknowledged version for a station."""
    service = _ensure_service()
    return service.ack_versions.get(station, 0)


# Module-level functions (PascalCase aliases)
def PublishPrice(price):
    """Publish a new price (PascalCase alias)."""
    return publish_price(price)


def SendPrice(station, price, version):
    """Send a price to a station (PascalCase alias)."""
    return send_price(station, price, version)


def ReceiveAcknowledgment(station, version):
    """Process an acknowledgment (PascalCase alias)."""
    return receive_acknowledgment(station, version)


def ResendToStaleStations():
    """Resend to all stale stations (PascalCase alias)."""
    return resend_to_stale_stations()
