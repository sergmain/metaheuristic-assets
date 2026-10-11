import pytest
import app
from nrvv_env import Simulation


def test_resend_only_to_non_acking_stations_seed42():
    """Resend targets only stations that haven't acked the latest version."""
    sim = Simulation(seed=42)
    transport = sim.get_transport()
    
    # Initialize app with transport
    app.set_transport(transport)
    sim.set_app(app)
    
    # Publish a price
    version = app.publish_price(100.0)
    
    # Run simulation to reach a mixed state (some acks, some pending)
    for _ in range(50):
        if not sim.step():
            break
    
    # Identify which stations haven't acked the latest version
    states = sim.get_all_station_states()
    non_acking = {
        sid for sid, state in states.items()
        if state['acked_version'] < version
    }
    
    # Skip if all stations are in the same ack state (unlucky seed)
    acking = {
        sid for sid, state in states.items()
        if state['acked_version'] >= version
    }
    if not non_acking or not acking:
        pytest.skip("All stations in same ack state")
    
    # Trigger resend
    app.resend_to_stale_stations()
    
    # Verify resend targets match non-acking stations exactly
    in_flight_sends = sim.get_in_flight_sends()
    resend_targets = {sid for sid, _, _ in in_flight_sends}
    
    assert resend_targets == non_acking, \
        f"Resend targeted {resend_targets} but should target {non_acking}"


def test_resend_only_to_non_acking_stations_seed100():
    """Resend targets only non-acking stations (alternate seed)."""
    sim = Simulation(seed=100)
    transport = sim.get_transport()
    
    app.set_transport(transport)
    sim.set_app(app)
    
    version = app.publish_price(100.0)
    
    # Simulate message delivery
    for _ in range(50):
        if not sim.step():
            break
    
    states = sim.get_all_station_states()
    non_acking = {
        sid for sid, state in states.items()
        if state['acked_version'] < version
    }
    
    acking = {
        sid for sid, state in states.items()
        if state['acked_version'] >= version
    }
    if not non_acking or not acking:
        pytest.skip("All stations in same ack state")
    
    app.resend_to_stale_stations()
    
    in_flight_sends = sim.get_in_flight_sends()
    resend_targets = {sid for sid, _, _ in in_flight_sends}
    
    assert resend_targets == non_acking


def test_resend_includes_all_non_acking_stations_seed200():
    """Resend includes every station that hasn't acked."""
    sim = Simulation(seed=200)
    transport = sim.get_transport()
    
    app.set_transport(transport)
    sim.set_app(app)
    
    version = app.publish_price(100.0)
    
    # Simulate to mixed state
    for _ in range(60):
        if not sim.step():
            break
    
    states = sim.get_all_station_states()
    non_acking = {
        sid for sid, state in states.items()
        if state['acked_version'] < version
    }
    
    acking = {
        sid for sid, state in states.items()
        if state['acked_version'] >= version
    }
    if not non_acking or not acking:
        pytest.skip("All stations in same ack state")
    
    # Before resend, record sends count
    sends_before = sim.get_transmission_cost()
    
    # Trigger resend
    app.resend_to_stale_stations()
    
    # Verify: exactly len(non_acking) new sends queued
    in_flight_sends = sim.get_in_flight_sends()
    new_sends_count = len(in_flight_sends)
    
    assert new_sends_count == len(non_acking), \
        f"Expected {len(non_acking)} resends, got {new_sends_count}"
    
    # Verify all are for the latest version
    for _, _, version_in_send in in_flight_sends:
        assert version_in_send == version


def test_resend_nothing_when_all_acked():
    """When all stations have acked, resend should queue no new sends."""
    sim = Simulation(seed=300)
    transport = sim.get_transport()
    
    app.set_transport(transport)
    sim.set_app(app)
    
    # Publish and let everything fully deliver
    version = app.publish_price(100.0)
    sim.step_until_idle()
    
    # Verify all stations have acked the version
    states = sim.get_all_station_states()
    for station_id, state in states.items():
        assert state['acked_version'] >= version, \
            f"Station {station_id} acked version {state['acked_version']}, expected >= {version}"
    
    # Trigger resend
    app.resend_to_stale_stations()
    
    # Should queue no sends since all have acked
    in_flight_sends = sim.get_in_flight_sends()
    assert len(in_flight_sends) == 0, \
        f"Should send nothing when all acked, but queued {len(in_flight_sends)} sends"


def test_resend_sends_latest_version_only():
    """Resend should send only the latest published version."""
    sim = Simulation(seed=400)
    transport = sim.get_transport()
    
    app.set_transport(transport)
    sim.set_app(app)
    
    # Publish first version
    v1 = app.publish_price(100.0)
    for _ in range(30):
        if not sim.step():
            break
    
    # Publish second version
    v2 = app.publish_price(101.0)
    for _ in range(30):
        if not sim.step():
            break
    
    states = sim.get_all_station_states()
    
    # Skip if no mixed state
    non_acking_v2 = {
        sid for sid, state in states.items()
        if state['acked_version'] < v2
    }
    if not non_acking_v2:
        pytest.skip("No non-acking stations for v2")
    
    # Trigger resend
    app.resend_to_stale_stations()
    
    # All resends should be for v2, not v1
    in_flight_sends = sim.get_in_flight_sends()
    for station_id, price, version in in_flight_sends:
        assert version == v2, \
            f"Resend to {station_id} has version {version}, expected {v2}"


def test_resend_does_not_send_to_acked_stations():
    """Resend should not send to stations that have already acked the latest version."""
    sim = Simulation(seed=500)
    transport = sim.get_transport()
    
    app.set_transport(transport)
    sim.set_app(app)
    
    version = app.publish_price(100.0)
    
    # Simulate to mixed state
    for _ in range(40):
        if not sim.step():
            break
    
    states = sim.get_all_station_states()
    acking_stations = {
        sid for sid, state in states.items()
        if state['acked_version'] >= version
    }
    
    if not acking_stations:
        pytest.skip("No acked stations in this seed")
    
    # Trigger resend
    app.resend_to_stale_stations()
    
    # Verify resend does not target acked stations
    in_flight_sends = sim.get_in_flight_sends()
    resend_targets = {sid for sid, _, _ in in_flight_sends}
    
    overlap = resend_targets & acking_stations
    assert len(overlap) == 0, \
        f"Resend incorrectly targeted already-acked stations: {overlap}"
