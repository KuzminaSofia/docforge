from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    BIGINT,
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    Table,
    Text,
    Uuid,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from technical_document_ml_service.db.base import Base


def utc_now() -> datetime:
    """текущее время в UTC"""
    return datetime.now(timezone.utc)


task_documents = Table(
    "task_documents",
    Base.metadata,
    Column(
        "task_id",
        Uuid,
        ForeignKey("ml_tasks.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "document_id",
        Uuid,
        ForeignKey("uploaded_documents.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Index("ix_task_documents_document_id", "document_id"),
)


class UserORM(Base):
    """ORM-модель пользователя"""

    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint(
            "balance_credits >= 0",
            name="ck_users_balance_non_negative",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(50), nullable=False)
    balance_credits: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
        nullable=False,
        default=Decimal("0.00"),
        server_default=text("0"),
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default=text("true"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
    )

    tasks: Mapped[list["MLTaskORM"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )
    transactions: Mapped[list["TransactionORM"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )
    request_history: Mapped[list["MLRequestHistoryORM"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )
    uploaded_documents: Mapped[list["UploadedDocumentORM"]] = relationship(
        back_populates="owner",
        cascade="all, delete-orphan",
    )


class MLModelORM(Base):
    """ORM-модель ML-модели"""

    __tablename__ = "ml_models"
    __table_args__ = (
        CheckConstraint(
            "prediction_cost >= 0",
            name="ck_ml_models_prediction_cost_non_negative",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    prediction_cost: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default=text("true"),
    )
    model_kind: Mapped[str] = mapped_column(String(100), nullable=False)
    supported_document_types: Mapped[list[str]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
        server_default=text("'[]'::jsonb"),
    )
    backend_name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        default="docling",
        server_default=text("'docling'"),
    )
    backend_config: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )

    tasks: Mapped[list["MLTaskORM"]] = relationship(back_populates="model")
    request_history: Mapped[list["MLRequestHistoryORM"]] = relationship(
        back_populates="model",
    )


class MLTaskORM(Base):
    """ORM-модель ML-задачи"""

    __tablename__ = "ml_tasks"
    __table_args__ = (
        CheckConstraint(
            "spent_credits >= 0",
            name="ck_ml_tasks_spent_credits_non_negative",
        ),
        Index("ix_ml_tasks_user_id_created_at", "user_id", "created_at"),
        Index("ix_ml_tasks_model_id_created_at", "model_id", "created_at"),
        Index("ix_ml_tasks_status", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    model_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("ml_models.id", ondelete="RESTRICT"),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(String(50), nullable=False)
    spent_credits: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
        nullable=False,
        default=Decimal("0.00"),
        server_default=text("0"),
    )
    target_schema: Mapped[str | None] = mapped_column(Text, nullable=True)
    callback_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
    )

    user: Mapped["UserORM"] = relationship(back_populates="tasks")
    model: Mapped["MLModelORM"] = relationship(back_populates="tasks")

    transactions: Mapped[list["TransactionORM"]] = relationship(back_populates="task")
    request_history: Mapped[list["MLRequestHistoryORM"]] = relationship(
        back_populates="task",
    )
    prediction_result: Mapped["PredictionResultORM | None"] = relationship(
        back_populates="task",
        uselist=False,
        cascade="all, delete-orphan",
        single_parent=True,
    )
    documents: Mapped[list["UploadedDocumentORM"]] = relationship(
        secondary=task_documents,
        back_populates="tasks",
    )


class TransactionORM(Base):
    """ORM-модель транзакции по балансу"""

    __tablename__ = "transactions"
    __table_args__ = (
        CheckConstraint("amount > 0", name="ck_transactions_amount_positive"),
        Index("ix_transactions_user_id_created_at", "user_id", "created_at"),
        Index("ix_transactions_task_id", "task_id"),
        Index("ix_transactions_type", "transaction_type"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    task_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("ml_tasks.id", ondelete="SET NULL"),
        nullable=True,
    )
    transaction_type: Mapped[str] = mapped_column(String(50), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
    )

    user: Mapped["UserORM"] = relationship(back_populates="transactions")
    task: Mapped["MLTaskORM | None"] = relationship(back_populates="transactions")


class UploadedDocumentORM(Base):
    """ORM-модель загруженного документа"""

    __tablename__ = "uploaded_documents"
    __table_args__ = (
        CheckConstraint(
            "file_size >= 0",
            name="ck_uploaded_documents_file_size_non_negative",
        ),
        Index("ix_uploaded_documents_owner_id_uploaded_at", "owner_id", "uploaded_at"),
        Index("ix_uploaded_documents_document_type", "document_type"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    owner_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    storage_path: Mapped[str] = mapped_column(String(500), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(100), nullable=False)
    document_type: Mapped[str] = mapped_column(String(100), nullable=False)
    file_size: Mapped[int] = mapped_column(BIGINT, nullable=False)
    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
    )

    owner: Mapped["UserORM"] = relationship(back_populates="uploaded_documents")
    tasks: Mapped[list["MLTaskORM"]] = relationship(
        secondary=task_documents,
        back_populates="documents",
    )


class PredictionResultORM(Base):
    """ORM-модель результата предсказания"""

    __tablename__ = "prediction_results"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    task_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("ml_tasks.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    extracted_data: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
    )
    validation_issues: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
        server_default=text("'[]'::jsonb"),
    )
    output_file_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    artifacts_dir: Mapped[str | None] = mapped_column(String(500), nullable=True)
    artifacts_manifest: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
        server_default=text("'[]'::jsonb"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
    )

    task: Mapped["MLTaskORM"] = relationship(back_populates="prediction_result")
    request_history: Mapped[list["MLRequestHistoryORM"]] = relationship(
        back_populates="result",
    )


class MLRequestHistoryORM(Base):
    """ORM-модель истории ML-запросов и предсказаний"""

    __tablename__ = "ml_request_history"
    __table_args__ = (
        CheckConstraint(
            "spent_credits >= 0",
            name="ck_ml_request_history_spent_credits_non_negative",
        ),
        Index("ix_ml_request_history_user_id_created_at", "user_id", "created_at"),
        Index("ix_ml_request_history_model_id_created_at", "model_id", "created_at"),
        Index("ix_ml_request_history_task_id", "task_id"),
        Index("ix_ml_request_history_result_id", "result_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    task_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("ml_tasks.id", ondelete="SET NULL"),
        nullable=True,
    )
    model_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("ml_models.id", ondelete="RESTRICT"),
        nullable=False,
    )
    result_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("prediction_results.id", ondelete="SET NULL"),
        nullable=True,
    )
    status: Mapped[str] = mapped_column(String(50), nullable=False)
    spent_credits: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
        nullable=False,
        default=Decimal("0.00"),
        server_default=text("0"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    user: Mapped["UserORM"] = relationship(back_populates="request_history")
    task: Mapped["MLTaskORM | None"] = relationship(back_populates="request_history")
    model: Mapped["MLModelORM"] = relationship(back_populates="request_history")
    result: Mapped["PredictionResultORM | None"] = relationship(
        back_populates="request_history",
    )