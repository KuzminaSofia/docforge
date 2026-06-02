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
    assert len(models_after_first_run) == 2

    emails = {user.email for user in users_after_first_run}
    model_names = {model.name for model in models_after_first_run}

    assert "demo.user@example.com" in emails
    assert "demo.admin@example.com" in emails
    assert "technical-document-extractor-basic" in model_names
    assert "technical-document-extractor-advanced" in model_names

    for model in models_after_first_run:
        assert model.backend_name == "docling"
        assert model.backend_config == {}

    with session_factory.begin() as session:
        seed_initial_data(session)

    with session_factory() as session:
        users_after_second_run = session.scalars(select(UserORM)).all()
        models_after_second_run = session.scalars(select(MLModelORM)).all()

    assert len(users_after_second_run) == 2
    assert len(models_after_second_run) == 2

    for model in models_after_second_run:
        assert model.backend_name == "docling"
        assert model.backend_config == {}