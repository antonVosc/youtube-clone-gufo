# TubeClone — правила для ИИ

## Цель

Копия YouTube: загрузка → транскодинг в HLS → просмотр → лайки/комментарии, роли, приватные видео, модерация.

## Стек (не менять без записи в docs/architecture.md)

FastAPI + SQLAlchemy 2 async + Alembic, PostgreSQL 16, MinIO (S3), Celery + Redis (ffmpeg), Nginx, фронт без сборки (`frontend/`, vanilla JS, hls.js локально).

## Архитектурные правила

- **Видео не проходят через Python.** Загрузка — presigned multipart прямо в MinIO через Nginx `/s3/`. Раздача — Nginx `/media/` через `auth_request` → `/api/media/auth` → presigned GET на 60 с.
- **Единственная точка прав на видео — `can_view_video` (app/deps.py).** Любой новый эндпоинт, отдающий метаданные, комментарии, лайки, сегменты или превью видео, обязан ее вызывать. Чужое непросматриваемое видео — **404**, не 403.
- Бакет приватный. Никаких публичных ссылок на S3. Оригинал (`source`) наружу не отдается.
- Схема БД меняется только Alembic-миграцией (`alembic revision --autogenerate`), `alembic check` должен быть чистым.
- Роутеры тонкие; запросы/сериализация видео — `app/services/videos.py`.
- Фронт: DOM только через `h()`/`textContent`. **`innerHTML`, `outerHTML`, `eval` запрещены** (есть тест). Inline-скрипты запрещены CSP.
- Секреты только из `.env`; в git только `.env.example`.
- Модерация = флаг `is_hidden`, а не статус. Роль читается из БД на каждый запрос.

## Процесс

- Одна задача = одна сессия = один коммит (conventional commits: `feat(scope):`, `fix:`, `test:`, `docs:`, `chore:`).
- Для каждой фичи — тест критичного поведения (негативные сценарии прав — раньше позитивных).
- Перед коммитом: `/check` (ruff + pytest + агент `reviewer`).

## Definition of Done

1. `docker compose exec api pytest -q` зеленый. 2. `ruff check backend` чистый. 3. Эндпоинт виден в Swagger. 4. docs/ обновлены. 5. Замечания `reviewer` закрыты. 6. Для затрагивающих основной сценарий — `scripts/smoke.py` проходит.

## Команды

- Запуск: `sudo ./deploy.sh` или `docker compose up -d --build`
- Тесты: `docker compose exec api pytest -q`; линт: `ruff check backend`
- Миграция: `docker compose exec api alembic revision --autogenerate -m "msg"`
- Seed: `docker compose exec api python -m app.seed`; сквозная проверка: `docker compose exec -T api python scripts/smoke.py`
