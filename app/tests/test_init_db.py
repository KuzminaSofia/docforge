from __future__ import annotations

from sqlalchemy import select

from technical_document_ml_service.db.init_db import seed_initial_data
from technical_document_ml_service.db.models import MLModelORM, UserORM


def test_seed_initial_data_creates_demo_data_and_is_idempotent(session_factory) -> None:
    with session_factory.begin() as session:
        seed_initial_data(session)

    with session_factory() as session:
        users_after_first_run = session.scalars(select(UserORM)).all()
        models_after_first_run = session.scalars(select(MLModelORM)).all()

    assert len(users_after_first_run) == 2
    assert len(models_after_first_run) == 3

    emails = {user.email for user in users_after_first_run}
    models_by_name = {model.name: model for model in models_after_first_run}

    assert "demo.user@example.com" in emails
    assert "demo.admin@example.com" in emails
    assert "technical-document-extractor-basic" in models_by_name
    assert "technical-document-extractor-advanced" in models_by_name
    assert "technical-document-extractor-datalab" in models_by_name

    # docling-модели не несут секретов и спец-конфига
    for name in ("technical-document-extractor-basic", "technical-document-extractor-advanced"):
        assert models_by_name[name].backend_name == "docling"
        assert models_by_name[name].backend_config == {}

    # datalab-модель: backend datalab, секрет в config не хранится (только mode)
    datalab_model = models_by_name["technical-document-extractor-datalab"]
    assert datalab_model.backend_name == "datalab"
    assert datalab_model.backend_config == {"mode": "fast"}
    assert "api_key" not in datalab_model.backend_config

    with session_factory.begin() as session:
        seed_initial_data(session)

    with session_factory() as session:
        users_after_second_run = session.scalars(select(UserORM)).all()
        models_after_second_run = session.scalars(select(MLModelORM)).all()

    assert len(users_after_second_run) == 2
    assert len(models_after_second_run) == 3