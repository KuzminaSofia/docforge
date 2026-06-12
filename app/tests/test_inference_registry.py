from __future__ import annotations

import pytest

from technical_document_ml_service.inference.exceptions import BackendNotFoundError
from technical_document_ml_service.inference.registry import build_default_backend_registry
from technical_document_ml_service.inference.selector import select_prediction_backend


def test_default_backend_registry_contains_docling_and_datalab() -> None:
    registry = build_default_backend_registry()

    assert registry.names() == ("datalab", "docling")


def test_select_prediction_backend_resolves_datalab() -> None:
    registry = build_default_backend_registry()

    selection = select_prediction_backend(
        requested_backend_name="datalab",
        backend_config={"mode": "fast"},
        registry=registry,
        default_backend_name="docling",
    )

    assert selection.resolved_backend_name == "datalab"
    assert selection.backend.name == "datalab"


def test_select_prediction_backend_uses_docling_by_default() -> None:
    registry = build_default_backend_registry()

    selection = select_prediction_backend(
        requested_backend_name=None,
        backend_config={"batch_size": 4},
        registry=registry,
        default_backend_name="docling",
    )

    assert selection.requested_backend_name is None
    assert selection.resolved_backend_name == "docling"
    assert selection.backend.name == "docling"
    assert selection.backend.config == {"batch_size": 4}


def test_registry_raises_for_unknown_backend() -> None:
    registry = build_default_backend_registry()

    with pytest.raises(BackendNotFoundError):
        registry.create(name="unknown-backend")