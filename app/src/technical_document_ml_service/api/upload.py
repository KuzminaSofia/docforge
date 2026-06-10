from __future__ import annotations

from fastapi import UploadFile

from technical_document_ml_service.services.document_storage_service import IncomingDocumentData


def collect_uploaded_documents(uploads: list[UploadFile]) -> list[IncomingDocumentData]:
    """адаптировать FastAPI UploadFile в доменно-нейтральные IncomingDocumentData

    Файлы не буферизуются: поток `UploadFile.file` передаётся дальше как есть и
    стримится напрямую в object storage. Проверка лимитов размера выполняется на
    лету при чтении потока (см. document_storage_service._LimitingReader).
    """
    return [
        IncomingDocumentData(
            filename=upload.filename or "document",
            content_type=upload.content_type,
            stream=upload.file,
        )
        for upload in uploads
    ]
