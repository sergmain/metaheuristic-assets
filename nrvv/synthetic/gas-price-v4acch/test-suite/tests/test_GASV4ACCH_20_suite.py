import pytest
import app
from nrvv_env import Environment


def test_single_station_monotonic_message_ids():
    """Message IDs are monotonically increasing for a single station."""
    env = Environment(seed=42)
    env.set_app(app)
    
    # Trigger multiple price messages
    env.new_price_available(100)
    env.new_price_available(101)
    env.new_price_available(102)
    
    sent = env.get_sent_messages()
    assert len(sent) > 0, "No messages sent"
    
    # Group messages by station
    by_station = {}
    for time, station_id, msg_id, price in sent:
        if station_id not in by_station:
            by_station[station_id] = []
        by_station[station_id].append(msg_id)
    
    # Verify monotonic increasing for each station
    for station_id, msg_ids in by_station.items():
        for i in range(len(msg_ids) - 1):
            assert msg_ids[i] < msg_ids[i+1], \
                f"Station {station_id}: message IDs not monotonic: {msg_ids}"


def test_station_message_id_pair_uniqueness():
    """Each (station_id, message_id) pair is unique."""
    env = Environment(seed=123)
    env.set_app(app)
    
    # Send multiple prices to generate many messages
    for price in range(100, 115):
        env.new_price_available(price)
    
    sent = env.get_sent_messages()
    
    # Extract (station_id, message_id) pairs
    pairs = [(station_id, msg_id) for _, station_id, msg_id, _ in sent]
    
    # Verify all pairs are unique
    assert len(pairs) == len(set(pairs)), \
        f"Duplicate (station_id, message_id) pairs found"


def test_no_reuse_of_message_id_pairs():
    """No (station_id, message_id) pair is ever reused."""
    env = Environment(seed=456)
    env.set_app(app)
    
    seen_pairs = set()
    
    # Send prices in batches and verify no reuse
    for batch in range(3):
        for price in range(100 + batch * 5, 105 + batch * 5):
            env.new_price_available(price)
        
        sent = env.get_sent_messages()
        current_pairs = set((station_id, msg_id) for _, station_id, msg_id, _ in sent)
        
        # Check for reused pairs
        reused = seen_pairs & current_pairs
        assert not reused, \
            f"Reused (station_id, message_id) pairs detected: {reused}"
        
        seen_pairs = current_pairs


def test_multiple_stations_independent_sequences():
    """Each station maintains its own independent message ID sequence."""
    env = Environment(seed=789)
    env.set_app(app)
    
    # Send multiple prices to trigger messages
    for price in range(100, 110):
        env.new_price_available(price)
    
    sent = env.get_sent_messages()
    
    # Group by station
    by_station = {}
    for time, station_id, msg_id, price in sent:
        if station_id not in by_station:
            by_station[station_id] = []
        by_station[station_id].append(msg_id)
    
    # Verify each station has monotonically increasing IDs
    for station_id, msg_ids in by_station.items():
        # Check that they are in sorted order (monotonic)
        assert msg_ids == sorted(msg_ids), \
            f"Station {station_id}: message IDs not monotonically increasing: {msg_ids}"


def test_monotonic_across_acknowledgments():
    """Message IDs remain monotonically increasing even after acknowledgments."""
    env = Environment(seed=222)
    env.set_app(app)
    
    # Send initial price and let acknowledgments happen
    env.new_price_available(100)
    env.run_until_idle()
    
    acks_batch1 = env.get_delivered_acks()
    assert len(acks_batch1) > 0 or len(env.get_sent_messages()) > 0
    
    # Send more prices
    env.new_price_available(101)
    env.new_price_available(102)
    env.run_until_idle()
    
    sent = env.get_sent_messages()
    
    # Group by station and verify monotonicity
    by_station = {}
    for time, station_id, msg_id, price in sent:
        if station_id not in by_station:
            by_station[station_id] = []
        by_station[station_id].append(msg_id)
    
    for station_id, msg_ids in by_station.items():
        assert msg_ids == sorted(msg_ids), \
            f"After acks, station {station_id} IDs not monotonic: {msg_ids}"


def test_comprehensive_uniqueness_and_monotonicity():
    """Comprehensive test: all pairs unique and all sequences monotonic."""
    env = Environment(seed=999)
    env.set_app(app)
    
    # Generate many messages
    for price in range(100, 125):
        env.new_price_available(price)
    
    sent = env.get_sent_messages()
    
    # Extract pairs and verify uniqueness
    pairs = [(station_id, msg_id) for _, station_id, msg_id, _ in sent]
    assert len(pairs) == len(set(pairs)), \
        "Duplicate (station_id, message_id) pairs detected"
    
    # Group by station and verify monotonicity
    by_station = {}
    for time, station_id, msg_id, price in sent:
        if station_id not in by_station:
            by_station[station_id] = []
        by_station[station_id].append(msg_id)
    
    for station_id, msg_ids in by_station.items():
        for i in range(len(msg_ids) - 1):
            assert msg_ids[i] < msg_ids[i+1], \
                f"Station {station_id}: non-monotonic sequence {msg_ids}"


def test_message_id_starts_from_consistent_base():
    """All stations start their message ID sequence from the same base value."""
    env = Environment(seed=333)
    env.set_app(app)
    
    # Send initial price
    env.new_price_available(100)
    
    sent = env.get_sent_messages()
    
    # Get first message ID for each station
    first_ids = {}
    for time, station_id, msg_id, price in sent:
        if station_id not in first_ids:
            first_ids[station_id] = msg_id
    
    # All stations should start from the same base value
    id_values = set(first_ids.values())
    assert len(id_values) == 1, \
        f"Stations have different starting message IDs: {first_ids}"
    
    # Verify the base is 1 (standard starting point)
    assert list(id_values)[0] == 1, \
        f"Message IDs should start at 1, got {list(id_values)[0]}"
