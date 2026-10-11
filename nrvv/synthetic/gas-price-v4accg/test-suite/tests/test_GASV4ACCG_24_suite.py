import pytest
import app
from nrvv_env import Simulation


def test_resend_latest_only_single_station():
    """GASV4ACCG-24: Resend sends only latest version to stale station."""
    sim = Simulation(seed=1001)
    sim.set_app(app)
    
    # Send 3 versions to station
    app.SendPrice("S1", 100.0, 1)
    app.SendPrice("S1", 110.0, 2)
    app.SendPrice("S1", 120.0, 3)
    
    before_cost = sim.get_transmission_cost()
    assert before_cost == 3
    
    # Deliver messages and acks until station acks version 1 only
    for _ in range(50):
        if not sim.step():
            break
        state = sim.get_station_state("S1")
        if state and state['acked_version'] >= 1:
            break
    
    state = sim.get_station_state("S1")
    acked = state['acked_version'] if state else 0
    
    # Verify station is stale (acked < 3)
    if acked < 3:
        before_resend = sim.get_transmission_cost()
        app.ResendToStaleStations()
        after_resend = sim.get_transmission_cost()
        
        # Only 1 resend should have been queued (version 3 to S1)
        assert after_resend - before_resend == 1, \
            f"Expected 1 resend, got {after_resend - before_resend}"


def test_resend_multiple_stale_stations():
    """Resend sends latest version to all stale stations, one send per station."""
    sim = Simulation(seed=1002)
    sim.set_app(app)
    
    # Send versions to two stations
    for sid in ["S1", "S2"]:
        app.SendPrice(sid, 100.0, 1)
        app.SendPrice(sid, 110.0, 2)
        app.SendPrice(sid, 120.0, 3)
    
    before_cost = sim.get_transmission_cost()
    assert before_cost == 6
    
    # Step until both stations have acknowledged something
    for _ in range(100):
        if not sim.step():
            break
        s1 = sim.get_station_state("S1") or {}
        s2 = sim.get_station_state("S2") or {}
        if s1.get('acked_version', 0) >= 1 and s2.get('acked_version', 0) >= 1:
            break
    
    # Count stale stations
    s1_state = sim.get_station_state("S1") or {}
    s2_state = sim.get_station_state("S2") or {}
    s1_stale = s1_state.get('acked_version', 0) < 3
    s2_stale = s2_state.get('acked_version', 0) < 3
    stale_count = (1 if s1_stale else 0) + (1 if s2_stale else 0)
    
    # Resend
    before_resend = sim.get_transmission_cost()
    app.ResendToStaleStations()
    after_resend = sim.get_transmission_cost()
    
    # Should have resent to each stale station exactly once
    assert after_resend - before_resend == stale_count


def test_resend_uptodate_station_unchanged():
    """Resend does not resend to stations that are up-to-date."""
    sim = Simulation(seed=1003)
    sim.set_app(app)
    
    # Send one version to station
    app.SendPrice("S1", 100.0, 1)
    
    initial_cost = sim.get_transmission_cost()
    
    # Step until fully delivered and acked
    for _ in range(50):
        if not sim.step():
            break
        state = sim.get_station_state("S1") or {}
        if state.get('acked_version', 0) >= 1 and state.get('displayed_version', 0) >= 1:
            break
    
    state = sim.get_station_state("S1") or {}
    # If station is up-to-date, resend should not increase cost
    if state.get('acked_version', 0) >= 1:
        before_resend = sim.get_transmission_cost()
        app.ResendToStaleStations()
        after_resend = sim.get_transmission_cost()
        
        # Should not increase (no stale stations)
        assert after_resend == before_resend


def test_resend_no_intermediate_versions():
    """Resend sends only latest version, never intermediate versions."""
    sim = Simulation(seed=1004)
    sim.set_app(app)
    
    # Send 4 versions
    app.SendPrice("S1", 100.0, 1)
    app.SendPrice("S1", 110.0, 2)
    app.SendPrice("S1", 120.0, 3)
    app.SendPrice("S1", 130.0, 4)
    
    initial = sim.get_transmission_cost()
    
    # Step until station acks v1
    for _ in range(100):
        if not sim.step():
            break
        state = sim.get_station_state("S1") or {}
        if state.get('acked_version', 0) >= 1:
            break
    
    state = sim.get_station_state("S1") or {}
    acked = state.get('acked_version', 0)
    
    # If station acked v1 but not v4, it's stale
    if acked == 1:
        before = sim.get_transmission_cost()
        app.ResendToStaleStations()
        after = sim.get_transmission_cost()
        
        # Only v4 should be resent (not v2 or v3)
        # Each resend is one transmission
        resend_count = after - before
        assert resend_count == 1, \
            f"Expected 1 resend (version 4), got {resend_count}"


def test_resend_to_never_acked_station():
    """Resend sends latest to station that never acknowledged anything."""
    sim = Simulation(seed=1005)
    sim.set_app(app)
    
    # Send versions but don't deliver acks
    app.SendPrice("S1", 100.0, 1)
    app.SendPrice("S1", 110.0, 2)
    app.SendPrice("S1", 120.0, 3)
    
    initial_cost = sim.get_transmission_cost()
    
    # Do a few steps but stay minimal to avoid full delivery
    step_count = 0
    for _ in range(10):
        if sim.step():
            step_count += 1
        else:
            break
    
    state = sim.get_station_state("S1") or {}
    # If station hasn't acked anything (acked_version = 0), it's stale
    if state.get('acked_version', 0) == 0:
        before_resend = sim.get_transmission_cost()
        app.ResendToStaleStations()
        after_resend = sim.get_transmission_cost()
        
        # Should resend version 3 (latest)
        assert after_resend - before_resend >= 1


def test_resend_multiple_calls_send_current_latest():
    """Subsequent ResendToStaleStations calls resend the updated latest version."""
    sim = Simulation(seed=1006)
    sim.set_app(app)
    
    # Send initial versions
    app.SendPrice("S1", 100.0, 1)
    app.SendPrice("S1", 110.0, 2)
    
    # Step until stale
    for _ in range(50):
        if not sim.step():
            break
        state = sim.get_station_state("S1") or {}
        if state.get('acked_version', 0) >= 1:
            break
    
    state1 = sim.get_station_state("S1") or {}
    if state1.get('acked_version', 0) < 2:
        # First resend
        before_resend1 = sim.get_transmission_cost()
        app.ResendToStaleStations()
        after_resend1 = sim.get_transmission_cost()
        
        resend1_cost = after_resend1 - before_resend1
        assert resend1_cost == 1
        
        # Send a new version
        app.SendPrice("S1", 120.0, 3)
        
        # Resend again
        before_resend2 = sim.get_transmission_cost()
        app.ResendToStaleStations()
        after_resend2 = sim.get_transmission_cost()
        
        # Should resend version 3 (the new latest)
        assert after_resend2 - before_resend2 == 1


def test_resend_cost_exactly_one_per_stale_station():
    """Resend incurs exactly one transmission cost per stale station."""
    sim = Simulation(seed=1007)
    sim.set_app(app)
    
    # Send to 3 stations
    for sid in ["S1", "S2", "S3"]:
        app.SendPrice(sid, 100.0, 1)
        app.SendPrice(sid, 110.0, 2)
    
    initial_cost = sim.get_transmission_cost()
    assert initial_cost == 6
    
    # Step until some acknowledgments
    for _ in range(100):
        if not sim.step():
            break
        states = sim.get_all_station_states()
        if all(s.get('acked_version', 0) >= 1 for s in states.values()):
            break
    
    # Count how many are stale
    states = sim.get_all_station_states()
    stale_stations = [sid for sid, s in states.items() if s.get('acked_version', 0) < 2]
    
    # Resend
    before_resend = sim.get_transmission_cost()
    app.ResendToStaleStations()
    after_resend = sim.get_transmission_cost()
    
    # Cost increase should match number of stale stations
    cost_increase = after_resend - before_resend
    assert cost_increase == len(stale_stations), \
        f"Expected {len(stale_stations)} resends, got {cost_increase}"
