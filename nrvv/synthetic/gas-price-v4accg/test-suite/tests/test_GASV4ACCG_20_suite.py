import pytest
import app
import nrvv_env


def _init_sim(seed):
    """Initialize simulation with app."""
    sim = nrvv_env.Simulation(seed=seed)
    transport = sim.get_transport()
    
    if hasattr(app, 'initialize'):
        app.initialize(transport)
    elif hasattr(app, 'set_transport'):
        app.set_transport(transport)
    
    service = app if not hasattr(app, 'get_service') else app.get_service()
    sim.set_app(service)
    return sim


def test_stale_ack_triggers_resend_basic():
    """Stale ack causes latest version to be queued for resend."""
    sim = _init_sim(42)
    
    v1 = app.publish_price(10.0)
    app.send_price('S1', 10.0, v1)
    sim.step_until_idle()
    
    v2 = app.publish_price(20.0)
    app.receive_acknowledgment('S1', v1)
    
    pending = sim.get_in_flight_sends()
    assert any(sid == 'S1' and v == v2 for sid, _, v in pending)


def test_stale_ack_multiple_stations():
    """All stations with stale acks get latest resend."""
    sim = _init_sim(43)
    
    v1 = app.publish_price(10.0)
    for s in ['S1', 'S2', 'S3']:
        app.send_price(s, 10.0, v1)
    sim.step_until_idle()
    
    v2 = app.publish_price(20.0)
    for s in ['S1', 'S2', 'S3']:
        app.receive_acknowledgment(s, v1)
    
    pending = sim.get_in_flight_sends()
    for s in ['S1', 'S2', 'S3']:
        assert any(sid == s and v == v2 for sid, _, v in pending)


def test_stale_ack_far_behind():
    """Ack far behind latest version triggers resend of latest."""
    sim = _init_sim(44)
    
    v1 = app.publish_price(10.0)
    v2 = app.publish_price(20.0)
    v3 = app.publish_price(30.0)
    v4 = app.publish_price(40.0)
    
    app.send_price('S1', 10.0, v1)
    sim.step_until_idle()
    app.receive_acknowledgment('S1', v1)
    
    pending = sim.get_in_flight_sends()
    assert any(sid == 'S1' and v == v4 for sid, _, v in pending)


def test_stale_ack_out_of_order():
    """Out-of-order acks: newer ack followed by older ack."""
    sim = _init_sim(45)
    
    v1 = app.publish_price(10.0)
    v2 = app.publish_price(20.0)
    v3 = app.publish_price(30.0)
    
    app.send_price('S1', 10.0, v1)
    app.send_price('S1', 20.0, v2)
    app.send_price('S1', 30.0, v3)
    sim.step_until_idle()
    
    app.receive_acknowledgment('S1', v3)
    app.receive_acknowledgment('S1', v1)
    
    pending = sim.get_in_flight_sends()
    assert any(sid == 'S1' and v == v3 for sid, _, v in pending)


def test_stale_ack_never_sent_station():
    """Stale ack from station that never received still triggers send."""
    sim = _init_sim(46)
    
    v1 = app.publish_price(10.0)
    v2 = app.publish_price(20.0)
    
    app.receive_acknowledgment('S99', v1)
    
    pending = sim.get_in_flight_sends()
    assert any(sid == 'S99' and v == v2 for sid, _, v in pending)


def test_non_stale_ack_no_new_send():
    """Ack of current version should not trigger new send."""
    sim = _init_sim(47)
    
    v1 = app.publish_price(10.0)
    app.send_price('S1', 10.0, v1)
    sim.step_until_idle()
    
    before_sends = len(sim.get_in_flight_sends())
    
    app.receive_acknowledgment('S1', v1)
    
    after_sends = len(sim.get_in_flight_sends())
    assert after_sends == before_sends
