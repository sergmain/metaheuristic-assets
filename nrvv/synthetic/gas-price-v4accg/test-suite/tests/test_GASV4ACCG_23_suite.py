import pytest
import app
from nrvv_env import Simulation


def test_single_acknowledgment_tracked():
    """A single acknowledgment updates the station's ack status."""
    sim = Simulation(seed=42)
    app.set_transport(sim.get_transport())
    
    v = app.PublishPrice(100.0)
    app.SendPrice('station_a', 100.0, v)
    sim.step_until_idle()
    
    assert app.get_ack_version('station_a') == v


def test_multiple_acknowledgments_show_highest_version():
    """Multiple acks are tracked, showing the highest version."""
    sim = Simulation(seed=43)
    app.set_transport(sim.get_transport())
    
    v1 = app.PublishPrice(100.0)
    v2 = app.PublishPrice(101.0)
    v3 = app.PublishPrice(102.0)
    
    app.SendPrice('station_a', 100.0, v1)
    app.SendPrice('station_a', 101.0, v2)
    app.SendPrice('station_a', 102.0, v3)
    
    sim.step_until_idle()
    
    assert app.get_ack_version('station_a') == v3


def test_independent_ack_status_per_station():
    """Each station's ack status is tracked independently."""
    sim = Simulation(seed=44)
    app.set_transport(sim.get_transport())
    
    v1 = app.PublishPrice(100.0)
    v2 = app.PublishPrice(101.0)
    
    # Station A acks v1 only
    app.SendPrice('station_a', 100.0, v1)
    
    # Station B acks v1 and v2
    app.SendPrice('station_b', 100.0, v1)
    app.SendPrice('station_b', 101.0, v2)
    
    sim.step_until_idle()
    
    assert app.get_ack_version('station_a') == v1
    assert app.get_ack_version('station_b') == v2


def test_ordered_acks_fifo_per_station():
    """Acknowledgments arrive in FIFO order per station (Simulation contract)."""
    sim = Simulation(seed=45)
    app.set_transport(sim.get_transport())
    
    versions = [app.PublishPrice(100.0 + i) for i in range(4)]
    
    # Send all versions to same station
    for v, price in zip(versions, [100.0, 101.0, 102.0, 103.0]):
        app.SendPrice('station_x', price, v)
    
    sim.step_until_idle()
    
    # All acks should be received due to FIFO order
    assert app.get_ack_version('station_x') == versions[-1]


def test_resend_uses_ack_status_for_targeting():
    """ResendToStaleStations uses ack status to identify which stations need resend."""
    sim = Simulation(seed=46)
    app.set_transport(sim.get_transport())
    
    v1 = app.PublishPrice(100.0)
    v2 = app.PublishPrice(101.0)
    
    # Both stations ack v1
    app.SendPrice('station_a', 100.0, v1)
    app.SendPrice('station_b', 100.0, v1)
    sim.step_until_idle()
    
    # Only station_a gets v2
    app.SendPrice('station_a', 101.0, v2)
    sim.step_until_idle()
    
    # Verify statuses before resend
    assert app.get_ack_version('station_a') == v2
    assert app.get_ack_version('station_b') == v1
    
    # Resend to stale stations
    cost_before = sim.get_transmission_cost()
    app.ResendToStaleStations()
    sim.step_until_idle()
    
    # station_b should now have v2
    assert app.get_ack_version('station_b') == v2
    # Should have incremented transmission cost
    assert sim.get_transmission_cost() > cost_before
