import pytest
import app
from nrvv_env import Environment


def test_single_message_starts_at_one_or_higher():
    """Single message to a station has message_id >= 1."""
    env = Environment(seed=42)
    env.set_app(app)
    
    env.new_price_available(10.0)
    
    sent = env.get_sent_messages()
    assert len(sent) > 0, "No messages were sent"
    
    for time, station_id, message_id, price in sent:
        assert message_id >= 1, f"Station {station_id}: message_id {message_id} < 1"


def test_strictly_increasing_ids_per_station():
    """Messages to the same station have strictly increasing IDs."""
    env = Environment(seed=111)
    env.set_app(app)
    
    # Multiple prices trigger multiple messages per station
    for price in [10.0, 20.0, 30.0, 40.0]:
        env.new_price_available(price)
    
    sent = env.get_sent_messages()
    
    # Group messages by station
    by_station = {}
    for time, station_id, message_id, price in sent:
        if station_id not in by_station:
            by_station[station_id] = []
        by_station[station_id].append(message_id)
    
    # Each station must have strictly increasing IDs
    for station_id, ids in by_station.items():
        for i in range(len(ids) - 1):
            assert ids[i] < ids[i + 1], \
                f"Station {station_id}: message_id {ids[i]} not < {ids[i + 1]}"


def test_message_id_greater_than_last_acknowledged():
    """No message with ID <= last acknowledged should be transmitted."""
    env = Environment(seed=222)
    env.set_app(app)
    
    # Send multiple prices to generate messages and acks
    for price in [10.0, 20.0, 30.0, 40.0, 50.0]:
        env.new_price_available(price)
    
    sent = env.get_sent_messages()
    acks = env.get_delivered_acks()
    
    # Track last acknowledged message_id per station
    last_acked = {}
    
    # Build chronological event list combining sends and acks
    events = []
    for time, station_id, message_id, price in sent:
        events.append((time, 'send', station_id, message_id))
    for time, station_id, message_id in acks:
        events.append((time, 'ack', station_id, message_id))
    
    events.sort()
    
    # Process events in chronological order
    for time, event_type, station_id, message_id in events:
        if event_type == 'ack':
            # Update last acknowledged for this station
            last_acked[station_id] = message_id
        else:  # send
            # Verify that sent message_id > last acknowledged
            prior_ack = last_acked.get(station_id, 0)
            assert message_id > prior_ack, \
                f"Station {station_id}: sent message_id {message_id} <= last_acked {prior_ack}"


def test_multiple_stations_independent_sequences():
    """Different stations have independent monotonic ID sequences."""
    env = Environment(seed=333)
    env.set_app(app)
    
    env.new_price_available(100.0)
    env.new_price_available(200.0)
    env.new_price_available(300.0)
    
    sent = env.get_sent_messages()
    
    # Group messages by station
    by_station = {}
    for time, station_id, message_id, price in sent:
        if station_id not in by_station:
            by_station[station_id] = []
        by_station[station_id].append(message_id)
    
    # Each station should have strictly increasing IDs independent of others
    for station_id, ids in by_station.items():
        for i in range(len(ids) - 1):
            assert ids[i] < ids[i + 1], \
                f"Station {station_id}: IDs not strictly increasing: {ids}"


def test_no_duplicate_ids_per_station():
    """Each station never receives duplicate message IDs."""
    env = Environment(seed=444)
    env.set_app(app)
    
    for price in [10.0, 20.0, 30.0]:
        env.new_price_available(price)
    
    sent = env.get_sent_messages()
    
    # Group by station
    by_station = {}
    for time, station_id, message_id, price in sent:
        if station_id not in by_station:
            by_station[station_id] = []
        by_station[station_id].append(message_id)
    
    # Each station should have unique message IDs
    for station_id, ids in by_station.items():
        assert len(ids) == len(set(ids)), \
            f"Station {station_id} has duplicate message IDs: {ids}"


def test_ack_ordering_maintains_constraint():
    """Acks arrive in order and constraint is maintained throughout."""
    env = Environment(seed=555)
    env.set_app(app)
    
    for price in [5.0, 15.0, 25.0, 35.0]:
        env.new_price_available(price)
    
    sent = env.get_sent_messages()
    acks = env.get_delivered_acks()
    
    # Verify acks are in order per station
    by_station_acks = {}
    for time, station_id, message_id in acks:
        if station_id not in by_station_acks:
            by_station_acks[station_id] = []
        by_station_acks[station_id].append(message_id)
    
    # Acks should be strictly increasing per station
    for station_id, ack_ids in by_station_acks.items():
        for i in range(len(ack_ids) - 1):
            assert ack_ids[i] < ack_ids[i + 1], \
                f"Station {station_id}: acks not in order: {ack_ids}"
