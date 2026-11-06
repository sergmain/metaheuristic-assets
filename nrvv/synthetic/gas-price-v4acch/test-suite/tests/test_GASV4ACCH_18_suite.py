import pytest
from nrvv_env import Environment
import app


def test_gasv4acch_18_sends_exactly_two_messages():
    """Verify that submitting P1, P2, P3 in flight results in exactly 2 sends."""
    env = Environment(seed=42)
    env.set_app(app)
    
    # Submit three prices in succession (P2 and P3 arrive while P1 in flight)
    app.new_price_available(100.0)  # P1
    app.new_price_available(200.0)  # P2
    app.new_price_available(300.0)  # P3
    
    # Run all events to completion
    env.run_until_idle()
    
    sent = env.get_sent_messages()
    
    # Should send exactly 2 messages, not 3 (P2 was overwritten)
    assert len(sent) == 2, (
        f"Expected exactly 2 messages sent, got {len(sent)}. "
        f"Sent: {sent}"
    )


def test_gasv4acch_18_sends_p1_and_p3_not_p2():
    """Verify that P1 is sent first, P2 is discarded, and P3 is sent second."""
    env = Environment(seed=42)
    env.set_app(app)
    
    # Submit three prices
    app.new_price_available(100.0)  # P1
    app.new_price_available(200.0)  # P2
    app.new_price_available(300.0)  # P3
    
    env.run_until_idle()
    
    sent = env.get_sent_messages()
    
    # First message should have price 100.0 (P1)
    assert len(sent) >= 1, "Expected at least 1 message sent"
    assert sent[0][3] == 100.0, (
        f"First sent message should have price 100.0 (P1), got {sent[0][3]}"
    )
    
    # Second message should have price 300.0 (P3, not P2)
    assert len(sent) >= 2, "Expected at least 2 messages sent"
    assert sent[1][3] == 300.0, (
        f"Second sent message should have price 300.0 (P3), got {sent[1][3]}. "
        f"P2 (200.0) should have been overwritten."
    )


def test_gasv4acch_18_p3_sent_after_p1_ack():
    """Verify that P3 is sent only after P1 is acknowledged."""
    env = Environment(seed=42)
    env.set_app(app)
    
    # Submit three prices in quick succession
    app.new_price_available(100.0)  # P1
    app.new_price_available(200.0)  # P2
    app.new_price_available(300.0)  # P3
    
    env.run_until_idle()
    
    sent = env.get_sent_messages()
    acked = env.get_delivered_acks()
    
    assert len(sent) >= 2, "Expected at least 2 messages sent"
    assert len(acked) >= 1, "Expected at least 1 acknowledgment"
    
    # Get message IDs
    p1_message_id = sent[0][2]
    p3_send_time = sent[1][0]
    
    # Find when P1 was acknowledged
    p1_ack_time = None
    for ack_time, station_id, ack_message_id in acked:
        if ack_message_id == p1_message_id:
            p1_ack_time = ack_time
            break
    
    assert p1_ack_time is not None, (
        f"P1 (message {p1_message_id}) should have been acknowledged"
    )
    
    # P3 should be sent only after P1 is acknowledged
    assert p1_ack_time <= p3_send_time, (
        f"P1 acknowledgment (time {p1_ack_time}) should arrive before or at "
        f"P3 send time ({p3_send_time})"
    )


def test_gasv4acch_18_sequential_message_ids():
    """Verify that message IDs are sequential for the station."""
    env = Environment(seed=42)
    env.set_app(app)
    
    # Submit three prices
    app.new_price_available(100.0)
    app.new_price_available(200.0)
    app.new_price_available(300.0)
    
    env.run_until_idle()
    
    sent = env.get_sent_messages()
    
    assert len(sent) >= 2, "Expected at least 2 messages sent"
    
    # Message IDs should be 1, 2 (sequential)
    assert sent[0][2] == 1, f"First message_id should be 1, got {sent[0][2]}"
    assert sent[1][2] == 2, f"Second message_id should be 2, got {sent[1][2]}"


def test_gasv4acch_18_different_seed():
    """Verify the behavior holds with a different random seed."""
    env = Environment(seed=123)
    env.set_app(app)
    
    app.new_price_available(50.0)
    app.new_price_available(75.0)
    app.new_price_available(95.0)
    
    env.run_until_idle()
    
    sent = env.get_sent_messages()
    
    # Still should send exactly 2 messages
    assert len(sent) == 2, (
        f"Expected 2 messages sent with seed=123, got {len(sent)}"
    )
    
    # First should be the first price
    assert sent[0][3] == 50.0
    
    # Second should be the last price (middle was overwritten)
    assert sent[1][3] == 95.0


def test_gasv4acch_18_all_acks_received():
    """Verify that all sent messages receive acknowledgments."""
    env = Environment(seed=42)
    env.set_app(app)
    
    app.new_price_available(100.0)
    app.new_price_available(200.0)
    app.new_price_available(300.0)
    
    env.run_until_idle()
    
    sent = env.get_sent_messages()
    acked = env.get_delivered_acks()
    
    # Every message should have been acknowledged
    sent_message_ids = {msg[2] for msg in sent}
    acked_message_ids = {ack[2] for ack in acked}
    
    assert sent_message_ids == acked_message_ids, (
        f"All sent message IDs should be acknowledged. "
        f"Sent: {sent_message_ids}, Acked: {acked_message_ids}"
    )
