from __future__ import annotations

import io

import pytest

from technical_document_ml_service.storage import (
    ObjectNotFoundError,
    get_object_storage,
)


def test_filesystem_storage_roundtrip(tmp_path) -> None:
    """upload -> exists -> get_bytes -> stream -> download -> delete"""
    storage = get_object_storage()
    key = "uploads/owner/doc.bin"
    payload = b"hello object storage" * 1000

    storage.upload_fileobj(io.BytesIO(payload), key, content_type="application/octet-stream")

    assert storage.exists(key) is True
    assert storage.get_bytes(key) == payload

    stream = storage.open_stream(key)
    assert stream.content_length == len(payload)
    assert b"".join(stream.chunks) == payload

    destination = tmp_path / "downloaded.bin"
    storage.download_file(key, destination)
    assert destination.read_bytes() == payload

    storage.delete([key])
    assert storage.exists(key) is False


def test_filesystem_storage_missing_key_raises(tmp_path) -> None:
    storage = get_object_storage()

    with pytest.raises(ObjectNotFoundError):
        storage.open_stream("artifacts/missing/none.json")

    with pytest.raises(ObjectNotFoundError):
        storage.download_file("artifacts/missing/none.json", tmp_path / "x")


def test_filesystem_storage_rejects_path_traversal_key() -> None:
    storage = get_object_storage()

    with pytest.raises(Exception):
        storage.upload_fileobj(io.BytesIO(b"x"), "../../escape.bin")


def test_upload_file_from_local_path(tmp_path) -> None:
    storage = get_object_storage()
    source = tmp_path / "source.txt"
    source.write_text("artifact body", encoding="utf-8")

    storage.upload_file(source, "artifacts/task/source.txt", content_type="text/plain")

    assert storage.get_bytes("artifacts/task/source.txt") == b"artifact body"
