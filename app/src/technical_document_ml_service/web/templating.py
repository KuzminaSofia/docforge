from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi import Request
from fastapi.templating import Jinja2Templates
from markupsafe import Markup
from starlette.responses import Response


WEB_DIR = Path(__file__).resolve().parent
TEMPLATES_DIR = WEB_DIR / "templates"
STATIC_DIR = WEB_DIR / "static"

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


def pretty_json(value: Any) -> Markup:
    """
    отрендерить объект в читаемый JSON без ASCII-экранирования кириллицы
    """
    rendered = json.dumps(
        value,
        ensure_ascii=False,
        indent=2,
        default=str,
    )
    return Markup(rendered)


templates.env.filters["pretty_json"] = pretty_json


def forge_page_context(active_page: str | None = None) -> dict[str, Any]:
    """layout-контекст для авторизованных страниц с боковым меню"""
    return {
        "body_class": "body-full-width",
        "page_content_class": "page-content-full-width",
        "hide_site_header": True,
        "active_page": active_page,
    }


def render_template(
    request: Request,
    template_name: str,
    *,
    page_title: str,
    current_user: Any = None,
    status_code: int = 200,
    **context: Any,
) -> Response:
    """отрендерить HTML-шаблон с базовым контекстом"""
    template_context = {
        "request": request,
        "page_title": page_title,
        "current_user": current_user,
        **context,
    }
    return templates.TemplateResponse(
        request,
        template_name,
        template_context,
        status_code=status_code,
    )