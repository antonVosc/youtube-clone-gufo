# Тестовое задание Гуфо Антон Вощинский - копия YouTube

Python + FastAPI, PostgreSQL, MinIO (S3), Celery/ffmpeg (HLS), Nginx, простой фронт без сборки.
Загрузка → фоновая нарезка в HLS (360p/720p) → просмотр → лайки/комментарии, подписки, плейлисты, роли, приватные видео, модерация.

## Запуск

1.

```bash
git clone https://github.com/antonVosc/youtube-clone-gufo/
```

2.

```bash
cd youtube-clone-gufo/
```

3.

```bash
sudo ./deploy.sh
```

Скрипт: ставит Docker → генерирует `.env` со случайными секретами → `docker compose up -d --build` → применяет миграции → наполняет демо-данными (пользователи всех ролей, 9 реальных видео, лайки, комментарии, подписки, плейлист, жалобы) → **прогоняет сквозной сценарий** «регистрация → загрузка → просмотр → лайк и комментарий» (`scripts/smoke.py`).

| Что        | Адрес                 |
| ---------- | --------------------- |
| Приложение | http://localhost      |
| Swagger    | http://localhost/docs |

Демо-аккаунты (пароль у всех `demo12345`): `admin@demo.local`, `moderator@demo.local`, `alice@demo.local`, `bob@demo.local`, `carol@demo.local`.

Нужны: Ubuntu с доступом в интернет (образы Docker, пакеты), порт 80, ~3 ГБ диска. Повторный запуск `deploy.sh` безопасен (seed идемпотентен).

```bash
docker compose exec api pytest -q
```

```bash
docker compose exec -T api python scripts/smoke.py
```

```bash
docker compose exec api python -m app.seed
```

```bash
docker compose logs -f worker
```

```bash
docker compose down -v
```

## Экраны

| Экран            | Маршрут                 | Что есть                                                                                                |
| ---------------- | ----------------------- | ------------------------------------------------------------------------------------------------------- |
| Главная          | `#/`                    | сетка видео с превью, длительностью, просмотрами, «N дней назад»                                        |
| Просмотр         | `#/watch/<id>`          | HLS-плеер (hls.js), лайк/дизлайк, подписка, комментарии и ответы, описание, жалоба, рекомендации справа |
| Канал            | `#/channel/<handle>`    | шапка, подписка/число подписчиков, вкладки «Видео» и «Плейлисты», редактирование своего канала          |
| Плейлист         | `#/playlist/<id>`       | список видео                                                                                            |
| Поиск            | `#/search/<запрос>`     | выдача списком в стиле YouTube                                                                          |
| Загрузка         | `#/upload`              | выбор файла, метаданные и доступ, прогресс-бар (части идут напрямую в хранилище)                        |
| Студия           | `#/studio`              | мои видео со статусами, смена доступа, выдача доступа друзьям к приватным, удаление                     |
| Подписки         | `#/subs`                | лента подписок                                                                                          |
| Вход/регистрация | `#/login`, `#/register` |                                                                                                         |
| Модерация        | `#/moderation`          | жалобы (скрыть/отклонить), скрытые видео (вернуть)                                                      |
| Админка          | `#/admin`               | роли пользователей, блокировка                                                                          |

Темная/светлая тема — по настройке системы.

## Роли и приватность

`user`, `moderator`, `admin` (таблица прав — `docs/architecture.md`). Видео бывают `public`, `unlisted` (по ссылке) и `private` — приватное видят только владелец, получившие доступ (`Студия → Дать доступ`) и модераторы; **проверка действует и на сегменты HLS**, а не только на страницу.

## Структура

```
backend/app/ - FastAPI: routers/, services/, models.py, deps.py (can_view_video), storage.py, transcode.py, worker.py, seed.py...
backend/alembic/ - миграции
backend/tests/ - автотесты(отдельная БД, фейковое S3, настоящий ffmpeg и т. д.)
backend/scripts/smoke.py - сквозная проверка
frontend/index.html, app.js, style.css, vendor/hls.min.js
nginx/nginx.conf (auth_request, прокси S3), snippets/ (заголовки, CSP)
docs/architecture.md, db.md, security.md, testing.md, prompts.md
scripts/ui_smoke.js, collect_ai_artifacts.sh
CLAUDE.md, .claude/, .mcp.json -     агентная обвязка
ai-dialogs/ - диалоги
```

## Документация

- [Архитектура](docs/architecture.md) — потоки загрузки/обработки/раздачи, решения, роли, инварианты, ограничения
- [БД](docs/db.md) — схема, связи, индексы, что лежит в БД и в S3
- [Безопасность](docs/security.md) — угрозы, меры, чем проверено, что не сделано
- [Тестирование](docs/testing.md)
- [Промпты](docs/prompts.md)

## Что проверено

Проверено в песочнице: все 51 автотест на реальном PostgreSQL 16; миграция (upgrade/downgrade/`alembic check`); полный сквозной сценарий (`smoke.py`) через **настоящие** Nginx + FastAPI + Celery + Redis + ffmpeg, включая presigned multipart-загрузку через `/s3/` и раздачу HLS через `auth_request`; seed; SPA целиком в jsdom (22 проверки по ролям и страницам).

## Работа с ИИ

Правила и агенты: `CLAUDE.md`, `.claude/` (агенты `reviewer`, `test-writer`, команда `/check`, скилл `add-endpoint`), `.mcp.json`. Исходные диалоги: `ai-dialogs/`
