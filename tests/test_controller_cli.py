import asyncio

from controller.cli import doctor


def test_doctor_returns_nonzero_when_worker_health_fails(monkeypatch, capsys):
    class FailingClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def get(self, _url):
            raise OSError("offline")

    monkeypatch.setenv("WORKER_TOKEN", "configured-worker-token")
    monkeypatch.setattr("controller.cli.httpx.AsyncClient", lambda **_kwargs: FailingClient())
    assert asyncio.run(doctor()) == 2
    assert "not verified" in capsys.readouterr().out
