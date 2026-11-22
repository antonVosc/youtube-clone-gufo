# Диалоги с ИИ

Сюда кладутся **исходные файлы сессий** инструмента, которым писался проект.

## Claude Code
Файлы `*.jsonl` из `~/ai-dialogs/` — ровно диалоги этого проекта. Скопируйте их целиком одной командой:

```bash
./scripts/collect_ai_artifacts.sh
```

Скрипт копирует все `*.jsonl` сессий проекта в `ai-dialogs/` и проверяет, что на месте вся обвязка: `CLAUDE.md`, `.claude/` (agents, skills, commands, settings.json), `.mcp.json`
