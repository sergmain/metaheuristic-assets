import pytest
from nrvv_env import Environment
import app


def test_monotonic_message_ids_per_station():
    """Message IDs for each station must be monotonically increasing.
    
    This ensures that newer messages always have higher IDs than older ones.
    """
    env = Environment(seed=42)
    env.set_app(app)
    
    # Send multiple prices to trigger multiple sends
    for price in [100, 105, 110, 115, 120]:
        env.new_price_available(price)
        env.run_until_idle()
    
    # Group messages by station and verify IDs increase
    sent = env.get_sent_messages()
    by_station = {}
    for time, sid, msg_id, price in sent:
        if sid not in by_station:
            by_station[sid] = []
        by_station[sid].append(msg_id)
    
    for sid, msg_ids in by_station.items():
        for i in range(1, len(msg_ids)):
            assert msg_ids[i] > msg_ids[i-1], \
                f"Station {sid} has non-monotonic message IDs: {msg_ids}"


def test_no_message_sent_below_acked_message_id():
    """After acking message_id=N, do not send message_id<N to that station.
    
    This is the core requirement: once a station acknowledges a message,
    the service must not transmit a message with a lower ID (less recent).
    """
    env = Environment(seed=123)
    env.set_app(app)
    
    station = "station_1"
    
    # Send first price
    env.new_price_available(100)
    env.run_until_idle()
    
    # Get the message ID of the first send
    sent = env.get_sent_messages()
    m1_id = [mid for t, sid, mid, p in sent if sid == station][-1]
    msgs_at_first_send = len([1 for t, sid, mid, p in sent if sid == station])
    
    # Station acknowledges the first message
    env.app.receive_ack(station, m1_id)
    env.run_until_idle()
    
    # Send more prices
    env.new_price_available(105)
    env.new_price_available(110)
    env.run_until_idle()
    
    # Verify: all messages sent after the ack have ID > m1_id
    sent = env.get_sent_messages()
    for time, sid, msg_id, price in sent[msgs_at_first_send:]:
        if sid == station:
            assert msg_id > m1_id, \
                f"Station {sid}: sent message_id={msg_id} after acking message_id={m1_id}"


def test_multiple_stations_maintain_independent_ack_state():
    """Different stations can have different acknowledged message IDs.
    
    The ack constraint applies per-station: station A acknowledging message 1
    does not prevent station B from receiving message 1 or any other message.
    """
    env = Environment(seed=456)
    env.set_app(app)
    
    s1, s2 = "station_1", "station_2"
    
    # Send price to both stations
    env.new_price_available(100)
    env.run_until_idle()
    
    sent = env.get_sent_messages()
    m1_s1 = [mid for t, sid, mid, p in sent if sid == s1][-1]
    m1_s2 = [mid for t, sid, mid, p in sent if sid == s2][-1]
    s1_count_at_first = len([1 for t, sid, mid, p in sent if sid == s1])
    s2_count_at_first = len([1 for t, sid, mid, p in sent if sid == s2])
    
    # Only ack station 1
    env.app.receive_ack(s1, m1_s1)
    env.run_until_idle()
    
    # Send more prices
    env.new_price_available(105)
    env.new_price_available(110)
    env.run_until_idle()
    
    sent = env.get_sent_messages()
    
    # Station 1 should not receive message IDs <= m1_s1
    for time, sid, msg_id, price in sent[s1_count_at_first:]:
        if sid == s1:
            assert msg_id > m1_s1, \
                f"After acking m1={m1_s1}, station 1 sent message {msg_id}"
    
    # Station 2's messages should still be monotonic (no ack received, so no constraint)
    s2_messages = [mid for t, sid, mid, p in sent if sid == s2]
    for i in range(1, len(s2_messages)):
        assert s2_messages[i] > s2_messages[i-1], \
            f"Station 2 has non-monotonic IDs: {s2_messages}"


def test_no_duplicate_message_ids_per_station():
    """Each message_id should be unique per station (no retransmits).
    
    This prevents the service from sending the same message_id twice,
    which would be both wasteful and a violation of the monotonicity requirement.
    """
    env = Environment(seed=789)
    env.set_app(app)
    
    # Send several prices
    for price in [100, 105, 110, 115]:
        env.new_price_available(price)
        env.run_until_idle()
    
    sent = env.get_sent_messages()
    by_station = {}
    for time, sid, msg_id, price in sent:
        if sid not in by_station:
            by_station[sid] = []
        by_station[sid].append(msg_id)
    
    # Check that each station has no duplicate message IDs
    for sid, msg_ids in by_station.items():
        unique_ids = set(msg_ids)
        assert len(msg_ids) == len(unique_ids), \
            f"Station {sid} has duplicate message IDs: {msg_ids}"


def test_multiple_ack_cycles_maintain_invariant():
    """Invariant holds across multiple ack and send cycles.
    
    Tests a complex scenario: send, ack, send, ack, etc.,
    verifying that the constraint is maintained throughout.
    """
    env = Environment(seed=321)
    env.set_app(app)
    
    station = "station_1"
    prices = [100, 105, 110, 115, 120]
    acked_ids = []
    
    for price in prices:
        # Send price
        env.new_price_available(price)
        env.run_until_idle()
        
        # Get the message ID that was just sent
        sent = env.get_sent_messages()
        station_messages = [mid for t, sid, mid, p in sent if sid == station]
        latest_mid = station_messages[-1]
        
        # Ack it
        env.app.receive_ack(station, latest_mid)
        acked_ids.append(latest_mid)
        env.run_until_idle()
    
    # Verify acked IDs are monotonically increasing
    for i in range(1, len(acked_ids)):
        assert acked_ids[i] > acked_ids[i-1], \
            f"Acked message IDs not monotonic: {acked_ids}"
    
    # Verify all sent message IDs for the station are monotonic
    sent = env.get_sent_messages()
    station_messages = [mid for t, sid, mid, p in sent if sid == station]
    for i in range(1, len(station_messages)):
        assert station_messages[i] > station_messages[i-1], \
            f"Sent message IDs not monotonic: {station_messages}"


def test_no_lower_id_sent_after_higher_id_acked():
    """Core invariant: after acking a higher message_id, don't send lower ones.
    
    Tests the scenario where message_id=2 is acknowledged before message_id=1
    is sent (due to out-of-order delivery). Once message_id=2 is acked, 
    message_id=1 should never be sent.
    """
    env = Environment(seed=555)
    env.set_app(app)
    
    station = "station_1"
    
    # Send multiple prices
    env.new_price_available(100)
    env.new_price_available(105)
    env.new_price_available(110)
    env.run_until_idle()
    
    # Get all sent message IDs
    sent = env.get_sent_messages()
    msg_ids = [mid for t, sid, mid, p in sent if sid == station]
    
    # Ack the second message (if at least 2 messages were sent)
    if len(msg_ids) >= 2:
        env.app.receive_ack(station, msg_ids[1])
        env.run_until_idle()
        
        # After acking msg_ids[1], we should not see msg_ids[0] again
        # (and certainly not any message_id <= msg_ids[1])
        sent_after = env.get_sent_messages()
        post_ack_messages = [(t, sid, mid, p) for t, sid, mid, p in sent_after]
        
        # Count messages for station before ack
        initial_count = len(msg_ids)
        
        # Check that no new message with ID <= msg_ids[1] is sent
        for time, sid, mid, price in post_ack_messages[initial_count:]:
            if sid == station:
                assert mid > msg_ids[1], \
                    f"After acking {msg_ids[1]}, station {sid} sent message_id={mid}"
