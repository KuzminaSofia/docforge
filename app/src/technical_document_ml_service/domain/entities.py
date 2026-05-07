"""основные сощности доменной модели ML-сервиса"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from .enums import DocumentType, TaskStatus, TransactionType, UserRole
from .exceptions import (
    DomainError,
    InsufficientBalanceError,
    InvalidAmountError,
    TaskExecutionError,
)


class BaseEntity:
    """базовый класс для всех сущностей доменной модели"""

    def __init__(self, entity_id: UUID | None = None) -> None:
        self._id: UUID = entity_id or uuid4()

    @property
    def id(self) -> UUID:
        """вернуть уникальный идентификатор сущности"""
        return self._id


class User(BaseEntity):
    """пользователь ML-сервиса
    пользователь имеет данные для авторизации, роль в системе
    и баланс в условных кредитах
    """

    def __init__(
        self,
        email: str,
        password_hash: str,
        role: UserRole = UserRole.USER,
        balance_credits: Decimal = Decimal("0"),
        is_active: bool = True,
        entity_id: UUID | None = None,
        created_at: datetime | None = None,
    ) -> None:
        super().__init__(entity_id=entity_id)
        self._email: str = email
        self._password_hash: str = password_hash
        self._role: UserRole = role
        self._balance_credits: Decimal = balance_credits
        self._is_active: bool = is_active
        self._created_at: datetime = created_at or datetime.now(UTC)

    @property
    def email(self) -> str:
        """вернуть электронную почту пользователя"""
        return self._email

    @property
    def role(self) -> UserRole:
        """вернуть роль пользователя"""
        return self._role

    @property
    def balance_credits(self) -> Decimal:
        """вернуть текущий баланс пользователя в кредитах"""
        return self._balance_credits

    @property
    def is_active(self) -> bool:
        """проверить, активен ли пользователь"""
        return self._is_active

    @property
    def created_at(self) -> datetime:
        """вернуть дату и время создания пользователя"""
        return self._created_at

    def check_password(self, raw_password: str, hasher) -> bool:
        """проверить пароль через переданную функцию верификации"""
        return hasher(raw_password, self._password_hash)

    def can_afford(self, amount: Decimal) -> bool:
        """проверить, хватает ли пользователю средств на операцию"""
        return self._balance_credits >= amount

    def activate(self) -> None:
        """активировать пользователя"""
        self._is_active = True

    def deactivate(self) -> None:
        """деактивировать пользователя"""
        self._is_active = False

    def _increase_balance(self, amount: Decimal) -> None:
        """увеличить баланс пользователя
        он должен вызываться через объект транзакции
        """
        if amount <= Decimal("0"):
            raise InvalidAmountError("Сумма пополнения должна быть положительной.")
        self._balance_credits += amount

    def _decrease_balance(self, amount: Decimal) -> None:
        """уменьшить баланс пользователя
        он должен вызываться через объект транзакции
        """
        if amount <= Decimal("0"):
            raise InvalidAmountError("Сумма списания должна быть положительной.")
        if not self.can_afford(amount):
            raise InsufficientBalanceError("Недостаточно средств на балансе.")
        self._balance_credits -= amount


class UploadedDocument(BaseEntity):
    """загруженный пользователем документ для ML-обработки"""

    SUPPORTED_MIME_TYPES = frozenset(
        {
            "application/pdf",
            "image/png",
            "image/jpeg",
            "image/jpg",
        }
    )

    def __init__(
        self,
        owner_id: UUID,
        original_filename: str,
        storage_path: str,
        mime_type: str,
        document_type: DocumentType = DocumentType.UNKNOWN,
        size_bytes: int = 0,
        entity_id: UUID | None = None,
        uploaded_at: datetime | None = None,
    ) -> None:
        super().__init__(entity_id=entity_id)
        self._owner_id: UUID = owner_id
        self._original_filename: str = original_filename
        self._storage_path: str = storage_path
        self._mime_type: str = mime_type
        self._document_type: DocumentType = document_type
        self._size_bytes: int = size_bytes
        self._uploaded_at: datetime = uploaded_at or datetime.now(UTC)

    @property
    def owner_id(self) -> UUID:
        """вернуть идентификатор владельца документа"""
        return self._owner_id

    @property
    def original_filename(self) -> str:
        """вернуть исходное имя файла"""
        return self._original_filename

    @property
    def storage_path(self) -> str:
        """вернуть путь хранения файла"""
        return self._storage_path

    @property
    def mime_type(self) -> str:
        """вернуть MIME-тип файла"""
        return self._mime_type

    @property
    def document_type(self) -> DocumentType:
        """вернуть тип документа предметной области"""
        return self._document_type

    @property
    def size_bytes(self) -> int:
        """вернуть размер файла в байтах"""
        return self._size_bytes

    @property
    def uploaded_at(self) -> datetime:
        """вернуть дату и время загрузки документа"""
        return self._uploaded_at

    def is_supported_format(self) -> bool:
        """проверить, поддерживается ли формат файла сервисом"""
        return self._mime_type in self.SUPPORTED_MIME_TYPES


@dataclass(frozen=True, slots=True)
class ValidationIssue:
    """ошибка или замечание, найденное при валидации входных данных"""

    field_name: str
    message: str
    raw_value: Any | None = None


class PredictionResult(BaseEntity):
    """результат работы ML-модели
    содержит извлеченные структурированные данные, список ошибок
    валидации и сведения о сохраненных артефактах обработки
    """

    def __init__(
        self,
        task_id: UUID,
        extracted_data: dict[str, Any] | None = None,
        validation_issues: list[ValidationIssue] | None = None,
        output_path: str | None = None,
        artifacts_dir: str | None = None,
        artifacts_manifest: list[dict[str, Any]] | None = None,
        entity_id: UUID | None = None,
        created_at: datetime | None = None,
    ) -> None:
        super().__init__(entity_id=entity_id)
        self._task_id: UUID = task_id
        self._extracted_data: dict[str, Any] = extracted_data or {}
        self._validation_issues: list[ValidationIssue] = validation_issues or []
        self._output_path: str | None = output_path
        self._artifacts_dir: str | None = artifacts_dir
        self._artifacts_manifest: list[dict[str, Any]] = artifacts_manifest or []
        self._created_at: datetime = created_at or datetime.now(UTC)

    @property
    def task_id(self) -> UUID:
        """вернуть идентификатор ML-задачи"""
        return self._task_id

    @property
    def extracted_data(self) -> dict[str, Any]:
        """вернуть извлеченные структурированные данные"""
        return self._extracted_data

    @property
    def validation_issues(self) -> list[ValidationIssue]:
        """вернуть список найденных ошибок валидации"""
        return self._validation_issues

    @property
    def output_path(self) -> str | None:
        """вернуть путь к сохраненному результату, если он есть"""
        return self._output_path

    @property
    def artifacts_dir(self) -> str | None:
        """вернуть директорию с артефактами обработки, если она есть"""
        return self._artifacts_dir

    @property
    def artifacts_manifest(self) -> list[dict[str, Any]]:
        """вернуть описание сохраненных артефактов обработки"""
        return self._artifacts_manifest

    @property
    def created_at(self) -> datetime:
        """вернуть дату и время создания результата"""
        return self._created_at

    def add_issue(self, issue: ValidationIssue) -> None:
        """добавить одну ошибку валидации в результат"""
        self._validation_issues.append(issue)

    def add_issues(self, issues: list[ValidationIssue]) -> None:
        """добавить несколько ошибок валидации в результат"""
        self._validation_issues.extend(issues)

    def has_issues(self) -> bool:
        """проверить, содержит ли результат ошибки валидации"""
        return len(self._validation_issues) > 0


class Transaction(BaseEntity, ABC):
    """абстрактная транзакция по балансу пользователя"""

    def __init__(
        self,
        user_id: UUID,
        amount: Decimal,
        task_id: UUID | None = None,
        entity_id: UUID | None = None,
        created_at: datetime | None = None,
    ) -> None:
        super().__init__(entity_id=entity_id)
        self._user_id: UUID = user_id
        self._amount: Decimal = amount
        self._task_id: UUID | None = task_id
        self._created_at: datetime = created_at or datetime.now(UTC)

    @property
    def user_id(self) -> UUID:
        """вернуть идентификатор пользователя"""
        return self._user_id

    @property
    def amount(self) -> Decimal:
        """вернуть сумму транзакции"""
        return self._amount

    @property
    def task_id(self) -> UUID | None:
        """вернуть идентификатор связанной ML-задачи, если он есть"""
        return self._task_id

    @property
    def created_at(self) -> datetime:
        """вернуть дату и время создания транзакции"""
        return self._created_at

    @property
    @abstractmethod
    def transaction_type(self) -> TransactionType:
        """вернуть тип транзакции"""
        raise NotImplementedError

    @abstractmethod
    def apply(self, user: User) -> None:
        """применить транзакцию к пользователю"""
        raise NotImplementedError


class CreditTransaction(Transaction):
    """транзакция пополнения баланса пользователя"""

    @property
    def transaction_type(self) -> TransactionType:
        """вернуть тип транзакции"""
        return TransactionType.CREDIT

    def apply(self, user: User) -> None:
        """применить пополнение баланса к пользователю"""
        if user.id != self.user_id:
            raise DomainError("Транзакция не соответствует пользователю.")
        user._increase_balance(self.amount)


class DebitTransaction(Transaction):
    """транзакция списания средств с баланса пользователя"""

    @property
    def transaction_type(self) -> TransactionType:
        """вернуть тип транзакции"""
        return TransactionType.DEBIT

    def apply(self, user: User) -> None:
        """применить списание средств к пользователю"""
        if user.id != self.user_id:
            raise DomainError("Транзакция не соответствует пользователю.")
        user._decrease_balance(self.amount)


class MLModel(BaseEntity):
    """абстракция ML-модели, доступной в сервисе"""

    def __init__(
        self,
        name: str,
        description: str,
        prediction_cost: Decimal,
        is_active: bool = True,
        entity_id: UUID | None = None,
    ) -> None:
        super().__init__(entity_id=entity_id)
        self._name: str = name
        self._description: str = description
        self._prediction_cost: Decimal = prediction_cost
        self._is_active: bool = is_active

    @property
    def name(self) -> str:
        """вернуть название модели"""
        return self._name

    @property
    def description(self) -> str:
        """вернуть описание модели"""
        return self._description

    @property
    def prediction_cost(self) -> Decimal:
        """вернуть стоимость одного запроса к модели в кредитах"""
        return self._prediction_cost

    @property
    def is_active(self) -> bool:
        """проверить, доступна ли модель для использования"""
        return self._is_active

    def activate(self) -> None:
        """активировать модель"""
        self._is_active = True

    def deactivate(self) -> None:
        """деактивировать модель"""
        self._is_active = False


class TechnicalDocumentExtractionModel(MLModel):
    """доменная абстракция модели извлечения данных из технической документации"""

    def __init__(
        self,
        name: str,
        description: str,
        prediction_cost: Decimal,
        supported_document_types: set[DocumentType],
        is_active: bool = True,
        entity_id: UUID | None = None,
    ) -> None:
        super().__init__(
            name=name,
            description=description,
            prediction_cost=prediction_cost,
            is_active=is_active,
            entity_id=entity_id,
        )
        self._supported_document_types: set[DocumentType] = supported_document_types

    @property
    def supported_document_types(self) -> set[DocumentType]:
        """вернуть поддерживаемые типы документов"""
        return self._supported_document_types


class MLTask(BaseEntity, ABC):
    """абстрактная ML-задача
    задача связывает пользователя, выбранную модель и входные данные,
    которые необходимо обработать
    """

    def __init__(
        self,
        user_id: UUID,
        model_id: UUID,
        entity_id: UUID | None = None,
        status: TaskStatus = TaskStatus.CREATED,
        created_at: datetime | None = None,
        started_at: datetime | None = None,
        finished_at: datetime | None = None,
        error_message: str | None = None,
        spent_credits: Decimal = Decimal("0"),
        result_id: UUID | None = None,
    ) -> None:
        super().__init__(entity_id=entity_id)
        self._user_id: UUID = user_id
        self._model_id: UUID = model_id
        self._status: TaskStatus = status
        self._created_at: datetime = created_at or datetime.now(UTC)
        self._started_at: datetime | None = started_at
        self._finished_at: datetime | None = finished_at
        self._error_message: str | None = error_message
        self._spent_credits: Decimal = spent_credits
        self._result_id: UUID | None = result_id

    @property
    def user_id(self) -> UUID:
        """вернуть идентификатор владельца задачи"""
        return self._user_id

    @property
    def model_id(self) -> UUID:
        """вернуть идентификатор выбранной модели"""
        return self._model_id

    @property
    def status(self) -> TaskStatus:
        """вернуть текущий статус задачи"""
        return self._status

    @property
    def created_at(self) -> datetime:
        """вернуть дату и время создания задачи"""
        return self._created_at

    @property
    def started_at(self) -> datetime | None:
        """вернуть дату и время запуска задачи"""
        return self._started_at

    @property
    def finished_at(self) -> datetime | None:
        """вернуть дату и время завершения задачи"""
        return self._finished_at

    @property
    def error_message(self) -> str | None:
        """вернуть текст ошибки, если задача завершилась с ошибкой"""
        return self._error_message

    @property
    def spent_credits(self) -> Decimal:
        """вернуть количество списанных кредитов"""
        return self._spent_credits

    @property
    def result_id(self) -> UUID | None:
        """вернуть идентификатор результата, если он есть"""
        return self._result_id

    @abstractmethod
    def validate_input(self) -> list[ValidationIssue]:
        """провалидировать входные данные задачи"""
        raise NotImplementedError

    def mark_as_queued(self) -> None:
        """перевести новую задачу в статус ожидания обработки в очереди"""
        if self._status != TaskStatus.CREATED:
            raise TaskExecutionError("В очередь можно поставить только новую задачу.")
        self._status = TaskStatus.QUEUED

    def mark_as_validating(self) -> None:
        """перевести задачу в статус валидации"""
        if self._status not in {TaskStatus.CREATED, TaskStatus.QUEUED}:
            raise TaskExecutionError(
                "На валидацию можно перевести только новую или поставленную в очередь задачу."
            )
        self._status = TaskStatus.VALIDATING

    def mark_as_processing(self) -> None:
        """перевести задачу в статус обработки"""
        if self._status not in {
            TaskStatus.CREATED,
            TaskStatus.QUEUED,
            TaskStatus.VALIDATING,
        }:
            raise TaskExecutionError(
                "В обработку можно перевести только новую, queued или validating задачу."
            )
        self._status = TaskStatus.PROCESSING
        if self._started_at is None:
            self._started_at = datetime.now(UTC)

    def mark_as_completed(
        self,
        *,
        result_id: UUID,
        spent_credits: Decimal,
    ) -> None:
        """завершить задачу успешно"""
        if self._status not in {TaskStatus.PROCESSING, TaskStatus.VALIDATING}:
            raise TaskExecutionError(
                "Завершить можно только задачу, находящуюся в обработке."
            )

        self._status = TaskStatus.COMPLETED
        self._spent_credits = spent_credits
        self._result_id = result_id
        self._error_message = None
        self._finished_at = datetime.now(UTC)

    def fail(self, error_message: str) -> None:
        """перевести задачу в статус ошибки"""
        self._status = TaskStatus.FAILED
        self._error_message = error_message
        self._finished_at = datetime.now(UTC)


class DocumentExtractionTask(MLTask):
    """ML-задача по извлечению данных из технических документов"""

    def __init__(
        self,
        user_id: UUID,
        model_id: UUID,
        documents: list[UploadedDocument],
        target_schema: str,
        entity_id: UUID | None = None,
        status: TaskStatus = TaskStatus.CREATED,
        created_at: datetime | None = None,
        started_at: datetime | None = None,
        finished_at: datetime | None = None,
        error_message: str | None = None,
        spent_credits: Decimal = Decimal("0"),
        result_id: UUID | None = None,
        callback_url: str | None = None,
    ) -> None:
        super().__init__(
            user_id=user_id,
            model_id=model_id,
            entity_id=entity_id,
            status=status,
            created_at=created_at,
            started_at=started_at,
            finished_at=finished_at,
            error_message=error_message,
            spent_credits=spent_credits,
            result_id=result_id,
        )
        self._documents: list[UploadedDocument] = documents
        self._target_schema: str = target_schema
        self._callback_url: str | None = callback_url

    @property
    def documents(self) -> list[UploadedDocument]:
        """вернуть список всех документов, прикрепленных к задаче"""
        return self._documents

    @property
    def target_schema(self) -> str:
        """вернуть название целевой схемы извлечения"""
        return self._target_schema

    @property
    def callback_url(self) -> str | None:
        """вернуть URL для webhook-уведомления о завершении задачи"""
        return self._callback_url

    def get_valid_documents(self) -> list[UploadedDocument]:
        """вернуть только те документы, которые прошли базовую проверку формата"""
        return [document for document in self._documents if document.is_supported_format()]

    def validate_input(self) -> list[ValidationIssue]:
        """провалидировать входные документы и целевую схему"""
        issues: list[ValidationIssue] = []

        if not self._documents:
            issues.append(
                ValidationIssue(
                    field_name="documents",
                    message="Для обработки не передан ни один документ.",
                )
            )
            return issues

        for document in self._documents:
            if not document.is_supported_format():
                issues.append(
                    ValidationIssue(
                        field_name=document.original_filename,
                        message="Неподдерживаемый формат файла.",
                        raw_value=document.mime_type,
                    )
                )

        if not self._target_schema.strip():
            issues.append(
                ValidationIssue(
                    field_name="target_schema",
                    message="Целевая схема извлечения не указана.",
                    raw_value=self._target_schema,
                )
            )

        return issues


class MLRequestHistoryRecord(BaseEntity):
    """запись в истории ML-запросов пользователя"""

    def __init__(
        self,
        user_id: UUID,
        task_id: UUID,
        model_id: UUID,
        status: TaskStatus,
        spent_credits: Decimal,
        result_id: UUID | None,
        created_at: datetime,
        completed_at: datetime | None,
        entity_id: UUID | None = None,
    ) -> None:
        super().__init__(entity_id=entity_id)
        self._user_id: UUID = user_id
        self._task_id: UUID = task_id
        self._model_id: UUID = model_id
        self._status: TaskStatus = status
        self._spent_credits: Decimal = spent_credits
        self._result_id: UUID | None = result_id
        self._created_at: datetime = created_at
        self._completed_at: datetime | None = completed_at

    @property
    def user_id(self) -> UUID:
        """вернуть идентификатор пользователя"""
        return self._user_id

    @property
    def task_id(self) -> UUID:
        """вернуть идентификатор ML-задачи"""
        return self._task_id

    @property
    def model_id(self) -> UUID:
        """вернуть идентификатор ML-модели"""
        return self._model_id

    @property
    def status(self) -> TaskStatus:
        """вернуть финальный статус задачи"""
        return self._status

    @property
    def spent_credits(self) -> Decimal:
        """вернуть количество кредитов, списанных за задачу"""
        return self._spent_credits

    @property
    def result_id(self) -> UUID | None:
        """вернуть идентификатор результата обработки"""
        return self._result_id

    @property
    def created_at(self) -> datetime:
        """вернуть дату и время создания запроса"""
        return self._created_at

    @property
    def completed_at(self) -> datetime | None:
        """вернуть дату и время завершения запроса"""
        return self._completed_at

    @classmethod
    def from_task(cls, task: MLTask) -> "MLRequestHistoryRecord":
        """создать запись истории на основе ML-задачи"""
        return cls(
            user_id=task.user_id,
            task_id=task.id,
            model_id=task.model_id,
            status=task.status,
            spent_credits=task.spent_credits,
            result_id=task.result_id,
            created_at=task.created_at,
            completed_at=task.finished_at,
        )