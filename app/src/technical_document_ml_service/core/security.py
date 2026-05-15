from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import time
from datetime import timedelta
from typing import Any
from uuid import UUID

from technical_document_ml_service.domain.exceptions import AuthenticationError


JWT_SECRET_ENV = "APP_JWT_SECRET_KEY"
JWT_EXPIRE_MINUTES_ENV = "APP_JWT_EXPIRE_MINUTES"
AUTH_COOKIE_NAME_ENV = "APP_AUTH_COOKIE_NAME"
AUTH_COOKIE_SECURE_ENV = "APP_AUTH_COOKIE_SECURE"

PASSWORD_PBKDF2_ITERATIONS_ENV = "APP_PASSWORD_PBKDF2_ITERATIONS"
PASSWORD_SALT_BYTES_ENV = "APP_PASSWORD_SALT_BYTES"

PASSWORD_SCHEME_PBKDF2_SHA256 = "pbkdf2_sha256"
_RESERVED_JWT_CLAIMS = {"sub", "user_id", "iat", "exp", "iss", "aud"}
JWT_ISSUER = "technical-document-ml-service"
JWT_AUDIENCE = "technical-document-ml-service"
_MIN_JWT_SECRET_LEN = 32
_KNOWN_WEAK_SECRETS = frozenset({
    "change-me-in-production",
    "super-secret-key-change-me",
    "secret",
    "password",
    "jwt-secret",
})


def _b64url_encode(data: bytes) -> str:
    """закодировать bytes в base64url без padding"""
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(data: str) -> bytes:
    """декодировать base64url строку с восстановлением padding"""
    padding = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(data + padding)


def get_password_pbkdf2_iterations() -> int:
    """получить число итераций PBKDF2 из окружения"""
    raw_value = os.getenv(PASSWORD_PBKDF2_ITERATIONS_ENV, "600000")
    try:
        value = int(raw_value)
    except ValueError as exc:
        raise RuntimeError(
            f"Некорректное значение {PASSWORD_PBKDF2_ITERATIONS_ENV}: {raw_value!r}"
        ) from exc

    if value <= 0:
        raise RuntimeError(
            f"{PASSWORD_PBKDF2_ITERATIONS_ENV} должен быть положительным числом."
        )

    return value


def get_password_salt_bytes() -> int:
    """получить размер соли в байтах"""
    raw_value = os.getenv(PASSWORD_SALT_BYTES_ENV, "16")
    try:
        value = int(raw_value)
    except ValueError as exc:
        raise RuntimeError(
            f"Некорректное значение {PASSWORD_SALT_BYTES_ENV}: {raw_value!r}"
        ) from exc

    if value < 16:
        raise RuntimeError(
            f"{PASSWORD_SALT_BYTES_ENV} должен быть не меньше 16."
        )

    return value


def hash_password(raw_password: str) -> str:
    """
    получить строку-хэш пароля в формате:

    pbkdf2_sha256$<iterations>$<salt_b64url>$<hash_b64url>
    """
    salt = secrets.token_bytes(get_password_salt_bytes())
    iterations = get_password_pbkdf2_iterations()

    derived_key = hashlib.pbkdf2_hmac(
        "sha256",
        raw_password.encode("utf-8"),
        salt,
        iterations,
    )

    salt_encoded = _b64url_encode(salt)
    hash_encoded = _b64url_encode(derived_key)

    return (
        f"{PASSWORD_SCHEME_PBKDF2_SHA256}"
        f"${iterations}"
        f"${salt_encoded}"
        f"${hash_encoded}"
    )


def verify_password(raw_password: str, password_hash: str) -> bool:
    """
    проверить соответствие пароля его хэшу

    Ожидаемый формат password_hash:
    pbkdf2_sha256$<iterations>$<salt_b64url>$<hash_b64url>
    """
    try:
        scheme, iterations_raw, salt_encoded, expected_hash_encoded = password_hash.split(
            "$", 3
        )
    except ValueError:
        return False

    if scheme != PASSWORD_SCHEME_PBKDF2_SHA256:
        return False

    try:
        iterations = int(iterations_raw)
        salt = _b64url_decode(salt_encoded)
        expected_hash = _b64url_decode(expected_hash_encoded)
    except (ValueError, TypeError):
        return False

    if iterations <= 0:
        return False

    candidate_hash = hashlib.pbkdf2_hmac(
        "sha256",
        raw_password.encode("utf-8"),
        salt,
        iterations,
    )

    return secrets.compare_digest(candidate_hash, expected_hash)


def get_jwt_secret_key() -> str:
    """получить секрет для подписи JWT-токенов"""
    secret = os.getenv(JWT_SECRET_ENV, "")
    if not secret:
        raise RuntimeError(
            f"Необходимо задать переменную окружения {JWT_SECRET_ENV}."
        )
    if secret in _KNOWN_WEAK_SECRETS:
        raise RuntimeError(
            f"{JWT_SECRET_ENV} содержит небезопасное значение по умолчанию. "
            "Задайте случайный секрет длиной не менее 32 символов."
        )
    if len(secret) < _MIN_JWT_SECRET_LEN:
        raise RuntimeError(
            f"{JWT_SECRET_ENV} должен быть длиной не менее {_MIN_JWT_SECRET_LEN} символов."
        )
    return secret


def get_jwt_expire_minutes() -> int:
    """получить срок жизни access token в минутах"""
    raw_value = os.getenv(JWT_EXPIRE_MINUTES_ENV, "60")
    try:
        value = int(raw_value)
    except ValueError as exc:
        raise RuntimeError(
            f"Некорректное значение {JWT_EXPIRE_MINUTES_ENV}: {raw_value!r}"
        ) from exc

    if value <= 0:
        raise RuntimeError(
            f"{JWT_EXPIRE_MINUTES_ENV} должен быть положительным числом."
        )

    return value


def get_auth_cookie_name() -> str:
    """получить имя cookie для access token"""
    return os.getenv(AUTH_COOKIE_NAME_ENV, "tdms_access_token")


def is_auth_cookie_secure() -> bool:
    """нужно ли ставить cookie только по HTTPS"""
    raw_value = os.getenv(AUTH_COOKIE_SECURE_ENV, "false").strip().lower()
    return raw_value in {"1", "true", "yes", "on"}


def create_access_token(
    *,
    user_id: UUID | str,
    email: str,
    expires_delta: timedelta | None = None,
    extra_claims: dict[str, Any] | None = None,
) -> str:
    """
    создать JWT access token с подписью HS256

    payload содержит:
    - sub: email пользователя
    - user_id: идентификатор пользователя (как строка)
    - iat: время выпуска токена
    - exp: время истечения токена
    """
    now = int(time.time())
    ttl = expires_delta or timedelta(minutes=get_jwt_expire_minutes())
    expires_at = now + int(ttl.total_seconds())

    if extra_claims:
        reserved_keys = _RESERVED_JWT_CLAIMS.intersection(extra_claims.keys())
        if reserved_keys:
            reserved_keys_str = ", ".join(sorted(reserved_keys))
            raise ValueError(
                "extra_claims содержит зарезервированные JWT-поля: "
                f"{reserved_keys_str}"
            )

    header = {
        "alg": "HS256",
        "typ": "JWT",
    }

    payload: dict[str, Any] = {}
    if extra_claims:
        payload.update(extra_claims)

    payload.update(
        {
            "iss": JWT_ISSUER,
            "aud": JWT_AUDIENCE,
            "sub": email,
            "user_id": str(user_id),
            "iat": now,
            "exp": expires_at,
        }
    )

    header_bytes = json.dumps(
        header,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    payload_bytes = json.dumps(
        payload,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")

    encoded_header = _b64url_encode(header_bytes)
    encoded_payload = _b64url_encode(payload_bytes)
    signing_input = f"{encoded_header}.{encoded_payload}".encode("ascii")

    signature = hmac.new(
        get_jwt_secret_key().encode("utf-8"),
        signing_input,
        hashlib.sha256,
    ).digest()

    encoded_signature = _b64url_encode(signature)
    return f"{encoded_header}.{encoded_payload}.{encoded_signature}"


def build_access_token(user_id: UUID, email: str) -> tuple[str, int]:
    """создать access token и вернуть его вместе со сроком жизни в секундах"""
    expires_delta = timedelta(minutes=get_jwt_expire_minutes())
    expires_in_seconds = int(expires_delta.total_seconds())
    access_token = create_access_token(
        user_id=user_id,
        email=email,
        expires_delta=expires_delta,
    )
    return access_token, expires_in_seconds


def decode_access_token(token: str) -> dict[str, Any]:
    """
    проверить подпись и срок действия JWT access token
    и вернуть его payload
    """
    if token.count(".") != 2:
        raise AuthenticationError("Некорректный формат токена.")

    encoded_header, encoded_payload, encoded_signature = token.split(".")

    try:
        header = json.loads(_b64url_decode(encoded_header).decode("utf-8"))
        payload = json.loads(_b64url_decode(encoded_payload).decode("utf-8"))
    except (ValueError, json.JSONDecodeError) as exc:
        raise AuthenticationError("Не удалось декодировать токен.") from exc

    if header.get("alg") != "HS256":
        raise AuthenticationError("Неподдерживаемый алгоритм токена.")

    if payload.get("iss") != JWT_ISSUER:
        raise AuthenticationError("Некорректный издатель токена.")

    if payload.get("aud") != JWT_AUDIENCE:
        raise AuthenticationError("Некорректная аудитория токена.")

    signing_input = f"{encoded_header}.{encoded_payload}".encode("ascii")
    expected_signature = hmac.new(
        get_jwt_secret_key().encode("utf-8"),
        signing_input,
        hashlib.sha256,
    ).digest()
    actual_signature = _b64url_decode(encoded_signature)

    if not secrets.compare_digest(actual_signature, expected_signature):
        raise AuthenticationError("Подпись токена недействительна.")

    exp = payload.get("exp")
    if not isinstance(exp, (int, float)):
        raise AuthenticationError("Токен не содержит срока действия.")

    if int(exp) <= int(time.time()):
        raise AuthenticationError("Срок действия токена истек.")

    return payload