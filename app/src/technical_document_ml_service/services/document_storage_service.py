from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import IO, Iterable
from uuid import UUID, uuid4

from technical_document_ml_service.core.config import app_settings
from technical_document_ml_service.domain.exceptions import FileSizeLimitError
from technical_document_ml_service.storage import get_object_storage


@dataclass(frozen=True, slots=True)
class IncomingDocumentData:
    """входные данные загружаемого документа — открытый поток на чтение"""

    filename: str
    content_type: str | None
    stream: IO[bytes]


@dataclass(frozen=True, slots=True)
class StoredDocumentData:
    """метаданные документа после сохранения в object storage"""

    original_filename: str
    storage_path: str
    mime_type: str
    size_bytes: int


def _normalize_filename(filename: str | None) -> str:
    """нормализовать имя файла"""
    if not filename:
        return "document"
    return PurePosixPath(filename).name or "document"


@dataclass
class _TotalCounter:
    """кумулятивный счетчик байтов по всем документам задачи"""

    total: int = 0


class _LimitingReader:
    """обертка над потоком: считает байты и enforce'ит лимиты на лету при чтении"""

    def __init__(
        self,
        source: IO[bytes],
        *,
        filename: str,
        max_file_bytes: int,
        counter: _TotalCounter,
        max_total_bytes: int,
    ) -> None:
        self._source = source
        self._filename = filename
        self._max_file_bytes = max_file_bytes
        self._counter = counter
        self._max_total_bytes = max_total_bytes
        self.bytes_read = 0

    def read(self, size: int = -1) -> bytes:
        chunk = self._source.read(size)
        if not chunk:
            return chunk

        self.bytes_read += len(chunk)
        if self.bytes_read > self._max_file_bytes:
            raise FileSizeLimitError(
                f"Файл '{self._filename}' превышает допустимый размер "
                f"{app_settings.max_upload_file_size_mb} МБ."
            )

        self._counter.total += len(chunk)
        if self._counter.total > self._max_total_bytes:
            raise FileSizeLimitError(
                f"Суммарный размер файлов задачи превышает "
                f"{app_settings.max_task_total_size_mb} МБ."
            )

        return chunk


def save_documents(
    *,
    owner_id: UUID,
    documents: list[IncomingDocumentData],
) -> list[StoredDocumentData]:
    """потоково загрузить документы в object storage; вернуть метаданные с S3-ключами"""
    storage = get_object_storage()
    max_file_bytes = app_settings.max_upload_file_size_mb * 1024 * 1024
    max_total_bytes = app_settings.max_task_total_size_mb * 1024 * 1024
    counter = _TotalCounter()

    stored_documents: list[StoredDocumentData] = []
    uploaded_keys: list[str] = []

    try:
        for document in documents:
            original_filename = _normalize_filename(document.filename)
            suffix = PurePosixPath(original_filename).suffix
            key = f"{app_settings.uploads_dir}/{owner_id}/{uuid4().hex}{suffix}"

            reader = _LimitingReader(
                document.stream,
                filename=original_filename,
                max_file_bytes=max_file_bytes,
                counter=counter,
                max_total_bytes=max_total_bytes,
            )

            uploaded_keys.append(key)
            storage.upload_fileobj(
                reader,
                key,
                content_type=document.content_type or "application/octet-stream",
            )

            stored_documents.append(
                StoredDocumentData(
                    original_filename=original_filename,
                    storage_path=key,
                    mime_type=document.content_type or "application/octet-stream",
                    size_bytes=reader.bytes_read,
                )
            )
    except Exception:
        storage.delete(uploaded_keys)
        raise

    return stored_documents


def delete_stored_files(paths: Iterable[str]) -> None:
    """удалить ранее сохраненные объекты по ключам"""
    get_object_storage().delete(paths)
