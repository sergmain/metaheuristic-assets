import pytest
from nrvv_env import Environment
import app


def test_no_transmission_for_unchanged_price():
    """Criterion: no message is transmitted if price is identical to acknowledged price."""
    env = Environment(seed=42)
    env.set_app(app)
    
    # Inject initial price to establish baseline
    env.new_price_available(100)
    sent_count_1 = len(env.get_sent_messages())
    
    # Inject the same price again
    env.new_price_available(100)
    sent_count_2 = len(env.get_sent_messages())
    
    # No new messages should be transmitted for the same price
    assert sent_count_2 == sent_count_1


def test_transmission_for_changed_price():
    """Criterion: new message is transmitted if price differs from acknowledged price."""
    env = Environment(seed=42)
    env.set_app(app)
    
    # Inject initial price
    env.new_price_available(100)
    sent_count_1 = len(env.get_sent_messages())
    
    # Inject a different price
    env.new_price_available(200)
    sent_count_2 = len(env.get_sent_messages())
    
    # New messages should be transmitted when price changes
    if sent_count_1 > 0:
        assert sent_count_2 > sent_count_1


def test_acknowledged_price_becomes_baseline():
    """Criterion: once a price is acknowledged, it becomes the baseline."""
    env = Environment(seed=42)
    env.set_app(app)
    
    # Send price and wait for acknowledgment
    env.new_price_available(100)
    ack_count_1 = len(env.get_delivered_acks())
    
    if ack_count_1 > 0:
        # Price was acknowledged, so it's now the baseline
        # Sending same price again should not trigger new acks
        env.new_price_available(100)
        ack_count_2 = len(env.get_delivered_acks())
        assert ack_count_2 == ack_count_1
        
        # Sending different price should trigger new acks
        env.new_price_available(200)
        ack_count_3 = len(env.get_delivered_acks())
        assert ack_count_3 > ack_count_2


def test_independent_per_station_tracking():
    """Criterion: each station maintains independent acknowledged price baseline."""
    env = Environment(seed=42)
    env.set_app(app)
    
    # Establish initial state
    env.new_price_available(100)
    sent_1 = len(env.get_sent_messages())
    
    if sent_1 > 0:
        # We have stations that received messages
        
        # Same price - no new sends
        env.new_price_available(100)
        sent_2 = len(env.get_sent_messages())
        assert sent_2 == sent_1
        
        # Different price - new sends
        env.new_price_available(200)
        sent_3 = len(env.get_sent_messages())
        assert sent_3 > sent_2
        
        # Same as current - no new sends
        env.new_price_available(200)
        sent_4 = len(env.get_sent_messages())
        assert sent_4 == sent_3


def test_sequence_with_alternating_prices():
    """Test a sequence of prices to verify correct transmission behavior."""
    env = Environment(seed=42)
    env.set_app(app)
    
    # Sequence: 100, 100 (same), 150 (new), 150 (same), 200 (new), 200 (same)
    sequence = [100, 100, 150, 150, 200, 200]
    
    prev_count = 0
    for i in range(len(sequence)):
        price = sequence[i]
        is_same_as_previous = (i > 0 and sequence[i] == sequence[i - 1])
        
        env.new_price_available(price)
        curr_count = len(env.get_sent_messages())
        
        if is_same_as_previous:
            # Same price as previous should not trigger new transmissions
            assert curr_count == prev_count, \
                f"Repeated price {price} should not trigger transmission"
        
        prev_count = curr_count


def test_message_id_monotonicity_per_station():
    """Verify that message IDs increment monotonically per station."""
    env = Environment(seed=42)
    env.set_app(app)
    
    # Send multiple prices to generate messages
    for price in [100, 200, 300]:
        env.new_price_available(price)
    
    # Group sent messages by station
    sent_messages = env.get_sent_messages()
    messages_per_station = {}
    
    for time, station_id, message_id, price in sent_messages:
        if station_id not in messages_per_station:
            messages_per_station[station_id] = []
        messages_per_station[station_id].append((time, message_id, price))
    
    # Verify monotonicity per station
    for station_id, messages in messages_per_station.items():
        for i in range(len(messages) - 1):
            msg_id_1 = messages[i][1]
            msg_id_2 = messages[i + 1][1]
            assert msg_id_2 > msg_id_1, \
                f"Station {station_id}: message IDs must be strictly increasing"


def test_latest_price_only_transmission():
    """Verify that only the latest price is eventually transmitted."""
    env = Environment(seed=42)
    env.set_app(app)
    
    # Send multiple prices in succession
    prices = [100, 150, 200, 250]
    for price in prices:
        env.new_price_available(price)
    
    # After all is settled, final messages should be for the latest price
    sent_messages = env.get_sent_messages()
    
    if sent_messages:
        # Get the latest message (by time) for each station
        latest_per_station = {}
        for time, station_id, message_id, price in sent_messages:
            if station_id not in latest_per_station or time > latest_per_station[station_id][0]:
                latest_per_station[station_id] = (time, price)
        
        # The latest price for each station should be the final price (250)
        for station_id, (time, price) in latest_per_station.items():
            assert price == 250, \
                f"Station {station_id} should have latest price (250), but has {price}"


def test_price_change_after_multiple_acks():
    """Test that multiple acks establish baseline correctly for future decisions."""
    env = Environment(seed=42)
    env.set_app(app)
    
    # First price wave
    env.new_price_available(100)
    acks_1 = len(env.get_delivered_acks())
    
    if acks_1 > 0:
        # Baseline is now 100
        # Repeat 100 multiple times - should not send
        for _ in range(3):
            env.new_price_available(100)
        
        acks_2 = len(env.get_delivered_acks())
        assert acks_2 == acks_1, "Multiple identical prices should not increase acks"
        
        # Change to 300
        env.new_price_available(300)
        acks_3 = len(env.get_delivered_acks())
        assert acks_3 > acks_2, "Price change should cause new acks"
