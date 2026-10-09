import app
from nrvv_env import Simulation

STATION = 'S1'
KEYWORD_NAMES = ('outbound', 'port', 'send_port', 'outbound_port', 'send')


def _service_class():
    found = [value for value in vars(app).values()
             if isinstance(value, type)
             and all(callable(getattr(value, name, None))
                     for name in ('set_desired_price', 'inspect_station', 'receive_acknowledgement'))]
    assert found, 'app must provide a service class with the three operations'
    return found[0]


def _build(seed, stations=(STATION,), **kwargs):
    sim = Simulation(seed, list(stations), **kwargs)
    cls = _service_class()
    try:
        service = cls(sim.send_price_update)
    except TypeError:
        service = None
        for name in KEYWORD_NAMES:
            try:
                service = cls(**{name: sim.send_price_update})
                break
            except TypeError:
                continue
    assert service is not None, 'service must accept the outbound port'
    return sim.connect(service)


def _sent_prices(sim, station=STATION):
    return [send.price for send in sim.sends if send.station == station]


def test_newest_price_only_after_in_flight_update():
    for seed in range(8):
        sim = _build(seed, changes=0)
        sim.issue_desired_price(STATION, '10.00')
        assert sim.outstanding(STATION) == 1
        sent_before = len(sim.sends)
        sim.issue_desired_price(STATION, '11.00')
        sim.issue_desired_price(STATION, '12.00')
        assert len(sim.sends) == sent_before
        sim.run()
        assert _sent_prices(sim) == ['10.00', '12.00'], seed
        assert sim.sends[-1].desired_at_send == '12.00'
        assert sim.displayed(STATION) == '12.00'


def test_intermediate_skipped_when_ack_still_in_transit():
    for seed in range(8):
        sim = _build(seed, changes=0)
        sim.issue_desired_price(STATION, '10.00')
        while sim.in_transit(STATION):
            sim.step()
        assert sim.displayed(STATION) == '10.00'
        assert sim.outstanding(STATION) == 1
        sim.issue_desired_price(STATION, '11.00')
        sim.issue_desired_price(STATION, '12.00')
        sim.run()
        assert _sent_prices(sim) == ['10.00', '12.00'], seed
        assert sim.displayed(STATION) == '12.00'


def test_sent_price_is_desired_price_at_send_time():
    for seed in range(12):
        sim = _build(seed, stations=('S1', 'S2', 'S3'), changes=30).run()
        for send in sim.sends:
            assert send.price == send.desired_at_send, seed
            assert send.outstanding_before == 0, seed


def test_station_converges_to_latest_desired_price():
    for seed in range(12):
        sim = _build(seed, stations=('S1', 'S2'), changes=30).run()
        for station in ('S1', 'S2'):
            assert sim.displayed(station) == sim.desired(station), seed
