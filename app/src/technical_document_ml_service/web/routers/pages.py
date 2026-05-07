from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Query, Request
from fastapi.responses import RedirectResponse
from pydantic import ValidationError

from technical_document_ml_service.api.deps import ReadSessionDep
from technical_document_ml_service.api.schemas.history import (
    PredictionHistoryItemResponse,
    TransactionHistoryItemResponse,
)
from technical_document_ml_service.api.schemas.tasks import (
    TaskDetailsResponse,
    TaskListItemResponse,
    TaskListQueryParams,
    TaskResultResponse,
)
from technical_document_ml_service.services.billing_service import get_user_transactions
from technical_document_ml_service.services.history_service import (
    get_user_prediction_history,
)
from technical_document_ml_service.services.artifact_service import read_markdown_artifact
from technical_document_ml_service.services.task_query_service import (
    get_user_task_details,
    get_user_task_result,
    get_user_tasks,
)
from technical_document_ml_service.domain.enums import TaskStatus
from technical_document_ml_service.web.deps import CurrentOptionalWebUserDep
from technical_document_ml_service.services.model_query_service import get_active_models
from technical_document_ml_service.web.templating import forge_page_context, render_template


logger = logging.getLogger(__name__)
router = APIRouter(tags=["web-pages"])


@router.get("/", name="home_page")
def home_page(
    request: Request,
    current_user: CurrentOptionalWebUserDep,
):
    """главная страница сервиса"""
    return render_template(
        request,
        "index.html",
        page_title="Главная",
        current_user=current_user,
    )


@router.get("/login", name="login_page")
def login_page(
    request: Request,
    current_user: CurrentOptionalWebUserDep,
):
    """страница входа"""
    if current_user is not None:
        return RedirectResponse(url="/dashboard", status_code=303)

    return render_template(
        request,
        "login.html",
        page_title="Вход",
        current_user=None,
        form_data={"email": ""},
        error_message=None,
    )


@router.get("/register", name="register_page")
def register_page(
    request: Request,
    current_user: CurrentOptionalWebUserDep,
):
    """страница регистрации"""
    if current_user is not None:
        return RedirectResponse(url="/dashboard", status_code=303)

    return render_template(
        request,
        "register.html",
        page_title="Регистрация",
        current_user=None,
        form_data={"email": ""},
        error_message=None,
    )


@router.get("/dashboard", name="dashboard_page")
def dashboard_page(
    request: Request,
    current_user: CurrentOptionalWebUserDep,
):
    """личный кабинет пользователя"""
    if current_user is None:
        return RedirectResponse(url="/login", status_code=303)

    return render_template(
        request,
        "dashboard.html",
        page_title="Кабинет",
        current_user=current_user,
        **forge_page_context("dashboard"),
    )


@router.get("/balance-ui", name="balance_page")
def balance_page(
    request: Request,
    current_user: CurrentOptionalWebUserDep,
    success: str | None = Query(default=None),
):
    """страница баланса и пополнения"""
    if current_user is None:
        return RedirectResponse(url="/login", status_code=303)

    success_message = None
    if success == "topup":
        success_message = "Баланс успешно пополнен."

    return render_template(
        request,
        "balance.html",
        page_title="Пополение баланса",
        current_user=current_user,
        success_message=success_message,
        error_message=None,
        form_data={"amount": "10.00"},
        **forge_page_context(None),
    )


@router.get("/predict-ui", name="predict_page")
def predict_page(
    request: Request,
    session: ReadSessionDep,
    current_user: CurrentOptionalWebUserDep,
):
    """страница отправки ML-задачи"""
    if current_user is None:
        return RedirectResponse(url="/login", status_code=303)

    models = get_active_models(session)

    return render_template(
        request,
        "predict.html",
        page_title="Новая обработка",
        current_user=current_user,
        models=models,
        error_message=None,
        form_data={
            "model_name": models[0]["name"] if models else "",
            "target_schema": "default_schema",
        },
        **forge_page_context("predict"),
    )


@router.get("/tasks-ui", name="tasks_page")
def tasks_page(
    request: Request,
    session: ReadSessionDep,
    current_user: CurrentOptionalWebUserDep,
    status: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
):
    """страница списка задач пользователя"""
    if current_user is None:
        return RedirectResponse(url="/login", status_code=303)

    normalized_status = None
    if status is not None:
        stripped = status.strip().lower()
        normalized_status = stripped or None

    try:
        query = TaskListQueryParams(
            status=normalized_status,
            limit=limit,
            offset=offset,
        )
    except ValidationError:
        valid_statuses = ", ".join(s.value for s in TaskStatus)
        return render_template(
            request,
            "tasks.html",
            page_title="Задачи",
            current_user=current_user,
            tasks=[],
            current_status=normalized_status or "",
            limit=limit,
            offset=offset,
            error_message=f"Некорректный фильтр статуса. Допустимые значения: {valid_statuses}.",
            **forge_page_context("tasks"),
        )

    items = get_user_tasks(
        session,
        user_id=current_user.id,
        limit=query.limit,
        offset=query.offset,
        status=query.status,
    )

    tasks = [
        TaskListItemResponse.from_item(item).model_dump(mode="json")
        for item in items
    ]

    current_status = query.status.value if query.status is not None else ""

    return render_template(
        request,
        "tasks.html",
        page_title="Задачи",
        current_user=current_user,
        tasks=tasks,
        current_status=current_status,
        limit=query.limit,
        offset=query.offset,
        error_message=None,
        **forge_page_context("tasks"),
    )


@router.get("/tasks-ui/{task_id}", name="task_detail_page")
def task_detail_page(
    task_id: UUID,
    request: Request,
    session: ReadSessionDep,
    current_user: CurrentOptionalWebUserDep,
):
    """детальная страница задачи"""
    if current_user is None:
        return RedirectResponse(url="/login", status_code=303)

    task_details = get_user_task_details(
        session,
        user_id=current_user.id,
        task_id=task_id,
    )
    task = TaskDetailsResponse.from_item(task_details).model_dump(mode="json")

    result_bundle = None
    result = None
    artifacts: list[dict[str, Any]] = []
    markdown_artifact = None
    markdown_content = None
    result_warning_message = None

    task_status = str(task.get("status", "")).lower()
    if task_status == "completed":
        try:
            bundle = get_user_task_result(
                session,
                user_id=current_user.id,
                task_id=task_id,
            )
            result_bundle = TaskResultResponse.from_bundle(bundle).model_dump(mode="json")
            result = result_bundle.get("result")
            artifacts = result_bundle.get("artifacts", [])

            markdown_artifact = read_markdown_artifact(
                artifacts,
                result=result,
            )
            markdown_content = (
                markdown_artifact["content"]
                if markdown_artifact is not None
                else None
            )
        except Exception:
            logger.exception(
                "Failed to load task result for task_id=%s user_id=%s",
                task_id,
                current_user.id,
            )
            result_bundle = None
            result = None
            artifacts = []
            markdown_artifact = None
            markdown_content = None
            result_warning_message = (
                "Задача завершена, но результат пока не удалось отобразить."
            )

    auto_refresh = task_status not in {"completed", "failed"}

    return render_template(
        request,
        "task_detail.html",
        page_title=f"Обработка {task_id}",
        current_user=current_user,
        task=task,
        result_bundle=result_bundle,
        result=result,
        artifacts=artifacts,
        markdown_artifact=markdown_artifact,
        markdown_content=markdown_content,
        result_warning_message=result_warning_message,
        auto_refresh=auto_refresh,
        **forge_page_context("tasks"),
    )


@router.get("/history-ui", name="history_page")
def history_page(
    request: Request,
    session: ReadSessionDep,
    current_user: CurrentOptionalWebUserDep,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
):
    """страница истории операций и предсказаний"""
    if current_user is None:
        return RedirectResponse(url="/login", status_code=303)

    transaction_items = get_user_transactions(
        session,
        user_id=current_user.id,
        limit=limit,
        offset=offset,
    )
    prediction_items = get_user_prediction_history(
        session,
        user_id=current_user.id,
        limit=limit,
        offset=offset,
    )

    transactions = [
        TransactionHistoryItemResponse.from_item(item).model_dump(mode="json")
        for item in transaction_items
    ]
    predictions = [
        PredictionHistoryItemResponse.from_item(item).model_dump(mode="json")
        for item in prediction_items
    ]

    return render_template(
        request,
        "history.html",
        page_title="История",
        current_user=current_user,
        transactions=transactions,
        predictions=predictions,
        limit=limit,
        offset=offset,
        **forge_page_context("history"),
    )