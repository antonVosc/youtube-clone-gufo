#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
ROOT="$(pwd)"
SLUG="$(echo "$ROOT" | sed 's#[/.]#-#g')"
SRC="$HOME/.claude/projects/$SLUG"
mkdir -p ai-dialogs

if [ -d "$SRC" ] && ls "$SRC"/*.jsonl >/dev/null 2>&1; then
  cp -v "$SRC"/*.jsonl ai-dialogs/
else
  echo "!! Не найдены сессии Claude Code в $SRC" >&2
  echo "   Проверьте каталог: ls ~/.claude/projects/  и скопируйте *.jsonl вручную в ai-dialogs/" >&2
fi

echo "--- обвязка:"

for f in CLAUDE.md .mcp.json .claude/settings.json; do [ -e "$f" ] && echo "ok  $f" || echo "!!  нет $f"; done
for d in .claude/agents .claude/skills .claude/commands; do [ -d "$d" ] && echo "ok  $d ($(find "$d" -type f | wc -l) файлов)" || echo "!!  нет $d"; done

echo "--- в ai-dialogs: $(ls ai-dialogs/*.jsonl 2>/dev/null | wc -l) файлов .jsonl"
