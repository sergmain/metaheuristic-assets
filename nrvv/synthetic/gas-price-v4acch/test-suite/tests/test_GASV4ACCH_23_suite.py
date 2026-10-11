import pytest
import app
from nrvv_env import Environment


def test_no_resend_same_price_twice():
    """Same price requested twice should not send redundantly."""
    env = Environment(seed=42)
    env.set_app(app)
    
    # First broadcast of price 100
    env.new_price_available(100)
    sends_after_first = len(env.get_sent_messages())
    
    # Second broadcast of same price 100
    env.new_price_available(100)
    sends_after_second = len(env.get_sent_messages())
    
    # Should not send again if already acknowledged
    assert sends_after_second == sends_after_first, \
        f"Resent redundantly: expected {sends_after_first} total sends, got {sends_after_second}"


def test_send_new_price_after_previous():
    """Different price should be sent even if previous price was sent."""
    env = Environment(seed=43)
    env.set_app(app)
    
    env.new_price_available(100)
    sends_100 = len(env.get_sent_messages())
    
    env.new_price_available(200)
    sends_100_and_200 = len(env.get_sent_messages())
    
    assert sends_100_and_200 > sends_100, \
        "New price should trigger sends"


def test_alternating_prices_no_resend():
    """Alternate prices should each send once, no redundant sends."""
    env = Environment(seed=44)
    env.set_app(app)
    
    # Send 100
    env.new_price_available(100)
    count_after_100 = len(env.get_sent_messages())
    
    # Send 200
    env.new_price_available(200)
    count_after_200 = len(env.get_sent_messages())
    
    # Send 100 again (should not resend)
    env.new_price_available(100)
    count_final = len(env.get_sent_messages())
    
    assert count_final == count_after_200, \
        f"Redundant resend of 100: expected {count_after_200} sends, got {count_final}"


def test_repeated_same_price_no_accumulation():
    """Calling with same price repeatedly should not accumulate sends."""
    env = Environment(seed=45)
    env.set_app(app)
    
    env.new_price_available(100)
    count_1 = len(env.get_sent_messages())
    
    env.new_price_available(100)
    env.new_price_available(100)
    env.new_price_available(100)
    count_final = len(env.get_sent_messages())
    
    assert count_final == count_1, \
        f"Accumulated redundant sends: expected {count_1}, got {count_final}"


def test_price_value_distinguishes_redundancy():
    """Only exact price matches trigger redundancy check (not message count)."""
    env = Environment(seed=46)
    env.set_app(app)
    
    env.new_price_available(100)
    env.new_price_available(101)
    env.new_price_available(102)
    count_after_three = len(env.get_sent_messages())
    
    # Resending 100 should not trigger new sends
    env.new_price_available(100)
    count_after_resend = len(env.get_sent_messages())
    
    assert count_after_resend == count_after_three, \
        "Price 100 should not resend even after other prices sent"
