class Station:
    """Represents a single station in the simulated network.
    
    Stations are simple: they apply any received message immediately (no
    versioning or deduplication) and acknowledge it. The environment ensures
    acks are delivered to the app in order.
    """

    def __init__(self, station_id):
        self.station_id = station_id
        self.last_price = None
        self.next_ack_message_id = 1
        self.received_messages = {}  # message_id -> price (acks pending for these)
