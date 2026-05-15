from __future__ import annotations

from fastapi import UploadFile

from technical_document_ml_service.core.config import app_settings
from technical_document_ml_service.domain.exceptions import FileSizeLimitError
from technical_document_ml_service.services.document_storage_service import IncomingDocumentData


_READ_CHUNK_BYTES = 64 * 1024  # 64 КБ — прекращаем чтение сразу при превышении лимита


def collect_uploaded_documents(uploads: list[UploadFile]) -> list[IncomingDocumentData]:
    """читать загруженные файлы чанками и проверить лимиты размера"""
    max_file_bytes = app_settings.max_upload_file_size_mb * 1024 * 1024
    max_total_bytes = app_settings.max_task_total_size_mb * 1024 * 1024

    incoming: list[IncomingDocumentData] = []
    total_bytes = 0

    try:
        for upload in uploads:
            chunks: list[bytes] = []
            file_bytes = 0

            while True:
                chunk = upload.file.read(_READ_CHUNK_BYTES)
                if not chunk:
                    break
                file_bytes += len(chunk)
                if file_bytes > max_file_bytes:
                    raise FileSizeLimitError(
                        f"Файл '{upload.filename}' превышает допустимый размер "
                        f"{app_settings.max_upload_file_size_mb} МБ."
                    )
                chunks.append(chunk)

            total_bytes += file_bytes
            if total_bytes > max_total_bytes:
                raise FileSizeLimitError(
                    f"Суммарный размер файлов задачи превышает "
                    f"{app_settings.max_task_total_size_mb} МБ."
                )

            incoming.append(
                IncomingDocumentData(
                    filename=upload.filename or "document",
                    content_type=upload.content_type,
                    content=b"".join(chunks),
                )
            )
    finally:
        for upload in uploads:
            upload.file.close()

    return incoming
