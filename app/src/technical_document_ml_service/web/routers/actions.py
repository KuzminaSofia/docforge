from __future__ import annotations

import logging
from decimal import Decimal, InvalidOperation

from fastapi import APIRouter, Form, Request, UploadFile
from fastapi.responses import RedirectResponse

from technical_document_ml_service.api.deps import ReadSessionDep, SessionDep
from technical_document_ml_service.core.auth_cookies import delete_auth_cookie, set_auth_cookie
from technical_document_ml_service.core.config import app_settings
from technical_document_ml_service.core.security import build_access_token
from technical_document_ml_service.domain.exceptions import (
    AuthenticationError,
    AuthorizationError,
    FileSizeLimitError,
)
from technical_document_ml_service.services.auth_service import (
    authenticate_user,
    register_user,
)
from technical_document_ml_service.services.billing_service import credit_balance
from technical_document_ml_service.services.document_storage_service import (
    IncomingDocumentData,
)
from technical_document_ml_service.services.prediction_submission_service import (
    submit_document_prediction,
)
from technical_document_ml_service.web.deps import CurrentOptionalWebUserDep
from technical_document_ml_service.services.model_query_service import get_active_models
from technical_document_ml_service.web.security import ensure_same_origin
from technical_document_ml_service.web.templating import forge_page_context, render_template


logger = logging.getLogger(__name__)
router = APIRouter(tags=["web-actions"])


@router.post("/login", name="login_action")
def login_action(
    request: Request,
    session: ReadSessionDep,
    email: str = Form(...),
    password: str = Form(...),
):
    """обработать web-форму входа"""
    ensure_same_origin(request)
    normalized_email = email.strip().lower()

    try:
        user = authenticate_user(
            session,
            email=normalized_email,
            password=password,
        )
    except (AuthenticationError, AuthorizationError) as exc:
        return render_template(
            request,
            "login.html",
            page_title="Вход",
            current_user=None,
            form_data={"email": normalized_email},
            error_message=str(exc),
            status_code=401,
        )
    except Exception:
        logger.exception("Unexpected error during web login.")
        return render_template(
            request,
            "login.html",
            page_title="Вход",
            current_user=None,
            form_data={"email": normalized_email},
            error_message="Не удалось выполнить вход. Попробуйте ещё раз.",
            status_code=500,
        )

    access_token, expires_in_seconds = build_access_token(
        user_id=user.id,
        email=user.email,
    )

    response = RedirectResponse(url="/dashboard", status_code=303)
    set_auth_cookie(response, access_token, expires_in_seconds)
    return response


@router.post("/register", name="register_action")
def register_action(
    request: Request,
    session: SessionDep,
    email: str = Form(...),
    password: str = Form(...),
):
    """обработать web-форму регистрации"""
    ensure_same_origin(request)
    normalized_email = email.strip().lower()

    try:
        user = register_user(
            session,
            email=normalized_email,
            password=password,
        )
    except Exception:
        logger.exception("Unexpected error during web registration.")
        return render_template(
            request,
            "register.html",
            page_title="Регистрация",
            current_user=None,
            form_data={"email": normalized_email},
            error_message=(
                "Не удалось зарегистрировать пользователя. "
                "Проверьте корректность данных или попробуйте другой email."
            ),
            status_code=400,
        )

    access_token, expires_in_seconds = build_access_token(
        user_id=user.id,
        email=user.email,
    )

    response = RedirectResponse(url="/dashboard", status_code=303)
    set_auth_cookie(response, access_token, expires_in_seconds)
    return response


@router.post("/logout", name="logout_action")
def logout_action(request: Request):
    """выйти из web-интерфейса"""
    ensure_same_origin(request)

    response = RedirectResponse(url="/", status_code=303)
    delete_auth_cookie(response)
    return response


@router.post("/balance-ui/top-up", name="top_up_action")
def top_up_action(
    request: Request,
    session: SessionDep,
    current_user: CurrentOptionalWebUserDep,
    amount: str = Form(...),
):
    """обработать форму пополнения баланса"""
    ensure_same_origin(request)

    if current_user is None:
        return RedirectResponse(url="/login", status_code=303)

    try:
        parsed_amount = Decimal(amount)
        if parsed_amount <= Decimal("0"):
            raise ValueError
    except (InvalidOperation, ValueError):
        return render_template(
            request,
            "balance.html",
            page_title="Баланс",
            current_user=current_user,
            success_message=None,
            error_message="Введите корректную положительную сумму пополнения.",
            form_data={"amount": amount},
            status_code=400,
            **forge_page_context(None),
        )

    try:
        credit_balance(
            session,
            user_id=current_user.id,
            amount=parsed_amount,
        )
    except Exception:
        logger.exception("Unexpected error during balance top-up.")
        return render_template(
            request,
            "balance.html",
            page_title="Баланс",
            current_user=current_user,
            success_message=None,
            error_message="Не удалось пополнить баланс. Попробуйте ещё раз.",
            form_data={"amount": amount},
            status_code=500,
            **forge_page_context(None),
        )

    return RedirectResponse(url="/balance-ui?success=topup", status_code=303)


@router.post("/predict-ui", name="predict_submit_action")
def predict_submit_action(
    request: Request,
    session: SessionDep,
    current_user: CurrentOptionalWebUserDep,
    model_name: str = Form(...),
    target_schema: str = Form(...),
    documents: list[UploadFile] | None = None,
):
    """обработать web-форму отправки ML-задачи"""
    ensure_same_origin(request)

    if current_user is None:
        return RedirectResponse(url="/login", status_code=303)

    models = get_active_models(session)

    if not documents:
        return render_template(
            request,
            "predict.html",
            page_title="Новая обработка",
            current_user=current_user,
            models=models,
            error_message="Нужно загрузить хотя бы один документ.",
            form_data={
                "model_name": model_name,
                "target_schema": target_schema,
            },
            status_code=400,
            **forge_page_context("predict"),
        )

    max_file_bytes = app_settings.max_upload_file_size_mb * 1024 * 1024
    max_total_bytes = app_settings.max_task_total_size_mb * 1024 * 1024

    incoming_documents: list[IncomingDocumentData] = []
    total_bytes = 0

    def _predict_error(message: str, status_code: int = 400):
        return render_template(
            request,
            "predict.html",
            page_title="Новая обработка",
            current_user=current_user,
            models=models,
            error_message=message,
            form_data={"model_name": model_name, "target_schema": target_schema},
            status_code=status_code,
            **forge_page_context("predict"),
        )

    try:
        for document in documents:
            content = document.file.read()
            file_size = len(content)

            if file_size > max_file_bytes:
                raise FileSizeLimitError(
                    f"Файл '{document.filename}' превышает допустимый размер "
                    f"{app_settings.max_upload_file_size_mb} МБ "
                    f"(получено {file_size / 1024 / 1024:.1f} МБ)."
                )

            total_bytes += file_size
            if total_bytes > max_total_bytes:
                raise FileSizeLimitError(
                    f"Суммарный размер файлов задачи превышает "
                    f"{app_settings.max_task_total_size_mb} МБ."
                )

            incoming_documents.append(
                IncomingDocumentData(
                    filename=document.filename or "document",
                    content_type=document.content_type,
                    content=content,
                )
            )
    except FileSizeLimitError as exc:
        return _predict_error(str(exc), status_code=413)
    finally:
        for document in documents:
            document.file.close()

    try:
        submission = submit_document_prediction(
            session,
            user_id=current_user.id,
            model_name=model_name,
            target_schema=target_schema,
            documents=incoming_documents,
        )
    except Exception:
        logger.exception("Unexpected error during web prediction submission.")
        return _predict_error(
            "Не удалось отправить задачу. "
            "Проверьте баланс, выбранную модель и загруженные документы.",
        )

    return RedirectResponse(
        url=f"/tasks-ui/{submission.task_id}",
        status_code=303,
    )