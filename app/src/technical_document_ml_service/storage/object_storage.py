"""Абстракция object storage.

ML-сервис хранит входные документы и артефакты обработки во внешнем S3-совместимом
хранилище, чтобы `app` и воркеры были stateless и могли масштабироваться на разные хосты.

Слой спроектирован как Strategy:
- :class:`S3ObjectStorage` — боевая реализация поверх boto3 (MinIO локально, реальный S3 в проде);
- :class:`FilesystemObjectStorage` — реализация для тестов, хранит объекты под локальным каталогом.

Все остальные модули зависят только от интерфейса :class:`ObjectStorage` и получают
конкретную реализацию через :func:`get_object_storage`.
"""

from __future__ import annotations

import logging
import shutil
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import IO, Any, Iterable, Iterator, Protocol, runtime_checkable

from technical_document_ml_service.core.config import app_settings

LOGGER = logging.getLogger("technical_document_ml_service.storage")

_STREAM_CHUNK_BYTES = 64 * 1024


class ObjectStorageError(Exception):
    """базовая ошибка слоя object storage"""


class ObjectNotFoundError(ObjectStorageError):
    """объект с указанным ключом не найден в хранилище"""


@dataclass(frozen=True, slots=True)
class ObjectStream:
    """потоковое тело объекта вместе с метаданными для отдачи клиенту"""

    chunks: Iterator[bytes]
    content_length: int | None
    content_type: str | None


@runtime_checkable
class ObjectStorage(Protocol):
    """контракт хранилища объектов (ключ -> содержимое)"""

    def upload_fileobj(self, fileobj: IO[bytes], key: str, *, content_type: str | None = None) -> None:
        """потоково загрузить содержимое file-like объекта под ключом"""
        ...

    def upload_file(self, source: Path, key: str, *, content_type: str | None = None) -> None:
        """загрузить локальный файл под ключом"""
        ...

    def download_file(self, key: str, destination: Path) -> None:
        """скачать объект по ключу в локальный файл"""
        ...

    def open_stream(self, key: str) -> ObjectStream:
        """открыть потоковое чтение объекта (для отдачи клиенту)"""
        ...

    def get_bytes(self, key: str) -> bytes:
        """прочитать объект целиком в память (для небольших файлов)"""
        ...

    def delete(self, keys: Iterable[str]) -> None:
        """удалить объекты по ключам (отсутствующие игнорируются)"""
        ...

    def exists(self, key: str) -> bool:
        """проверить наличие объекта по ключу"""
        ...

    def generate_presigned_url(self, key: str, *, expires_in: int = 3600) -> str:
        """сгенерировать временную ссылку на объект"""
        ...


class S3ObjectStorage:
    """реализация object storage поверх boto3 (S3 / MinIO)"""

    def __init__(
        self,
        *,
        endpoint_url: str,
        bucket: str,
        access_key: str,
        secret_key: str,
        region: str,
        use_ssl: bool,
    ) -> None:
        import boto3
        from botocore.config import Config

        self._bucket = bucket
        self._client = boto3.client(
            "s3",
            endpoint_url=endpoint_url,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            region_name=region,
            use_ssl=use_ssl,
            # path-style адресация обязательна для MinIO и совместима с S3
            config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
        )

    def upload_fileobj(self, fileobj: IO[bytes], key: str, *, content_type: str | None = None) -> None:
        extra_args = {"ContentType": content_type} if content_type else None
        self._client.upload_fileobj(fileobj, self._bucket, key, ExtraArgs=extra_args)

    def upload_file(self, source: Path, key: str, *, content_type: str | None = None) -> None:
        extra_args = {"ContentType": content_type} if content_type else None
        self._client.upload_file(str(source), self._bucket, key, ExtraArgs=extra_args)

    def download_file(self, key: str, destination: Path) -> None:
        destination.parent.mkdir(parents=True, exist_ok=True)
        try:
            self._client.download_file(self._bucket, key, str(destination))
        except Exception as exc:  # botocore ClientError 404 и пр.
            if _is_not_found(exc):
                raise ObjectNotFoundError(key) from exc
            raise ObjectStorageError(str(exc)) from exc

    def open_stream(self, key: str) -> ObjectStream:
        try:
            response = self._client.get_object(Bucket=self._bucket, Key=key)
        except Exception as exc:
            if _is_not_found(exc):
                raise ObjectNotFoundError(key) from exc
            raise ObjectStorageError(str(exc)) from exc

        return ObjectStream(
            chunks=_iter_s3_body(response["Body"]),
            content_length=response.get("ContentLength"),
            content_type=response.get("ContentType"),
        )

    def get_bytes(self, key: str) -> bytes:
        try:
            response = self._client.get_object(Bucket=self._bucket, Key=key)
        except Exception as exc:
            if _is_not_found(exc):
                raise ObjectNotFoundError(key) from exc
            raise ObjectStorageError(str(exc)) from exc
        body = response["Body"]
        try:
            return body.read()
        finally:
            body.close()

    def delete(self, keys: Iterable[str]) -> None:
        objects = [{"Key": key} for key in keys]
        if not objects:
            return
        try:
            self._client.delete_objects(Bucket=self._bucket, Delete={"Objects": objects})
        except Exception:
            LOGGER.exception("Не удалось удалить объекты из S3: %s", [o["Key"] for o in objects])

    def exists(self, key: str) -> bool:
        try:
            self._client.head_object(Bucket=self._bucket, Key=key)
            return True
        except Exception as exc:
            if _is_not_found(exc):
                return False
            raise ObjectStorageError(str(exc)) from exc

    def generate_presigned_url(self, key: str, *, expires_in: int = 3600) -> str:
        return self._client.generate_presigned_url(
            "get_object",
            Params={"Bucket": self._bucket, "Key": key},
            ExpiresIn=expires_in,
        )


def _iter_s3_body(body: Any) -> Iterator[bytes]:
    """стримить тело S3-объекта, гарантированно закрывая коннект по завершении/разрыву

    Без этого при отключении клиента посреди скачивания соединение к S3 не вернётся
    в пул (StreamingResponse закрывает генератор -> срабатывает finally).
    """
    try:
        yield from body.iter_chunks(_STREAM_CHUNK_BYTES)
    finally:
        body.close()


def _is_not_found(exc: Exception) -> bool:
    """определить, является ли ошибка botocore «объект не найден»"""
    response = getattr(exc, "response", None)
    if not isinstance(response, dict):
        return False
    code = str(response.get("Error", {}).get("Code", ""))
    status = response.get("ResponseMetadata", {}).get("HTTPStatusCode")
    return code in {"404", "NoSuchKey", "NotFound"} or status == 404


class FilesystemObjectStorage:
    """реализация object storage поверх локальной ФС (для тестов/dev)

    Ключи интерпретируются как относительные пути под `root`.
    """

    def __init__(self, root: Path) -> None:
        self._root = root

    def _path_for(self, key: str) -> Path:
        # ключи всегда относительные (uploads/..., artifacts/...); защита от выхода за root
        candidate = (self._root / key).resolve()
        root = self._root.resolve()
        if not candidate.is_relative_to(root):
            raise ObjectStorageError(f"Недопустимый ключ объекта: {key!r}")
        return candidate

    def upload_fileobj(self, fileobj: IO[bytes], key: str, *, content_type: str | None = None) -> None:
        destination = self._path_for(key)
        destination.parent.mkdir(parents=True, exist_ok=True)
        with destination.open("wb") as target:
            shutil.copyfileobj(fileobj, target, _STREAM_CHUNK_BYTES)

    def upload_file(self, source: Path, key: str, *, content_type: str | None = None) -> None:
        destination = self._path_for(key)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)

    def download_file(self, key: str, destination: Path) -> None:
        source = self._path_for(key)
        if not source.is_file():
            raise ObjectNotFoundError(key)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)

    def open_stream(self, key: str) -> ObjectStream:
        source = self._path_for(key)
        if not source.is_file():
            raise ObjectNotFoundError(key)
        content_length = source.stat().st_size
        return ObjectStream(
            chunks=_iter_file_chunks(source),
            content_length=content_length,
            content_type=None,
        )

    def get_bytes(self, key: str) -> bytes:
        source = self._path_for(key)
        if not source.is_file():
            raise ObjectNotFoundError(key)
        return source.read_bytes()

    def delete(self, keys: Iterable[str]) -> None:
        for key in keys:
            try:
                self._path_for(key).unlink(missing_ok=True)
            except OSError:
                continue

    def exists(self, key: str) -> bool:
        return self._path_for(key).is_file()

    def generate_presigned_url(self, key: str, *, expires_in: int = 3600) -> str:
        return self._path_for(key).as_uri()


def _iter_file_chunks(path: Path) -> Iterator[bytes]:
    """потоково читать файл чанками"""
    with path.open("rb") as source:
        while chunk := source.read(_STREAM_CHUNK_BYTES):
            yield chunk


_instance: ObjectStorage | None = None
_instance_lock = threading.Lock()


def _build_object_storage() -> ObjectStorage:
    """собрать реализацию хранилища по текущим настройкам приложения"""
    backend = app_settings.storage_backend.strip().lower()
    if backend == "filesystem":
        return FilesystemObjectStorage(root=Path(app_settings.storage_filesystem_root))
    if backend == "s3":
        return S3ObjectStorage(
            endpoint_url=app_settings.s3_endpoint_url,
            bucket=app_settings.s3_bucket,
            access_key=app_settings.s3_access_key,
            secret_key=app_settings.s3_secret_key,
            region=app_settings.s3_region,
            use_ssl=app_settings.s3_use_ssl,
        )
    raise ObjectStorageError(f"Неизвестный storage backend: {app_settings.storage_backend!r}")


def get_object_storage() -> ObjectStorage:
    """вернуть процесс-синглтон object storage"""
    global _instance
    if _instance is None:
        with _instance_lock:
            if _instance is None:
                _instance = _build_object_storage()
    return _instance


def reset_object_storage() -> None:
    """сбросить кэшированный синглтон (используется тестами при подмене настроек)"""
    global _instance
    with _instance_lock:
        _instance = None
