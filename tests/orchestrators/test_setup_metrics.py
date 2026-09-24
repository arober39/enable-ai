"""The metrics provisioner must hit the real LaunchDarkly REST paths.

``POST /api/v2/projects/{proj}/metrics`` 404s. The documented collection
path is ``/api/v2/metrics/{project}`` (project key after ``/metrics``).
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType


def _load_setup_metrics() -> ModuleType:
    path = Path(__file__).resolve().parents[2] / "scripts" / "setup_metrics.py"
    spec = importlib.util.spec_from_file_location("setup_metrics", path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


setup_metrics = _load_setup_metrics()
MetricSpec = setup_metrics.MetricSpec
_create_metric = setup_metrics._create_metric
_metric_exists = setup_metrics._metric_exists


class _Resp:
    def __init__(self, status_code: int, text: str = "") -> None:
        self.status_code = status_code
        self.text = text


class _CapturingClient:
    def __init__(self) -> None:
        self.urls: list[tuple[str, str]] = []

    def get(self, url: str, headers: dict[str, str] | None = None) -> _Resp:
        self.urls.append(("GET", url))
        return _Resp(404)

    def post(
        self,
        url: str,
        headers: dict[str, str] | None = None,
        json: dict[str, object] | None = None,
    ) -> _Resp:
        self.urls.append(("POST", url))
        return _Resp(201)


def test_metric_exists_gets_metrics_project_key() -> None:
    client = _CapturingClient()
    exists = _metric_exists(client, "enable-ai", "support.errors.count", "fake-key")
    assert exists is False
    assert client.urls == [
        ("GET", "https://app.launchdarkly.com/api/v2/metrics/enable-ai/support.errors.count")
    ]


def test_create_metric_posts_to_metrics_project() -> None:
    client = _CapturingClient()
    spec = MetricSpec(
        key="support.errors.count",
        name="Support: error count",
        description="test",
        event_key="support.error",
    )
    _create_metric(client, "enable-ai", spec, "fake-key")
    assert client.urls == [("POST", "https://app.launchdarkly.com/api/v2/metrics/enable-ai")]
