import pytest
import nrvv_env
import app


def test_publish_price_returns_integer_version():
    """PublishPrice should return a positive integer version number."""
    sim = nrvv_env.Simulation(seed=42)
    sim.set_app(app)
    
    version = app.PublishPrice(100.0)
    assert isinstance(version, int)
    assert version > 0


def test_versions_strictly_increase():
    """Each published price receives a strictly increasing version number."""
    sim = nrvv_env.Simulation(seed=42)
    sim.set_app(app)
    
    v1 = app.PublishPrice(100.0)
    v2 = app.PublishPrice(101.0)
    v3 = app.PublishPrice(102.0)
    v4 = app.PublishPrice(103.0)
    
    versions = [v1, v2, v3, v4]
    for i in range(1, len(versions)):
        assert versions[i] > versions[i-1], \
            f"Version {versions[i]} should be strictly greater than {versions[i-1]}"


def test_published_versions_unique():
    """All published versions must be unique integers."""
    sim = nrvv_env.Simulation(seed=42)
    sim.set_app(app)
    
    versions = [app.PublishPrice(float(i)) for i in range(10)]
    
    # All versions should be unique
    assert len(versions) == len(set(versions)), \
        f"Expected unique versions, got duplicates in {versions}"


def test_consecutive_versions_increment_by_one():
    """Consecutive publish calls should increment version by exactly one."""
    sim = nrvv_env.Simulation(seed=42)
    sim.set_app(app)
    
    v1 = app.PublishPrice(100.0)
    v2 = app.PublishPrice(101.0)
    v3 = app.PublishPrice(102.0)
    
    assert v2 == v1 + 1, f"v2={v2} should equal v1+1={v1 + 1}"
    assert v3 == v2 + 1, f"v3={v3} should equal v2+1={v2 + 1}"


def test_get_latest_version_returns_published_version():
    """get_latest_version should return the version of the most recent published price."""
    sim = nrvv_env.Simulation(seed=42)
    sim.set_app(app)
    
    v1 = app.PublishPrice(100.0)
    latest1 = app.get_latest_version()
    assert latest1 == v1, f"After first publish, latest={latest1} should equal v1={v1}"
    
    v2 = app.PublishPrice(101.0)
    latest2 = app.get_latest_version()
    assert latest2 == v2, f"After second publish, latest={latest2} should equal v2={v2}"
    
    v3 = app.PublishPrice(102.0)
    latest3 = app.get_latest_version()
    assert latest3 == v3, f"After third publish, latest={latest3} should equal v3={v3}"


def test_latest_version_is_maximum():
    """Querying for latest version returns the highest version number assigned."""
    sim = nrvv_env.Simulation(seed=42)
    sim.set_app(app)
    
    versions = []
    for i in range(5):
        v = app.PublishPrice(float(i * 10))
        versions.append(v)
    
    latest = app.get_latest_version()
    max_version = max(versions)
    
    assert latest == max_version, \
        f"Latest version {latest} should equal maximum {max_version} from {versions}"


def test_latest_version_never_decreases():
    """Latest version should never decrease when new prices are published."""
    sim = nrvv_env.Simulation(seed=42)
    sim.set_app(app)
    
    latest_versions = []
    for i in range(5):
        app.PublishPrice(float(i))
        latest = app.get_latest_version()
        latest_versions.append(latest)
    
    # Verify monotonically increasing
    for i in range(1, len(latest_versions)):
        assert latest_versions[i] >= latest_versions[i-1], \
            f"Latest version decreased: {latest_versions[i]} < {latest_versions[i-1]}"
        
        # Since we're publishing new prices, latest should actually increase
        assert latest_versions[i] > latest_versions[i-1], \
            f"Latest version should increase with each publish: {latest_versions}"


def test_versions_with_different_price_values():
    """Version assignment should be independent of price value differences."""
    sim = nrvv_env.Simulation(seed=42)
    sim.set_app(app)
    
    v1 = app.PublishPrice(50.0)
    v2 = app.PublishPrice(150.0)
    v3 = app.PublishPrice(75.0)
    
    # Versions should still be strictly increasing despite price changes
    assert v1 < v2 < v3, \
        f"Versions should strictly increase regardless of prices: {v1}, {v2}, {v3}"
