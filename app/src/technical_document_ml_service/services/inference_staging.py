"""Staging-слой между object storage и ML-бэкендом

ML-бэкенды (`PredictionBackend`) работают исключительно с локальной файловой системой:
читают входные файлы по пути и пишут артефакты в каталог. Чтобы бэкенды оставались
S3-агностичными и тестируемыми без хранилища, вся работа с object storage вынесена сюда:

1. входные документы скачиваются из S3 во временный каталог (`materialize`);
2. бэкенд запускается на локальных путях (без изменений);
3. артефакты загружаются обратно в S3, а пути в результате переписываются в S3-ключи

временный каталог живет только на время обработки и удаляется по завершении
"""

from __future__ import annotations

import logging
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path, PurePosixPath
from tempfile import TemporaryDirectory
from typing import Iterator

from technical_document_ml_service.inference.backends.base import PredictionBackend
from technical_document_ml_service.inference.contracts import BackendRequest, BackendResult
from technical_document_ml_service.storage import ObjectStorage, get_object_storage

LOGGER = logging.getLogger("technical_document_ml_service.inference_staging")


def run_backend_with_staging(
    backend: PredictionBackend,
    request: BackendRequest,
) -> BackendResult:
    """выполнить бэкенд, обеспечив доставку входов из S3 и выгрузку артефактов в S3

    `request.artifacts_dir` приходит как S3-префикс (`artifacts/<task_id>`);
    `document.storage_path` приходит как S3-ключ входного файла.
    """
    storage = get_object_storage()
    s3_artifacts_prefix = request.artifacts_dir

    with _staging_workspace() as workspace:
        local_request = _materialize_inputs(request, storage, workspace)
        local_result = backend.process(local_request)
        return _persist_artifacts(
            local_result,
            storage,
            local_artifacts_dir=workspace.artifacts_dir,
            s3_artifacts_prefix=s3_artifacts_prefix,
        )


class _StagingWorkspace:
    """временные каталоги для одной обработки"""

    def __init__(self, root: Path) -> None:
        self.inputs_dir = root / "inputs"
        self.artifacts_dir = root / "artifacts"


@contextmanager
def _staging_workspace() -> Iterator[_StagingWorkspace]:
    """выделить временный workspace и гарантированно удалить его по завершении"""
    with TemporaryDirectory(prefix="tdms-staging-") as root:
        yield _StagingWorkspace(Path(root))


def _materialize_inputs(
    request: BackendRequest,
    storage: ObjectStorage,
    workspace: _StagingWorkspace,
) -> BackendRequest:
    """скачать входные документы из S3 и вернуть request с локальными путями"""
    workspace.inputs_dir.mkdir(parents=True, exist_ok=True)

    localized_documents = []
    for document in request.documents:
        suffix = PurePosixPath(document.storage_path).suffix
        local_path = workspace.inputs_dir / f"{document.document_id}{suffix}"
        storage.download_file(document.storage_path, local_path)
        localized_documents.append(replace(document, storage_path=str(local_path)))

    return replace(
        request,
        documents=localized_documents,
        artifacts_dir=str(workspace.artifacts_dir),
    )


def _persist_artifacts(
    result: BackendResult,
    storage: ObjectStorage,
    *,
    local_artifacts_dir: Path,
    s3_artifacts_prefix: str,
) -> BackendResult:
    """загрузить артефакты в S3 и переписать локальные пути в S3-ключи"""
    root = local_artifacts_dir.resolve()

    def to_key(local_path: str) -> str:
        relative = Path(local_path).resolve().relative_to(root)
        return f"{s3_artifacts_prefix}/{relative.as_posix()}"

    uploaded_artifacts = []
    for artifact in result.artifacts:
        key = to_key(artifact.path)
        storage.upload_file(Path(artifact.path), key, content_type=artifact.mime_type)
        uploaded_artifacts.append(replace(artifact, path=key))

    # output_path указывает на task summary, который уже выгружен как артефакт 
    # только переписываем его в ключ, повторно не загружаем
    output_key = to_key(result.output_path) if result.output_path else None

    return replace(result, artifacts=uploaded_artifacts, output_path=output_key)
