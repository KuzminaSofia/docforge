from __future__ import annotations

import pytest

from technical_document_ml_service.inference.backends._artifact_io import sanitize_stem


@pytest.mark.parametrize(
    "filename, expected",
    [
        # кириллица транслитерируется, а не срезается до ASCII-хвоста
        ("Кузьмина Софья-3.pdf", "Kuzmina_Sofya-3"),
        ("Документ 1.pdf", "Dokument_1"),
        ("Спецификация.docx", "Spetsifikatsiya"),
        # ASCII-имена не меняются
        ("sample.pdf", "sample"),
        ("my-doc_v2.pdf", "my-doc_v2"),
        # вырожденные имена дают безопасный fallback
        ("___.pdf", "document"),
        ("", "document"),
    ],
)
def test_sanitize_stem(filename: str, expected: str) -> None:
    assert sanitize_stem(filename) == expected
