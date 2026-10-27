from app.services import demo_data


def test_demo_monitor_measurements_are_explicitly_labeled():
    sample = demo_data.demo_monitor_measurement()

    assert sample["simulated"] is True
    assert 18 <= sample["latency_ms"] <= 45
    assert sample["internet_up"] is True
