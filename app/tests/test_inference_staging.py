from __future__ import annotations

import io
from pathlib import Path
from uuid import uuid4

from technical_document_ml_service.inference.backends.base import PredictionBackend
from technical_document_ml_service.inference.contracts import (
    BackendArtifact,
    BackendDocument,
    BackendRequest,
    BackendResult,
)
from technical_document_ml_service.services.inference_staging import run_backend_with_staging
from technical_document_ml_service.storage import get_object_storage


class _EchoBackend(PredictionBackend):
    """тестовый backend: проверяет, что вход материализован локально, и пишет один артефакт"""

    backend_name = "echo-test"

    def process(self, request: BackendRequest) -> BackendResult:
        document = request.documents[0]
        local_input = Path(document.storage_path)
        # вход должен быть скачан на локальную ФС перед запуском backend
        assert local_input.is_file()
        body = local_input.read_bytes()

        artifacts_dir = Path(request.artifacts_dir)
        artifacts_dir.mkdir(parents=True, exist_ok=True)
        artifact_path = artifacts_dir / "echo.txt"
        artifact_path.write_bytes(b"echo:" + body)

        artifact = BackendArtifact(
            name="echo.txt",
            path=str(artifact_path),
            kind="plain_text",
            mime_type="text/plain",
        )
        return BackendResult(
            extracted_data={"ok": True},
            output_path=str(artifact_path),
            artifacts=[artifact],
        )


def _build_request(task_id, *, input_key: str) -> BackendRequest:
    return BackendRequest(
        task_id=task_id,
        user_id=uuid4(),
        model_id=uuid4(),
        model_name="m",
        model_kind="technical_document_extraction",
        backend_name="echo-test",
        backend_config={},
        target_schema="schema",
        documents=[
            BackendDocument(
                document_id=uuid4(),
                owner_id=uuid4(),
                original_filename="in.pdf",
                storage_path=input_key,
                mime_type="application/pdf",
                document_type="unknown",
                size_bytes=5,
            )
        ],
        artifacts_dir=f"artifacts/{task_id}",
    )


def test_staging_materializes_input_and_uploads_artifacts_as_keys() -> None:
    storage = get_object_storage()
    task_id = uuid4()
    input_key = f"uploads/{task_id}/in.pdf"
    storage.upload_fileobj(io.BytesIO(b"BODY!"), input_key)

    request = _build_request(task_id, input_key=input_key)
    result = run_backend_with_staging(_EchoBackend(), request)

    expected_key = f"artifacts/{task_id}/echo.txt"
    # пути в результате переписаны в S3-ключи
    assert result.artifacts[0].path == expected_key
    assert result.output_path == expected_key
    # содержимое артефакта реально загружено в object storage
    assert storage.get_bytes(expected_key) == b"echo:BODY!"


def test_staging_cleans_up_temporary_workspace() -> None:
    storage = get_object_storage()
    task_id = uuid4()
    input_key = f"uploads/{task_id}/in.pdf"
    storage.upload_fileobj(io.BytesIO(b"BODY!"), input_key)

    captured: dict[str, str] = {}

    class _CapturingBackend(_EchoBackend):
        def process(self, request: BackendRequest) -> BackendResult:
            captured["artifacts_dir"] = request.artifacts_dir
            return super().process(request)

    run_backend_with_staging(_CapturingBackend(), _build_request(task_id, input_key=input_key))

    # временный workspace удалён после обработки
    assert not Path(captured["artifacts_dir"]).exists()
