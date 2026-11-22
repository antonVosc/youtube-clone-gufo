---
name: add-endpoint
description: Шаблон добавления нового API-эндпоинта в TubeClone (схема, сервис, роутер, права, тест).
---
1. Pydantic-схемы в `app/schemas/<домен>.py`.
2. Логика в `app/services/<домен>.py` (async, принимает session и текущего пользователя).
3. Тонкий роутер в `app/routers/<домен>.py`; права — через `Depends(require_role(...))` или `can_view_video`.
4. Подключить роутер в `app/main.py`.
5. Тест: негативный сценарий прав + позитивный.
6. Если менялись модели — миграция Alembic.
