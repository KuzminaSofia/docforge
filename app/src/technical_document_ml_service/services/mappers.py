from __future__ import annotations

from technical_document_ml_service.db.models import (
    MLModelORM,
    MLRequestHistoryORM,
    MLTaskORM,
    TransactionORM,
    UploadedDocumentORM,
    UserORM,
)
from technical_document_ml_service.domain.entities import (
    DocumentExtractionTask,
    MLRequestHistoryRecord,
    MLTask,
    TechnicalDocumentExtractionModel,
    UploadedDocument,
    User,
)
from technical_document_ml_service.domain.enums import (
    DocumentType,
    TaskStatus,
    TransactionType,
    UserRole,
)
from technical_document_ml_service.domain.exceptions import TaskExecutionError
from technical_document_ml_service.services.dto import (
    PredictionHistoryItem,
    TransactionHistoryItem,
)


def _parse_supported_document_types(values: list[str]) -> set[DocumentType]:
    """преобразовать список строковых типов документов в enum-значения"""
    parsed: set[DocumentType] = set()
    for value in values:
        try:
            parsed.add(DocumentType(value))
        except ValueError:
            continue
    return parsed or {DocumentType.UNKNOWN}


def model_orm_to_domain(model_orm: MLModelORM) -> TechnicalDocumentExtractionModel:
    """преобразовать ORM-модель в доменную ML-модель"""
    if model_orm.model_kind != "technical_document_extraction":
        raise TaskExecutionError("Неподдерживаемый тип ML-модели.")

    return TechnicalDocumentExtractionModel(
        name=model_orm.name,
        description=model_orm.description,
        prediction_cost=model_orm.prediction_cost,
        supported_document_types=_parse_supported_document_types(
            model_orm.supported_document_types
        ),
        is_active=model_orm.is_active,
        entity_id=model_orm.id,
    )


def orm_to_domain_user(user_orm: UserORM) -> User:
    """
    преобразовать ORM-пользователя в доменную сущность
    """
    return User(
        email=user_orm.email,
        password_hash=user_orm.password_hash,
        role=UserRole(user_orm.role),
        balance_credits=user_orm.balance_credits,
        is_active=user_orm.is_active,
        entity_id=user_orm.id,
        created_at=user_orm.created_at,
    )


def parse_document_type(raw_value: str) -> DocumentType:
    """безопасно преобразовать строковый тип документа в enum, при ошибке — UNKNOWN"""
    try:
        return DocumentType(raw_value)
    except ValueError:
        return DocumentType.UNKNOWN


def document_orm_to_domain(document_orm: UploadedDocumentORM) -> UploadedDocument:
    """преобразовать ORM-документ в доменную сущность"""
    return UploadedDocument(
        owner_id=document_orm.owner_id,
        original_filename=document_orm.filename,
        storage_path=document_orm.storage_path,
        mime_type=document_orm.mime_type,
        document_type=parse_document_type(document_orm.document_type),
        size_bytes=document_orm.file_size,
        entity_id=document_orm.id,
        uploaded_at=document_orm.uploaded_at,
    )


def sync_user_orm_from_domain(user_orm: UserORM, user: User) -> None:
    """синхронизировать изменяемые поля ORM-модели пользователя из доменной сущности"""
    user_orm.balance_credits = user.balance_credits
    user_orm.is_active = user.is_active


def sync_task_orm_from_domain(task_orm: MLTaskORM, task: MLTask) -> None:
    """синхронизировать изменяемые поля ORM-задачи из доменной сущности"""
    task_orm.status = task.status.value
    task_orm.spent_credits = task.spent_credits
    task_orm.error_message = task.error_message
    task_orm.started_at = task.started_at
    task_orm.completed_at = task.finished_at  # ORM: completed_at; domain: finished_at


def task_orm_to_domain(task_orm: MLTaskORM) -> DocumentExtractionTask:
    """преобразовать ORM-задачу в доменную сущность DocumentExtractionTask"""
    result_id = None
    if task_orm.prediction_result is not None:
        result_id = task_orm.prediction_result.id

    return DocumentExtractionTask(
        user_id=task_orm.user_id,
        model_id=task_orm.model_id,
        documents=[document_orm_to_domain(doc) for doc in task_orm.documents],
        target_schema=task_orm.target_schema or "",
        entity_id=task_orm.id,
        status=TaskStatus(task_orm.status),
        created_at=task_orm.created_at,
        started_at=task_orm.started_at,
        finished_at=task_orm.completed_at,
        error_message=task_orm.error_message,
        spent_credits=task_orm.spent_credits,
        result_id=result_id,
        callback_url=task_orm.callback_url,
    )


def transaction_orm_to_item(transaction_orm: TransactionORM) -> TransactionHistoryItem:
    """преобразовать ORM-транзакцию в DTO истории"""
    return TransactionHistoryItem(
        id=transaction_orm.id,
        user_id=transaction_orm.user_id,
        task_id=transaction_orm.task_id,
        transaction_type=TransactionType(transaction_orm.transaction_type),
        amount=transaction_orm.amount,
        created_at=transaction_orm.created_at,
    )


def history_orm_to_item(history_orm: MLRequestHistoryORM) -> PredictionHistoryItem:
    """преобразовать ORM-запись истории в DTO истории предиктов"""
    return PredictionHistoryItem(
        id=history_orm.id,
        user_id=history_orm.user_id,
        task_id=history_orm.task_id,
        model_id=history_orm.model_id,
        result_id=history_orm.result_id,
        status=TaskStatus(history_orm.status),
        spent_credits=history_orm.spent_credits,
        created_at=history_orm.created_at,
        completed_at=history_orm.completed_at,
    )


def domain_history_to_orm(record: MLRequestHistoryRecord) -> MLRequestHistoryORM:
    """преобразовать доменную запись истории в ORM-модель"""
    return MLRequestHistoryORM(
        id=record.id,
        user_id=record.user_id,
        task_id=record.task_id,
        model_id=record.model_id,
        result_id=record.result_id,
        status=record.status.value,
        spent_credits=record.spent_credits,
        created_at=record.created_at,
        completed_at=record.completed_at,
    )