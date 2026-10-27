import requests

from app.schemas.network import SpeedTestRequest
from app.services import speedtest


def test_speed_test_rejects_invalid_transfer_sizes():
    assert SpeedTestRequest().download_bytes == 10_000_000
    try:
        SpeedTestRequest(download_bytes=10**9)
    except ValueError:
        pass
    else:
        raise AssertionError("Oversized speed test request should be rejected.")


def test_download_counts_received_bytes_and_closes_response(monkeypatch):
    class Response:
        closed = False

        def raise_for_status(self):
            pass

        def iter_content(self, chunk_size):
            assert chunk_size == 65536
            yield b"a" * 100
            yield b"b" * 50

        def close(self):
            self.closed = True

    response = Response()
    monkeypatch.setattr(speedtest.requests, "get", lambda *args, **kwargs: response)

    result = speedtest.measure_download(150)

    assert result["success"] is True
    assert result["bytes"] == 150
    assert response.closed is True


def test_http_error_is_not_reported_as_successful_download(monkeypatch):
    class Response:
        def raise_for_status(self):
            raise requests.HTTPError("server error")

        def close(self):
            pass

    monkeypatch.setattr(speedtest.requests, "get", lambda *args, **kwargs: Response())

    result = speedtest.measure_download(100_000)

    assert result["success"] is False
    assert result["mbps"] is None
