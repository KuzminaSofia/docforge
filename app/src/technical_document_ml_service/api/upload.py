from __future__ import annotations

import os
import tempfile
from pathlib import Path

from fastapi import UploadFile

from technical_document_ml_service.core.config import app_settings
from technical_document_ml_service.domain.exceptions import FileSizeLimitError
from technical_document_ml_service.services.document_storage_service import IncomingDocumentData


_READ_CHUNK_BYTES = 64 * 1024


def collect_uploaded_documents(uploads: list[UploadFile]) -> list[IncomingDocumentData]:
    """стримингово записать загружаемые файлы во временные файлы с проверкой лимитов"""
    max_file_bytes = app_settings.max_upload_file_size_mb * 1024 * 1024
    max_total_bytes = app_settings.max_task_total_size_mb * 1024 * 1024
    uploads_root = Path(app_settings.uploads_dir)
    uploads_root.mkdir(parents=True, exist_ok=True)

    incoming: list[IncomingDocumentData] = []
    total_bytes = 0

    try:
        for upload in uploads:
            size_bytes, tmp_path = _stream_to_temp(upload, max_file_bytes, uploads_root)
            total_bytes += size_bytes
            if total_bytes > max_total_bytes:
                tmp_path.unlink(missing_ok=True)
                raise FileSizeLimitError(
                    f"Суммарный размер файлов задачи превышает "
                    f"{app_settings.max_task_total_size_mb} МБ."
                )
            incoming.append(
                IncomingDocumentData(
                    filename=upload.filename or "document",
                    content_type=upload.content_type,
                    temp_path=tmp_path,
                    size_bytes=size_bytes,
                )
            )
    except Exception:
        for doc in incoming:
            doc.temp_path.unlink(missing_ok=True)
        raise
    finally:
        for upload in uploads:
            upload.file.close()

    return incoming


def _stream_to_temp(
    upload: UploadFile,
    max_file_bytes: int,
    tmp_dir: Path,
) -> tuple[int, Path]:
    """записать загрузку в temp-файл чанками; при превышении лимита — удалить и поднять ошибку"""
    fd, tmp_str = tempfile.mkstemp(dir=tmp_dir)
    tmp_path = Path(tmp_str)
    file_bytes = 0
    try:
        with os.fdopen(fd, "wb") as tmp_file:
            while chunk := upload.file.read(_READ_CHUNK_BYTES):
                file_bytes += len(chunk)
                if file_bytes > max_file_bytes:
                    raise FileSizeLimitError(
                        f"Файл '{upload.filename}' превышает допустимый размер "
                        f"{app_settings.max_upload_file_size_mb} МБ."
                    )
                tmp_file.write(chunk)
    except Exception:
        tmp_path.unlink(missing_ok=True)
        raise
    return file_bytes, tmp_path
