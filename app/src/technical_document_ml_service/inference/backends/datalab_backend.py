from __future__ import annotations

import base64
import binascii
import logging
import mimetypes
import re
import shutil
import time
from pathlib import Path
from typing import Any

from technical_document_ml_service.inference.backends._artifact_io import (
    sanitize_stem as _sanitize_stem,
    save_json as _save_json,
)
from technical_document_ml_service.inference.backends._secrets import resolve_api_key
from technical_document_ml_service.inference.backends.base import PredictionBackend
from technical_document_ml_service.inference.contracts import (
    BackendArtifact,
    BackendDocument,
    BackendRequest,
    BackendResult,
)
from technical_document_ml_service.inference.exceptions import (
    BackendExecutionError,
    InvalidBackendConfigurationError,
)


LOGGER = logging.getLogger("technical_document_ml_service.datalab_backend")

# дефолты, специфичные для Datalab. Живут в самом бэкенде, а не в общем config.py,
# чтобы core/config оставался провайдер-агностичным.
_DEFAULT_API_BASE = "https://www.datalab.to/api/v1"
_DEFAULT_API_KEY_ENV = "APP_DATALAB_API_KEY"

# режимы качества/скорости обработки на стороне Datalab
_VALID_MODES = ("fast", "balanced", "accurate")
_DEFAULT_MODE = "fast"

# опрос результата: запрос выполняется асинхронно на стороне сервиса
_DEFAULT_POLL_INTERVAL_S = 3
_DEFAULT_POLL_TIMEOUT_S = 600
_DEFAULT_SUBMIT_TIMEOUT_S = 120


def _load_requests():
    """лениво загрузить requests, чтобы app-контейнер не требовал зависимость"""
    import requests

    return requests


def _safe_image_name(name: str) -> str:
    """нормализовать имя извлеченного изображения, отбросив сегменты пути (anti-traversal)"""
    leaf = name.replace("\\", "/").rsplit("/", 1)[-1]
    normalized = re.sub(r"[^A-Za-z0-9._-]+", "_", leaf).strip("._")
    return normalized or "image"


class DatalabClient:
    """тонкий HTTP-клиент Datalab convert API (submit + poll)"""

    def __init__(
        self,
        *,
        api_key: str,
        api_base: str,
        poll_interval_s: int = _DEFAULT_POLL_INTERVAL_S,
        poll_timeout_s: int = _DEFAULT_POLL_TIMEOUT_S,
        submit_timeout_s: int = _DEFAULT_SUBMIT_TIMEOUT_S,
    ) -> None:
        self._api_key = api_key
        self._convert_url = f"{api_base.rstrip('/')}/convert"
        self._poll_interval_s = poll_interval_s
        self._poll_timeout_s = poll_timeout_s
        self._submit_timeout_s = submit_timeout_s

    @property
    def _headers(self) -> dict[str, str]:
        return {"X-API-Key": self._api_key}

    @staticmethod
    def _check_status(response: Any, *, action: str) -> None:
        """проверить HTTP-статус и поднять ошибку с телом ответа Datalab

        Datalab кладет причину (невалидный параметр, лимит плана и т.п.) в тело
        ответа. requests.raise_for_status() его теряет — поэтому разбираем сами.
        """
        status_code = getattr(response, "status_code", None)
        if status_code is None or status_code < 400:
            return

        detail = ""
        try:
            payload = response.json()
            detail = payload.get("error") or payload.get("detail") or str(payload)
        except Exception:
            detail = (getattr(response, "text", "") or "").strip()

        raise BackendExecutionError(
            f"Datalab {action}: HTTP {status_code}. {detail}".strip()
        )

    def submit(
        self,
        *,
        file_path: Path,
        options: dict[str, Any],
        content_type: str | None = None,
    ) -> str:
        """запустить конвертацию и вернуть request_check_url для опроса"""
        requests = _load_requests()
        data = {k: v for k, v in options.items() if v is not None}

        # Datalab определяет тип файла по Content-Type части multipart, а не по
        # расширению. Без явного типа requests шлет application/octet-stream и API
        # отвечает 400 "Invalid file type". Берем mime из документа, иначе угадываем.
        effective_type = (
            content_type
            or mimetypes.guess_type(file_path.name)[0]
            or "application/octet-stream"
        )

        with file_path.open("rb") as fh:
            files = {"file": (file_path.name, fh, effective_type)}
            response = requests.post(
                self._convert_url,
                headers=self._headers,
                data=data,
                files=files,
                timeout=self._submit_timeout_s,
            )

        self._check_status(response, action="отклонил запрос (submit)")
        body = response.json()
        if not body.get("success"):
            raise BackendExecutionError(
                f"Datalab отклонил запрос: {body.get('error') or 'unknown error'}"
            )

        check_url = body.get("request_check_url")
        if not check_url:
            raise BackendExecutionError(
                "Datalab не вернул request_check_url в ответе на submit."
            )
        return check_url

    def poll(self, check_url: str) -> dict[str, Any]:
        """опрашивать до завершения конвертации, вернуть финальный JSON результата"""
        requests = _load_requests()
        deadline = time.monotonic() + self._poll_timeout_s

        while True:
            response = requests.get(
                check_url,
                headers=self._headers,
                timeout=self._submit_timeout_s,
            )
            self._check_status(response, action="ошибка при опросе результата (poll)")
            body = response.json()
            status = body.get("status")

            if status == "complete":
                if not body.get("success"):
                    raise BackendExecutionError(
                        f"Datalab завершил конвертацию с ошибкой: "
                        f"{body.get('error') or 'unknown error'}"
                    )
                return body

            if time.monotonic() > deadline:
                raise BackendExecutionError(
                    f"Datalab не завершил обработку за {self._poll_timeout_s}s "
                    f"(последний статус: {status})."
                )

            time.sleep(self._poll_interval_s)

    def convert(
        self,
        *,
        file_path: Path,
        options: dict[str, Any],
        content_type: str | None = None,
    ) -> dict[str, Any]:
        """полный цикл: submit -> poll -> результат"""
        check_url = self.submit(
            file_path=file_path, options=options, content_type=content_type
        )
        return self.poll(check_url)


def _decode_images(
    images: dict[str, Any],
    images_dir: Path,
) -> list[tuple[str, Path]]:
    """декодировать base64-изображения на диск; вернуть [(orig_name, saved_path)]"""
    saved: list[tuple[str, Path]] = []
    if not images:
        return saved

    images_dir.mkdir(parents=True, exist_ok=True)
    for original_name, b64 in images.items():
        if not isinstance(b64, str):
            continue
        try:
            raw = base64.b64decode(b64)
        except (binascii.Error, ValueError):
            LOGGER.warning("Не удалось декодировать изображение '%s'", original_name)
            continue
        target = images_dir / _safe_image_name(original_name)
        target.write_bytes(raw)
        saved.append((original_name, target))
    return saved


class DatalabBackend(PredictionBackend):
    """backend обработки на основе Datalab convert API"""

    backend_name = "datalab"

    def _resolve_api_key(self) -> str | None:
        """разрешить ключ: config.api_key -> env по config.api_key_env -> env по умолчанию"""
        return resolve_api_key(self.config, default_env=_DEFAULT_API_KEY_ENV)

    def _resolve_mode(self) -> str:
        mode = str(self.config.get("mode") or _DEFAULT_MODE).strip().lower()
        if mode not in _VALID_MODES:
            raise InvalidBackendConfigurationError(
                f"Недопустимый mode='{mode}' для Datalab. "
                f"Разрешены: {', '.join(_VALID_MODES)}."
            )
        return mode

    def _is_stub_fallback_allowed(self) -> bool:
        """разрешен ли явный fallback на stub-режим (без обращения к API)"""
        return bool(self.config.get("allow_stub_fallback", False))

    def _build_options(self) -> dict[str, Any]:
        """собрать опции конвертации из config модели"""
        config = self.config
        disable_images = bool(config.get("disable_image_extraction", False))
        return {
            "mode": self._resolve_mode(),
            "output_format": "markdown",
            "max_pages": config.get("max_pages"),
            "page_range": config.get("page_range"),
            "disable_image_extraction": True if disable_images else None,
        }

    def _int_config(self, key: str, default: int) -> int:
        """прочитать целочисленную опцию из config с понятной ошибкой при мусоре"""
        raw = self.config.get(key, default)
        try:
            return int(raw)
        except (TypeError, ValueError) as exc:
            raise InvalidBackendConfigurationError(
                f"Опция '{key}' для Datalab должна быть целым числом, получено: {raw!r}."
            ) from exc

    def _build_client(self, api_key: str) -> DatalabClient:
        config = self.config
        return DatalabClient(
            api_key=api_key,
            api_base=str(config.get("api_base") or _DEFAULT_API_BASE),
            poll_interval_s=self._int_config("poll_interval_s", _DEFAULT_POLL_INTERVAL_S),
            poll_timeout_s=self._int_config("poll_timeout_s", _DEFAULT_POLL_TIMEOUT_S),
            submit_timeout_s=self._int_config("submit_timeout_s", _DEFAULT_SUBMIT_TIMEOUT_S),
        )

    def process(self, request: BackendRequest) -> BackendResult:
        """выполнить обработку через Datalab convert API"""
        task_artifacts_dir = Path(request.artifacts_dir)
        task_artifacts_dir.mkdir(parents=True, exist_ok=True)

        try:
            client, mode_label, warnings = self._init_client(request)
            options = self._build_options()

            artifacts: list[BackendArtifact] = []
            extracted_data: dict[str, Any] = {}
            documents_summary: list[dict[str, Any]] = []

            for index, document in enumerate(request.documents, start=1):
                doc_artifacts, extracted_entry, summary_entry = self._process_document(
                    index, document, task_artifacts_dir, request, client, options
                )
                artifacts.extend(doc_artifacts)
                extracted_data[document.original_filename] = extracted_entry
                documents_summary.append(summary_entry)

            task_summary_path = task_artifacts_dir / "task.summary.json"
            task_artifact = self._save_task_summary(
                task_summary_path, request, mode_label, options, warnings, documents_summary
            )
            artifacts.append(task_artifact)

            return BackendResult(
                extracted_data=extracted_data,
                output_path=str(task_summary_path),
                artifacts=artifacts,
                warnings=warnings,
                metadata={
                    "backend": self.name,
                    "mode": mode_label,
                    "datalab_mode": options["mode"],
                    "artifacts_count": len(artifacts),
                    "task_summary_path": str(task_summary_path),
                },
            )

        except Exception:
            shutil.rmtree(task_artifacts_dir, ignore_errors=True)
            raise

    def _init_client(
        self, request: BackendRequest
    ) -> tuple[DatalabClient | None, str, list[str]]:
        """создать клиент Datalab; вернуть (client | None, mode_label, warnings)"""
        warnings: list[str] = []
        api_key = self._resolve_api_key()

        if api_key:
            return self._build_client(api_key), "datalab", warnings

        if not self._is_stub_fallback_allowed():
            raise BackendExecutionError(
                f"Не задан Datalab API key. Задайте env {_DEFAULT_API_KEY_ENV} "
                "(или config.api_key_env / config.api_key). Stub fallback отключен."
            )

        warning_message = (
            "Datalab API key не задан. Использован разрешенный stub fallback."
        )
        warnings.append(warning_message)
        LOGGER.warning(
            "task_id=%s | backend=%s | %s", request.task_id, self.name, warning_message
        )
        return None, "stub_fallback", warnings

    def _process_document(
        self,
        index: int,
        document: BackendDocument,
        task_artifacts_dir: Path,
        request: BackendRequest,
        client: DatalabClient | None,
        options: dict[str, Any],
    ) -> tuple[list[BackendArtifact], dict[str, Any], dict[str, Any]]:
        """обработать один документ; вернуть (artifacts, extracted_entry, summary_entry)"""
        safe_stem = _sanitize_stem(document.original_filename)
        doc_dir = (
            task_artifacts_dir
            / f"{index:02d}_{safe_stem}_{str(document.document_id)[:8]}"
        )
        doc_dir.mkdir(parents=True, exist_ok=True)

        markdown, raw_result, mode = self._convert_document(client, document, options)

        return self._materialize_document_outputs(
            doc_dir=doc_dir,
            safe_stem=safe_stem,
            markdown=markdown,
            raw_result=raw_result,
            document=document,
            request=request,
            mode=mode,
        )

    def _convert_document(
        self,
        client: DatalabClient | None,
        document: BackendDocument,
        options: dict[str, Any],
    ) -> tuple[str, dict[str, Any], str]:
        """вызвать Datalab или stub; вернуть (markdown, raw_result, mode)"""
        if client is None:
            stub_md = (
                f"# {document.original_filename}\n\n"
                "Datalab API key недоступен в текущем окружении. "
                "Сформирован stub-результат."
            )
            stub_result = {
                "status": "complete",
                "success": True,
                "markdown": stub_md,
                "images": {},
                "page_count": 0,
                "mode": "stub_fallback",
            }
            return stub_md, stub_result, "stub_fallback"

        try:
            result = client.convert(
                file_path=document.path,
                options=options,
                content_type=document.mime_type or None,
            )
        except BackendExecutionError:
            raise
        except Exception as exc:
            raise BackendExecutionError(
                f"Ошибка Datalab при обработке файла '{document.original_filename}': {exc}"
            ) from exc

        markdown = result.get("markdown") or ""
        return markdown, result, "datalab"

    def _materialize_document_outputs(
        self,
        *,
        doc_dir: Path,
        safe_stem: str,
        markdown: str,
        raw_result: dict[str, Any],
        document: BackendDocument,
        request: BackendRequest,
        mode: str,
    ) -> tuple[list[BackendArtifact], dict[str, Any], dict[str, Any]]:
        """сохранить файлы (md/json/изображения/summary) и собрать артефакты"""
        md_path = doc_dir / f"{safe_stem}.datalab.md"
        json_path = doc_dir / f"{safe_stem}.datalab.json"
        summary_path = doc_dir / f"{safe_stem}.summary.json"

        md_path.write_text(markdown, encoding="utf-8")

        images = raw_result.get("images") if isinstance(raw_result, dict) else None
        saved_images = _decode_images(images or {}, doc_dir / "images")

        # в JSON-результат не кладем base64 изображений: они уже выгружены как файлы
        result_without_images = {
            k: v for k, v in raw_result.items() if k != "images"
        }
        result_without_images["image_names"] = [name for name, _ in saved_images]
        _save_json(json_path, result_without_images)

        page_count = raw_result.get("page_count") if isinstance(raw_result, dict) else None

        common_meta = {
            "document_id": str(document.document_id),
            "original_filename": document.original_filename,
            "mode": mode,
        }

        artifacts: list[BackendArtifact] = [
            BackendArtifact(
                name=md_path.name,
                path=str(md_path),
                kind="markdown",
                mime_type="text/markdown",
                description="Экспорт распознанного документа в Markdown (Datalab)",
                metadata=common_meta,
            ),
            BackendArtifact(
                name=json_path.name,
                path=str(json_path),
                kind="datalab_json",
                mime_type="application/json",
                description="Полный ответ Datalab convert API (без base64 изображений)",
                metadata=common_meta,
            ),
        ]

        for original_name, image_path in saved_images:
            mime_type = mimetypes.guess_type(image_path.name)[0]
            artifacts.append(
                BackendArtifact(
                    name=f"{safe_stem}__{image_path.name}",
                    path=str(image_path),
                    kind="image",
                    mime_type=mime_type,
                    description="Изображение, извлеченное из документа",
                    metadata={**common_meta, "source_name": original_name},
                )
            )

        summary = {
            "document_id": str(document.document_id),
            "input_file": str(document.path),
            "original_filename": document.original_filename,
            "markdown_file": str(md_path),
            "json_file": str(json_path),
            "images_count": len(saved_images),
            "page_count": page_count,
            "status": "success",
            "backend": self.name,
            "mode": mode,
        }
        _save_json(summary_path, summary)
        artifacts.append(
            BackendArtifact(
                name=summary_path.name,
                path=str(summary_path),
                kind="document_summary",
                mime_type="application/json",
                description="Сводка по обработке одного документа",
                metadata=common_meta,
            )
        )

        extracted_entry = {
            "document_id": str(document.document_id),
            "document_type": document.document_type,
            "target_schema": request.target_schema,
            "status": "processed",
            "backend": self.name,
            "mode": mode,
            "page_count": page_count,
            "images_count": len(saved_images),
            "artifacts": {
                "markdown_path": str(md_path),
                "json_path": str(json_path),
                "summary_path": str(summary_path),
            },
        }

        summary_entry = {
            "document_id": str(document.document_id),
            "original_filename": document.original_filename,
            "status": "success",
            "mode": mode,
            "page_count": page_count,
            "images_count": len(saved_images),
            "summary_path": str(summary_path),
        }

        return artifacts, extracted_entry, summary_entry

    def _save_task_summary(
        self,
        task_summary_path: Path,
        request: BackendRequest,
        mode_label: str,
        options: dict[str, Any],
        warnings: list[str],
        documents_summary: list[dict[str, Any]],
    ) -> BackendArtifact:
        """сохранить сводку задачи и вернуть artifact"""
        _save_json(
            task_summary_path,
            {
                "task_id": str(request.task_id),
                "user_id": str(request.user_id),
                "model_id": str(request.model_id),
                "model_name": request.model_name,
                "backend": self.name,
                "mode": mode_label,
                "datalab_mode": options["mode"],
                "documents_count": len(request.documents),
                "warnings": warnings,
                "documents": documents_summary,
            },
        )
        return BackendArtifact(
            name=task_summary_path.name,
            path=str(task_summary_path),
            kind="task_summary",
            mime_type="application/json",
            description="Сводка по обработке всей задачи",
            metadata={
                "task_id": str(request.task_id),
                "backend": self.name,
                "mode": mode_label,
            },
        )


def create_datalab_backend(
    config: dict | None = None,
) -> PredictionBackend:
    """фабрика backend-а Datalab"""
    return DatalabBackend(config=config)
