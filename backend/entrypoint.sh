#!/bin/sh
# django 컨테이너에서만 마이그레이션 실행 (RUN_MIGRATIONS=1). celery는 바로 시작.
set -e
if [ "${RUN_MIGRATIONS:-0}" = "1" ]; then
  python manage.py migrate --noinput
  # .env에 DJANGO_SUPERUSER_USERNAME/PASSWORD가 있으면 관리자 계정을 한 번 만들어 둠 (이미 있으면 건너뜀)
  if [ -n "${DJANGO_SUPERUSER_USERNAME}" ] && [ -n "${DJANGO_SUPERUSER_PASSWORD}" ]; then
    python manage.py createsuperuser --noinput --email "${DJANGO_SUPERUSER_EMAIL:-admin@example.com}" 2>/dev/null || true
  fi
fi
exec "$@"
