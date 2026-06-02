"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-05-20

"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("role", sa.String(50), nullable=False),
        sa.Column(
            "balance_credits",
            sa.Numeric(12, 2),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("balance_credits >= 0", name="ck_users_balance_non_negative"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email"),
    )

    op.create_table(
        "ml_models",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("prediction_cost", sa.Numeric(12, 2), nullable=False),
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
        sa.Column("model_kind", sa.String(100), nullable=False),
        sa.Column(
            "supported_document_types",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "backend_name",
            sa.String(100),
            nullable=False,
            server_default=sa.text("'docling'"),
        ),
        sa.Column(
            "backend_config",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.CheckConstraint(
            "prediction_cost >= 0",
            name="ck_ml_models_prediction_cost_non_negative",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )

    op.create_table(
        "uploaded_documents",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "owner_id",
            sa.Uuid(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("filename", sa.String(255), nullable=False),
        sa.Column("storage_path", sa.String(500), nullable=False),
        sa.Column("mime_type", sa.String(100), nullable=False),
        sa.Column("document_type", sa.String(100), nullable=False),
        sa.Column("file_size", sa.BigInteger(), nullable=False),
        sa.Column("uploaded_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "file_size >= 0",
            name="ck_uploaded_documents_file_size_non_negative",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_uploaded_documents_owner_id_uploaded_at",
        "uploaded_documents",
        ["owner_id", "uploaded_at"],
    )
    op.create_index(
        "ix_uploaded_documents_document_type",
        "uploaded_documents",
        ["document_type"],
    )

    op.create_table(
        "ml_tasks",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "user_id",
            sa.Uuid(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "model_id",
            sa.Uuid(),
            sa.ForeignKey("ml_models.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("status", sa.String(50), nullable=False),
        sa.Column(
            "spent_credits",
            sa.Numeric(12, 2),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column("target_schema", sa.Text(), nullable=True),
        sa.Column("callback_url", sa.String(2048), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "spent_credits >= 0",
            name="ck_ml_tasks_spent_credits_non_negative",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_ml_tasks_user_id_created_at",
        "ml_tasks",
        ["user_id", "created_at"],
    )
    op.create_index(
        "ix_ml_tasks_model_id_created_at",
        "ml_tasks",
        ["model_id", "created_at"],
    )
    op.create_index("ix_ml_tasks_status", "ml_tasks", ["status"])

    op.create_table(
        "task_documents",
        sa.Column(
            "task_id",
            sa.Uuid(),
            sa.ForeignKey("ml_tasks.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "document_id",
            sa.Uuid(),
            sa.ForeignKey("uploaded_documents.id", ondelete="CASCADE"),
            primary_key=True,
        ),
    )
    op.create_index(
        "ix_task_documents_document_id",
        "task_documents",
        ["document_id"],
    )

    op.create_table(
        "transactions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "user_id",
            sa.Uuid(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "task_id",
            sa.Uuid(),
            sa.ForeignKey("ml_tasks.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("transaction_type", sa.String(50), nullable=False),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("amount > 0", name="ck_transactions_amount_positive"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_transactions_user_id_created_at",
        "transactions",
        ["user_id", "created_at"],
    )
    op.create_index("ix_transactions_task_id", "transactions", ["task_id"])
    op.create_index("ix_transactions_type", "transactions", ["transaction_type"])

    op.create_table(
        "prediction_results",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "task_id",
            sa.Uuid(),
            sa.ForeignKey("ml_tasks.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column("extracted_data", postgresql.JSONB(), nullable=False),
        sa.Column(
            "validation_issues",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("output_file_path", sa.String(500), nullable=True),
        sa.Column("artifacts_dir", sa.String(500), nullable=True),
        sa.Column(
            "artifacts_manifest",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "ml_request_history",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "user_id",
            sa.Uuid(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "task_id",
            sa.Uuid(),
            sa.ForeignKey("ml_tasks.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "model_id",
            sa.Uuid(),
            sa.ForeignKey("ml_models.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "result_id",
            sa.Uuid(),
            sa.ForeignKey("prediction_results.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("status", sa.String(50), nullable=False),
        sa.Column(
            "spent_credits",
            sa.Numeric(12, 2),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "spent_credits >= 0",
            name="ck_ml_request_history_spent_credits_non_negative",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_ml_request_history_user_id_created_at",
        "ml_request_history",
        ["user_id", "created_at"],
    )
    op.create_index(
        "ix_ml_request_history_model_id_created_at",
        "ml_request_history",
        ["model_id", "created_at"],
    )
    op.create_index(
        "ix_ml_request_history_task_id",
        "ml_request_history",
        ["task_id"],
    )
    op.create_index(
        "ix_ml_request_history_result_id",
        "ml_request_history",
        ["result_id"],
    )


def downgrade() -> None:
    op.drop_table("ml_request_history")
    op.drop_table("prediction_results")
    op.drop_table("transactions")
    op.drop_table("task_documents")
    op.drop_table("ml_tasks")
    op.drop_table("uploaded_documents")
    op.drop_table("ml_models")
    op.drop_table("users")
