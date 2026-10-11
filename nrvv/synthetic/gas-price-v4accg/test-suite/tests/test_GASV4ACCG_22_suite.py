import pytest
from nrvv_env import Simulation
import app


def test_single_price_reaches_station():
    """Single price update is correctly delivered and displayed."""
    sim = Simulation(seed=42)
    server = app.App(stations=['station1'], transport=sim.get_transport())
    sim.set_app(server)
    
    v1 = server.publish_price(100)
    sim.step_until_idle()
    
    state = sim.get_station_state('station1')
    assert state['displayed_price'] == 100
    assert state['displayed_version'] == v1


def test_multiple_prices_station_displays_latest():
    """Station eventually displays the most recent of multiple published prices."""
    sim = Simulation(seed=42)
    server = app.App(stations=['station1'], transport=sim.get_transport())
    sim.set_app(server)
    
    v1 = server.publish_price(100)
    v2 = server.publish_price(200)
    v3 = server.publish_price(300)
    
    sim.step_until_idle()
    
    state = sim.get_station_state('station1')
    assert state['displayed_price'] == 300
    assert state['displayed_version'] == v3


def test_multiple_stations_converge_to_latest_price():
    """All stations eventually display the most recent price."""
    sim = Simulation(seed=123)
    stations = ['s1', 's2', 's3']
    server = app.App(stations=stations, transport=sim.get_transport())
    sim.set_app(server)
    
    v1 = server.publish_price(100)
    v2 = server.publish_price(200)
    v3 = server.publish_price(300)
    
    sim.step_until_idle()
    
    for station_id in stations:
        state = sim.get_station_state(station_id)
        assert state['displayed_price'] == 300
        assert state['displayed_version'] == v3


def test_resend_mechanism_delivers_latest():
    """Resend mechanism ensures latest version reaches stale stations."""
    sim = Simulation(seed=999)
    server = app.App(stations=['s1'], transport=sim.get_transport())
    sim.set_app(server)
    
    v1 = server.publish_price(100)
    v2 = server.publish_price(200)
    
    # Partial delivery before resend
    for _ in range(5):
        if not sim.step():
            break
    
    # Request resend of latest to stale stations
    server.resend_to_stale_stations()
    sim.step_until_idle()
    
    state = sim.get_station_state('s1')
    assert state['displayed_price'] == 200
    assert state['displayed_version'] == v2


def test_version_numbers_monotonically_increase():
    """Each PublishPrice call assigns a higher version number."""
    sim = Simulation(seed=55)
    server = app.App(stations=['s1'], transport=sim.get_transport())
    
    v1 = server.publish_price(100)
    v2 = server.publish_price(200)
    v3 = server.publish_price(300)
    v4 = server.publish_price(400)
    
    assert v1 < v2 < v3 < v4


def test_many_prices_converges_to_highest_version():
    """Station with many price updates converges to the highest version."""
    sim = Simulation(seed=777)
    server = app.App(stations=['s1'], transport=sim.get_transport())
    sim.set_app(server)
    
    prices = [100, 150, 200, 250, 300, 350, 400]
    versions = [server.publish_price(p) for p in prices]
    
    sim.step_until_idle()
    
    state = sim.get_station_state('s1')
    assert state['displayed_price'] == 400
    assert state['displayed_version'] == versions[-1]
