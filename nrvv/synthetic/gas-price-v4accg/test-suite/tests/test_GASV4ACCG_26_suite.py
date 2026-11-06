import pytest
import app
from nrvv_env import Simulation


def test_ack_version_updated_to_higher_version():
    """Verify that ReceiveAcknowledgment updates station's highest ack version when version is higher."""
    sim = Simulation(seed=42)
    service = app.PriceService(transport=sim.get_transport())
    sim.set_app(service)
    
    # Register station with initial ack version 0
    service.ReceiveAcknowledgment('station_A', 0)
    
    # Publish two versions
    v1 = service.PublishPrice(100)
    v2 = service.PublishPrice(200)
    
    # Acknowledge v1 first
    service.ReceiveAcknowledgment('station_A', v1)
    
    # Acknowledge higher version v2
    service.ReceiveAcknowledgment('station_A', v2)
    
    # ResendToStaleStations should not resend since station_A has acked the latest version
    cost_before = sim.get_transmission_cost()
    service.ResendToStaleStations()
    cost_after = sim.get_transmission_cost()
    assert cost_before == cost_after, "Should not resend to station with highest ack version"


def test_ack_version_not_downgraded_by_lower_version():
    """Verify that a lower version ack does not downgrade the highest ack version."""
    sim = Simulation(seed=42)
    service = app.PriceService(transport=sim.get_transport())
    sim.set_app(service)
    
    # Register station
    service.ReceiveAcknowledgment('station_A', 0)
    
    # Publish three versions
    v1 = service.PublishPrice(100)
    v2 = service.PublishPrice(200)
    v3 = service.PublishPrice(300)
    
    # Acknowledge v3 (highest)
    service.ReceiveAcknowledgment('station_A', v3)
    
    # Acknowledge lower version v1 - should not downgrade
    service.ReceiveAcknowledgment('station_A', v1)
    
    # ResendToStaleStations should not resend since highest ack is still v3
    cost_before = sim.get_transmission_cost()
    service.ResendToStaleStations()
    cost_after = sim.get_transmission_cost()
    assert cost_before == cost_after, "Should maintain highest ack version, not downgrade"


def test_multiple_stations_independent_ack_tracking():
    """Verify that different stations have independent ack version tracking."""
    sim = Simulation(seed=42)
    service = app.PriceService(transport=sim.get_transport())
    sim.set_app(service)
    
    # Register multiple stations
    service.ReceiveAcknowledgment('station_A', 0)
    service.ReceiveAcknowledgment('station_B', 0)
    service.ReceiveAcknowledgment('station_C', 0)
    
    # Publish versions
    v1 = service.PublishPrice(100)
    v2 = service.PublishPrice(200)
    v3 = service.PublishPrice(300)
    
    # Different stations ack different versions
    service.ReceiveAcknowledgment('station_A', v3)  # Latest
    service.ReceiveAcknowledgment('station_B', v1)  # Older
    service.ReceiveAcknowledgment('station_C', v2)  # Middle
    
    # ResendToStaleStations should only resend to B and C (stale relative to v3)
    cost_before = sim.get_transmission_cost()
    service.ResendToStaleStations()
    cost_after = sim.get_transmission_cost()
    # Expect 2 resends: one to station_B, one to station_C
    assert cost_after - cost_before == 2, "Should resend only to stations with ack_version < latest"


def test_ack_state_updated_only_by_receive_acknowledgment():
    """Verify that ack state is updated only through ReceiveAcknowledgment, not SendPrice."""
    sim = Simulation(seed=42)
    service = app.PriceService(transport=sim.get_transport())
    sim.set_app(service)
    
    # Register station
    service.ReceiveAcknowledgment('station_A', 0)
    
    # Publish versions
    v1 = service.PublishPrice(100)
    v2 = service.PublishPrice(200)
    
    # SendPrice sends but does not update ack state
    service.SendPrice('station_A', 100, v1)
    
    # Station's ack version should still be 0 (not updated by SendPrice)
    # ResendToStaleStations should resend v2 since station_A hasn't acked anything yet
    cost_before = sim.get_transmission_cost()
    service.ResendToStaleStations()
    cost_after = sim.get_transmission_cost()
    # Should resend because ack_version (0) < latest_version (v2)
    assert cost_after > cost_before, "Ack state should not be updated by SendPrice, only by ReceiveAcknowledgment"


def test_out_of_order_acks_maintains_highest_version():
    """Verify that out-of-order ReceiveAcknowledgment messages result in highest version being maintained."""
    sim = Simulation(seed=42)
    service = app.PriceService(transport=sim.get_transport())
    sim.set_app(service)
    
    # Register station
    service.ReceiveAcknowledgment('station_A', 0)
    
    # Publish versions
    v1 = service.PublishPrice(100)
    v2 = service.PublishPrice(200)
    v3 = service.PublishPrice(300)
    v4 = service.PublishPrice(400)
    
    # Receive acks in non-sequential order: v2, v4, v1, v3
    service.ReceiveAcknowledgment('station_A', v2)
    service.ReceiveAcknowledgment('station_A', v4)
    service.ReceiveAcknowledgment('station_A', v1)
    service.ReceiveAcknowledgment('station_A', v3)
    
    # After all acks, highest should be v4
    cost_before = sim.get_transmission_cost()
    service.ResendToStaleStations()
    cost_after = sim.get_transmission_cost()
    # Should not resend since highest ack (v4) == latest version
    assert cost_before == cost_after, "Out-of-order acks should result in highest version being maintained"


def test_station_ack_version_same_as_current_no_resend():
    """Verify that ResendToStaleStations does not resend to station with ack_version == current_latest_version."""
    sim = Simulation(seed=42)
    service = app.PriceService(transport=sim.get_transport())
    sim.set_app(service)
    
    # Register station
    service.ReceiveAcknowledgment('station_A', 0)
    
    # Publish version
    v1 = service.PublishPrice(100)
    
    # Station acks the current version
    service.ReceiveAcknowledgment('station_A', v1)
    
    # ResendToStaleStations should not resend
    cost_before = sim.get_transmission_cost()
    service.ResendToStaleStations()
    cost_after = sim.get_transmission_cost()
    assert cost_before == cost_after, "Should not resend to station at current version"


def test_new_station_starts_at_zero_ack_version():
    """Verify that a newly registered station starts with ack_version of 0."""
    sim = Simulation(seed=42)
    service = app.PriceService(transport=sim.get_transport())
    sim.set_app(service)
    
    # Register station (ack version implicitly 0)
    service.ReceiveAcknowledgment('station_A', 0)
    
    # Publish version
    v1 = service.PublishPrice(100)
    
    # New station should be considered stale and receive resend
    cost_before = sim.get_transmission_cost()
    service.ResendToStaleStations()
    cost_after = sim.get_transmission_cost()
    # Should resend to station_A since its ack_version (0) < v1
    assert cost_after > cost_before, "New station should have ack_version of 0 and be resent to"
