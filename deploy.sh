#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

if [ "$(id -u)" -ne 0 ]; then echo "Запустите через sudo: sudo ./deploy.sh" >&2; exit 1; fi

if ! command -v docker >/dev/null 2>&1; then
  echo ">> Устанавливаю Docker..."
  apt-get update -y
  apt-get install -y ca-certificates curl openssl
  curl -fsSL https://get.docker.com | sh
fi

docker compose version >/dev/null 2>&1 || { apt-get update -y && apt-get install -y docker-compose-plugin; }

if [ ! -f .env ]; then
  echo ">> Генерирую .env с случайными секретами..."
  cp .env.example .env
  PG=$(openssl rand -hex 16); MN=$(openssl rand -hex 16); JWT=$(openssl rand -hex 32)
  sed -i "s/^POSTGRES_PASSWORD=.*/POSTGRES_PASSWORD=$PG/" .env
  sed -i "s/^MINIO_ROOT_PASSWORD=.*/MINIO_ROOT_PASSWORD=$MN/" .env
  sed -i "s/^JWT_SECRET=.*/JWT_SECRET=$JWT/" .env
  sed -i "s#postgresql+asyncpg://tube:change-me@#postgresql+asyncpg://tube:$PG@#" .env
  chmod 600 .env
fi

echo ">> Собираю и запускаю сервисы (первый запуск занимает несколько минут)..."
docker compose up -d --build

echo ">> Жду готовности API..."

for _ in $(seq 1 90); do
  curl -fs http://localhost/api/health >/dev/null 2>&1 && break || sleep 2
done

curl -fs http://localhost/api/health >/dev/null 2>&1 || { echo "API не поднялся:"; docker compose logs --tail=60 api; exit 1; }
