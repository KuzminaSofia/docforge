#!/bin/sh
# Идемпотентный провижининг MinIO для technical-document-ml-service.
# Запускается сервисом createbucket на каждом старте стека.
#
# Делает: bucket -> private -> scoped RW-пользователь (least privilege) ->
#         SSE-S3 (шифрование at-rest) -> lifecycle (ротация входных файлов).
#
# Root-креды minioadmin используются ТОЛЬКО здесь (admin-операции). Приложение
# и воркеры ходят в MinIO под scoped-пользователем $APP_S3_ACCESS_KEY.
set -eu

BUCKET="${APP_S3_BUCKET:-technical-documents}"
RETENTION_DAYS="${APP_S3_UPLOADS_RETENTION_DAYS:-7}"

mc alias set local "${APP_S3_ENDPOINT_URL:-http://minio:9000}" \
  "${MINIO_ROOT_USER:-minioadmin}" "${MINIO_ROOT_PASSWORD:-minioadmin}"

# --- bucket + явный private доступ ---
mc mb --ignore-existing "local/${BUCKET}"
mc anonymous set none "local/${BUCKET}"

# --- scoped RW-политика только на этот bucket + пользователь под ней ---
cat > /tmp/tdms-policy.json <<EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": ["s3:GetObject", "s3:PutObject", "s3:DeleteObject"],
      "Resource": ["arn:aws:s3:::${BUCKET}/*"]
    },
    {
      "Effect": "Allow",
      "Action": ["s3:ListBucket", "s3:GetBucketLocation"],
      "Resource": ["arn:aws:s3:::${BUCKET}"]
    }
  ]
}
EOF

# create/add идемпотентны через "|| true": при повторном запуске объекты уже существуют
mc admin policy create local tdms-app-rw /tmp/tdms-policy.json || true
mc admin user add local "${APP_S3_ACCESS_KEY}" "${APP_S3_SECRET_KEY}" || true
mc admin policy attach local tdms-app-rw --user "${APP_S3_ACCESS_KEY}" || true

# --- шифрование at-rest (SSE-S3, bucket default) ---
mc encrypt set sse-s3 "local/${BUCKET}"

# --- lifecycle: автоудаление входных файлов через N дней (декларативный import) ---
# import заменяет всю ILM-конфигурацию целиком -> повторный запуск не плодит дубли правил.
# Прерванные multipart-загрузки boto3 абортит сам при ошибке, поэтому отдельное
# AbortIncompleteMultipartUpload-правило не заводим (упрощает ILM-конфиг).
cat > /tmp/tdms-lifecycle.json <<EOF
{
  "Rules": [
    {
      "ID": "expire-uploads",
      "Status": "Enabled",
      "Filter": { "Prefix": "uploads/" },
      "Expiration": { "Days": ${RETENTION_DAYS} }
    }
  ]
}
EOF
mc ilm import "local/${BUCKET}" < /tmp/tdms-lifecycle.json

echo "minio provisioning complete: bucket=${BUCKET} retention=${RETENTION_DAYS}d user=${APP_S3_ACCESS_KEY}"
