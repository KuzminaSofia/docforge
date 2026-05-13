from __future__ import annotations

from fastapi import UploadFile

from technical_document_ml_service.core.config import app_settings
from technical_document_ml_service.domain.exceptions import FileSizeLimitError
from technical_document_ml_service.services.document_storage_service import IncomingDocumentData


def collect_uploaded_documents(uploads: list[UploadFile]) -> list[IncomingDocumentData]:
    """читать загруженные файлы и проверить лимиты размера"""
    max_file_bytes = app_settings.max_upload_file_size_mb * 1024 * 1024
    max_total_bytes = app_settings.max_task_total_size_mb * 1024 * 1024

    incoming: list[IncomingDocumentData] = []
    total_bytes = 0

    try:
        for upload in uploads:
            content = upload.file.read()
            file_size = len(content)

            if file_size > max_file_bytes:
                raise FileSizeLimitError(
                    f"Файл '{upload.filename}' превышает допустимый размер "
                    f"{app_settings.max_upload_file_size_mb} МБ "
                    f"(получено {file_size / 1024 / 1024:.1f} МБ)."
                )

            total_bytes += file_size
            if total_bytes > max_total_bytes:
                raise FileSizeLimitError(
                    f"Суммарный размер файлов задачи превышает "
                    f"{app_settings.max_task_total_size_mb} МБ."
                )

            incoming.append(
                IncomingDocumentData(
                    filename=upload.filename or "document",
                    content_type=upload.content_type,
                    content=content,
                )
            )
    finally:
        for upload in uploads:
            upload.file.close()

    return incoming
