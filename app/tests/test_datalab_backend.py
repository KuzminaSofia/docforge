from __future__ import annotations

import base64
import json
from pathlib import Path
from uuid import uuid4

import pytest

from technical_document_ml_service.inference.backends import datalab_backend
from technical_document_ml_service.inference.backends._secrets import resolve_api_key
from technical_document_ml_service.inference.backends.datalab_backend import (
    DatalabBackend,
)
from technical_document_ml_service.inference.contracts import (
    BackendDocument,
    BackendRequest,
)
from technical_document_ml_service.inference.exceptions import (
    BackendExecutionError,
    InvalidBackendConfigurationError,
)


# ── helpers ──────────────────────────────────────────────────────────────────


def _build_request(tmp_path, *, backend_config: dict) -> BackendRequest:
    """собрать BackendRequest с одним реальным файлом во временном каталоге"""
    pdf_path = tmp_path / "sample.pdf"
    pdf_path.write_bytes(b"%PDF-1.4 test content")

    return BackendRequest(
        task_id=uuid4(),
        user_id=uuid4(),
        model_id=uuid4(),
        model_name="technical-document-extractor-datalab",
        model_kind="technical_document_extraction",
        backend_name="datalab",
        backend_config=backend_config,
        target_schema="passport_fields",
        documents=[
            BackendDocument(
                document_id=uuid4(),
                owner_id=uuid4(),
                original_filename="sample.pdf",
                storage_path=str(pdf_path),
                mime_type="application/pdf",
                document_type="unknown",
                size_bytes=pdf_path.stat().st_size,
            )
        ],
        artifacts_dir=str(tmp_path / "artifacts"),
        context={},
    )


class _FakeResponse:
    """минимальная замена requests.Response"""

    def __init__(self, payload: dict, *, status_code: int = 200, text: str = "") -> None:
        self._payload = payload
        self.status_code = status_code
        self.text = text

    def json(self) -> dict:
        return self._payload


class _FakeRequests:
    """фейковый requests: один ответ на submit (POST) и очередь на poll (GET)"""

    def __init__(
        self,
        *,
        submit_payload: dict,
        poll_payloads: list[dict] | None = None,
        submit_status: int = 200,
    ) -> None:
        self._submit_payload = submit_payload
        self._submit_status = submit_status
        self._poll_payloads = list(poll_payloads or [])
        self.post_calls: list[dict] = []
        self.get_calls: list[str] = []

    def post(self, url, *, headers=None, data=None, files=None, timeout=None):
        self.post_calls.append(
            {"url": url, "headers": headers, "data": data, "files": files}
        )
        return _FakeResponse(self._submit_payload, status_code=self._submit_status)

    def get(self, url, *, headers=None, timeout=None):
        self.get_calls.append(url)
        payload = self._poll_payloads.pop(0)
        return _FakeResponse(payload)


# ── resolve_api_key (generic secret resolution) ──────────────────────────────


def test_resolve_api_key_direct_value_wins(monkeypatch) -> None:
    monkeypatch.setenv("APP_DATALAB_API_KEY", "env-key")
    assert resolve_api_key({"api_key": "direct"}, default_env="APP_DATALAB_API_KEY") == "direct"


def test_resolve_api_key_via_named_env(monkeypatch) -> None:
    monkeypatch.setenv("CUSTOM_KEY_ENV", "from-named-env")
    resolved = resolve_api_key(
        {"api_key_env": "CUSTOM_KEY_ENV"}, default_env="APP_DATALAB_API_KEY"
    )
    assert resolved == "from-named-env"


def test_resolve_api_key_via_default_env(monkeypatch) -> None:
    monkeypatch.setenv("APP_DATALAB_API_KEY", "default-env-key")
    assert resolve_api_key({}, default_env="APP_DATALAB_API_KEY") == "default-env-key"


def test_resolve_api_key_returns_none_when_unset(monkeypatch) -> None:
    monkeypatch.delenv("APP_DATALAB_API_KEY", raising=False)
    assert resolve_api_key({}, default_env="APP_DATALAB_API_KEY") is None


# ── stub fallback / missing key ──────────────────────────────────────────────


def test_datalab_stub_fallback_when_no_api_key(monkeypatch, tmp_path) -> None:
    monkeypatch.delenv("APP_DATALAB_API_KEY", raising=False)
    backend = DatalabBackend(config={"allow_stub_fallback": True})
    request = _build_request(tmp_path, backend_config={"allow_stub_fallback": True})

    result = backend.process(request)

    assert result.output_path is not None
    # markdown + datalab_json + document_summary + task_summary
    assert len(result.artifacts) == 4
    assert "sample.pdf" in result.extracted_data
    entry = result.extracted_data["sample.pdf"]
    assert entry["backend"] == "datalab"
    assert entry["status"] == "processed"
    assert entry["mode"] == "stub_fallback"
    assert len(result.warnings) == 1


def test_datalab_raises_without_key_when_stub_disabled(monkeypatch, tmp_path) -> None:
    monkeypatch.delenv("APP_DATALAB_API_KEY", raising=False)
    backend = DatalabBackend(config={})
    request = _build_request(tmp_path, backend_config={})

    with pytest.raises(BackendExecutionError):
        backend.process(request)


# ── config validation ────────────────────────────────────────────────────────


def test_datalab_invalid_mode_raises() -> None:
    backend = DatalabBackend(config={"mode": "turbo"})
    with pytest.raises(InvalidBackendConfigurationError):
        backend._resolve_mode()


def test_datalab_invalid_int_option_raises() -> None:
    backend = DatalabBackend(config={"poll_timeout_s": "not-a-number"})
    with pytest.raises(InvalidBackendConfigurationError):
        backend._build_client("api-key")


# ── full convert path (submit + poll, mocked requests) ───────────────────────


def test_datalab_converts_via_api(monkeypatch, tmp_path) -> None:
    image_bytes = b"\x89PNG fake image bytes"
    image_b64 = base64.b64encode(image_bytes).decode()
    markdown = "# Spec\n\nDiagram: ![](_page_0_Figure_1.jpeg)\n"

    fake = _FakeRequests(
        submit_payload={"success": True, "request_check_url": "https://check.url"},
        poll_payloads=[
            {"status": "processing"},
            {
                "status": "complete",
                "success": True,
                "markdown": markdown,
                "images": {"_page_0_Figure_1.jpeg": image_b64},
                "page_count": 3,
            },
        ],
    )
    monkeypatch.setattr(datalab_backend, "_load_requests", lambda: fake)

    backend = DatalabBackend(
        # api_key прямо в config + poll_interval_s=0 чтобы цикл опроса не спал
        config={"api_key": "test-key", "poll_interval_s": 0}
    )
    request = _build_request(
        tmp_path, backend_config={"api_key": "test-key", "poll_interval_s": 0}
    )

    result = backend.process(request)

    # вызвали submit один раз и опросили дважды (processing -> complete)
    assert len(fake.post_calls) == 1
    assert len(fake.get_calls) == 2
    assert fake.post_calls[0]["headers"] == {"X-API-Key": "test-key"}

    # файл уходит с явным Content-Type (иначе Datalab отвечает 400 Invalid file type)
    file_tuple = fake.post_calls[0]["files"]["file"]
    assert len(file_tuple) == 3
    assert file_tuple[2] == "application/pdf"

    by_kind = {a.kind: a for a in result.artifacts}
    assert set(by_kind) == {"markdown", "datalab_json", "image", "document_summary", "task_summary"}

    # markdown сохранен дословно
    md_artifact = by_kind["markdown"]
    assert Path(md_artifact.path).read_text(encoding="utf-8") == markdown

    # изображение декодировано на диск, source_name == исходная ссылка из markdown
    image_artifact = by_kind["image"]
    assert image_artifact.metadata["source_name"] == "_page_0_Figure_1.jpeg"
    assert Path(image_artifact.path).read_bytes() == image_bytes

    # datalab_json не содержит base64 изображений, но содержит их имена
    saved_json = json.loads(Path(by_kind["datalab_json"].path).read_text(encoding="utf-8"))
    assert "images" not in saved_json
    assert saved_json["image_names"] == ["_page_0_Figure_1.jpeg"]

    entry = result.extracted_data["sample.pdf"]
    assert entry["mode"] == "datalab"
    assert entry["page_count"] == 3
    assert entry["images_count"] == 1
    assert result.warnings == []


def test_datalab_surfaces_http_error_body(monkeypatch, tmp_path) -> None:
    # Datalab возвращает 400 с причиной в теле — она должна попасть в текст ошибки
    fake = _FakeRequests(
        submit_payload={"success": False, "error": "max_pages exceeds plan limit"},
        submit_status=400,
    )
    monkeypatch.setattr(datalab_backend, "_load_requests", lambda: fake)

    backend = DatalabBackend(config={"api_key": "test-key"})
    request = _build_request(tmp_path, backend_config={"api_key": "test-key"})

    with pytest.raises(BackendExecutionError) as exc_info:
        backend.process(request)

    message = str(exc_info.value)
    assert "400" in message
    assert "max_pages exceeds plan limit" in message


def test_datalab_propagates_api_failure(monkeypatch, tmp_path) -> None:
    fake = _FakeRequests(
        submit_payload={"success": True, "request_check_url": "https://check.url"},
        poll_payloads=[{"status": "complete", "success": False, "error": "bad doc"}],
    )
    monkeypatch.setattr(datalab_backend, "_load_requests", lambda: fake)

    backend = DatalabBackend(config={"api_key": "test-key"})
    request = _build_request(tmp_path, backend_config={"api_key": "test-key"})

    with pytest.raises(BackendExecutionError):
        backend.process(request)
