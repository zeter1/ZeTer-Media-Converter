#!/usr/bin/env python3
"""Fast lexical owner lookup for Codex/humans using generated CODE_MAP.json."""
from __future__ import annotations
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAP = ROOT / "docs" / "CODE_MAP.json"

ALIASES = {
    "аудио": ["audio", "mp3", "звук"],
    "звук": ["audio", "mp3", "аудио"],
    "склейка": ["concat", "merge", "объедин", "full_audio"],
    "объединение": ["merge", "concat", "video", "групп"],
    "разбивка": ["split", "part", "част"],
    "часть": ["split", "part", "segment"],
    "видео": ["video", "mp4"],
    "папка": ["folder", "queue", "scan"],
    "очередь": ["queue", "run"],
    "отмена": ["cancel", "terminate", "process"],
    "завис": ["timeout", "process", "ffmpeg"],
    "таймаут": ["timeout", "process", "ffmpeg"],
    "ffmpeg": ["ffmpeg", "process", "command"],
    "ffprobe": ["probe", "info", "duration"],
    "лог": ["log", "diagnostic", "report", "problem"],
    "ошибка": ["problem", "failure", "diagnostic", "exception"],
    "диагностика": ["diagnostic", "problem", "report", "health"],
    "отчет": ["report", "summary", "codex"],
    "отчёт": ["report", "summary", "codex"],
    "интерфейс": ["ui", "tkinter"],
    "кнопка": ["ui", "button"],
    "прогресс": ["progress", "ui"],
    "путь": ["path", "output", "folder"],
    "файл": ["file", "storage", "output"],
    "атомар": ["atomic", "replace", "storage"],
}


def tokens(text: str) -> list[str]:
    base = re.findall(r"[\wа-яё]+", text.lower(), flags=re.UNICODE)
    expanded = list(base)
    for token in base:
        for key, values in ALIASES.items():
            if token.startswith(key) or key.startswith(token):
                expanded.extend(values)
    return sorted(set(expanded))


def main() -> int:
    if len(sys.argv) < 2:
        print('Usage: python tools/find_owner.py "ffmpeg timeout"')
        return 2
    query = " ".join(sys.argv[1:])
    qtokens = tokens(query)
    payload = json.loads(MAP.read_text(encoding="utf-8"))
    results = []
    for name, item in payload["method_owners"].items():
        haystack = " ".join([
            name,
            item.get("module", ""),
            item.get("class", ""),
            item.get("doc", ""),
            " ".join(item.get("calls", [])),
            " ".join(item.get("called_by", [])),
        ]).lower()
        score = 0
        matches = []
        for token in qtokens:
            if token in name.lower():
                score += 8
                matches.append(token)
            elif token in item.get("module", "").lower():
                score += 5
                matches.append(token)
            elif token in haystack:
                score += 2
                matches.append(token)
        if score:
            results.append((score, name, item, sorted(set(matches))))
    results.sort(key=lambda row: (-row[0], row[2].get("loc", 9999), row[1]))
    print(f"Query: {query}")
    print(f"Expanded tokens: {', '.join(qtokens)}")
    print()
    for score, name, item, matches in results[:12]:
        print(f"[{score:02}] {name}() -> {item['module']}:{item['line_start']}-{item['line_end']}")
        if item.get("doc"):
            print(f"     {item['doc']}")
        if item.get("called_by"):
            print(f"     called_by: {', '.join(item['called_by'][:8])}")
        print(f"     matched: {', '.join(matches)}")
    if not results:
        print("No owner candidates found. Use docs/CODE_INDEX.md or ripgrep.")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
