import pytest
import app
from nrvv_env import Environment


def test_station_eventually_applies_transmitted_price():
    """A station shall eventually apply a transmitted price."""
    env = Environment(seed=42)
    env.set_app(app)
    
    env.new_price_available(100.0)
    
    delivered = env.get_delivered_messages()
    assert delivered, "App did not send any messages"
    
    stations = {sid for _, sid, _, _ in delivered}
    for station_id in stations:
        assert env.get_station_price(station_id) == 100.0


def test_stations_eventually_apply_new_price():
    """A station shall eventually apply a new price after receiving an initial price."""
    env = Environment(seed=222)
    env.set_app(app)
    
    env.new_price_available(100.0)
    env.new_price_available(200.0)
    
    delivered = env.get_delivered_messages()
    stations = {sid for _, sid, _, _ in delivered}
    
    for station_id in stations:
        assert env.get_station_price(station_id) == 200.0


def test_stations_settle_on_latest_of_multiple_prices():
    """Stations shall eventually settle on the most recent price among multiple transmissions."""
    env = Environment(seed=333)
    env.set_app(app)
    
    prices = [100.0, 150.0, 200.0, 250.0, 300.0]
    for price in prices:
        env.new_price_available(price)
    
    delivered = env.get_delivered_messages()
    stations = {sid for _, sid, _, _ in delivered}
    
    for station_id in stations:
        assert env.get_station_price(station_id) == 300.0


def test_stations_cease_using_earlier_prices():
    """Stations shall cease to operate with earlier prices after newer prices are transmitted."""
    env = Environment(seed=444)
    env.set_app(app)
    
    env.new_price_available(100.0)
    env.new_price_available(200.0)
    env.new_price_available(300.0)
    
    delivered = env.get_delivered_messages()
    stations = {sid for _, sid, _, _ in delivered}
    
    for station_id in stations:
        current = env.get_station_price(station_id)
        assert current == 300.0
        assert current not in [100.0, 200.0]


def test_rapid_price_updates_converge():
    """Stations shall settle on the latest price even with rapid successive price updates."""
    env = Environment(seed=555)
    env.set_app(app)
    
    for i in range(1, 11):
        env.new_price_available(float(i * 10))
    
    delivered = env.get_delivered_messages()
    stations = {sid for _, sid, _, _ in delivered}
    
    for station_id in stations:
        assert env.get_station_price(station_id) == 100.0


def test_all_stations_converge_to_same_latest_price():
    """All stations shall eventually operate with the same latest price."""
    env = Environment(seed=666)
    env.set_app(app)
    
    env.new_price_available(100.0)
    env.new_price_available(200.0)
    env.new_price_available(300.0)
    
    delivered = env.get_delivered_messages()
    stations = list({sid for _, sid, _, _ in delivered})
    
    if len(stations) > 1:
        prices = [env.get_station_price(sid) for sid in stations]
        assert len(set(prices)) == 1
        assert prices[0] == 300.0
    elif stations:
        assert env.get_station_price(stations[0]) == 300.0
