#!/usr/bin/env python3
"""Generate AI-oriented code navigation artifacts from the current source tree."""
from __future__ import annotations

import argparse
import ast
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "videovaudio"
JSON_PATH = ROOT / "docs" / "CODE_MAP.json"
MD_PATH = ROOT / "docs" / "CODE_INDEX.md"


def first_line(value: str | None) -> str:
    if not value:
        return ""
    return value.strip().splitlines()[0].strip()


def self_calls(node: ast.AST) -> list[str]:
    calls: set[str] = set()
    for child in ast.walk(node):
        if not isinstance(child, ast.Call):
            continue
        func = child.func
        if (
            isinstance(func, ast.Attribute)
            and isinstance(func.value, ast.Name)
            and func.value.id == "self"
        ):
            calls.add(func.attr)
    return sorted(calls)


def phase_anchors(lines: list[str]) -> list[dict]:
    result = []
    for index, line in enumerate(lines, 1):
        stripped = line.strip()
        if stripped.startswith("# CODEX-PHASE"):
            label, _, description = stripped[2:].partition(":")
            result.append({
                "line": index,
                "label": label.strip(),
                "description": description.strip(),
            })
    return result


def build_map() -> dict:
    module_data: dict[str, dict] = {}
    all_methods: list[dict] = []
    for path in sorted(PACKAGE.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        rel = path.relative_to(ROOT).as_posix()
        text = path.read_text(encoding="utf-8-sig")
        lines = text.splitlines()
        tree = ast.parse(text, filename=rel)
        classes = []
        for cls in [node for node in tree.body if isinstance(node, ast.ClassDef)]:
            method_items = []
            for method in [
                node for node in cls.body
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            ]:
                start = min(
                    [method.lineno]
                    + [decorator.lineno for decorator in method.decorator_list]
                )
                item = {
                    "name": method.name,
                    "class": cls.name,
                    "line_start": start,
                    "line_end": method.end_lineno,
                    "loc": method.end_lineno - start + 1,
                    "doc": first_line(ast.get_docstring(method)),
                    "calls": self_calls(method),
                    "called_by": [],
                    "module": rel,
                }
                method_items.append(item)
                all_methods.append(item)
            classes.append({
                "name": cls.name,
                "line_start": cls.lineno,
                "line_end": cls.end_lineno,
                "doc": first_line(ast.get_docstring(cls)),
                "methods": method_items,
            })
        module_data[rel] = {
            "loc": len(lines),
            "summary": first_line(ast.get_docstring(tree)),
            "classes": classes,
            "phase_anchors": phase_anchors(lines),
        }

    owners: dict[str, list[dict]] = {}
    for method in all_methods:
        owners.setdefault(method["name"], []).append(method)
    for method in all_methods:
        callers = []
        for candidate in all_methods:
            if method["name"] in candidate["calls"]:
                callers.append(candidate["name"])
        method["called_by"] = sorted(set(callers))

    unique_owners = {
        name: {
            key: value for key, value in entries[0].items()
            if key in {
                "module", "class", "line_start", "line_end", "loc",
                "doc", "calls", "called_by"
            }
        }
        for name, entries in owners.items()
        if len(entries) == 1 and not name.startswith("__")
    }
    duplicates = {
        name: [entry["module"] for entry in entries]
        for name, entries in owners.items()
        if len(entries) > 1 and not name.startswith("__")
    }
    return {
        "schema_version": 2,
        "entrypoint": "ZeTer Media Converter.py",
        "package": "videovaudio",
        "module_count": len(module_data),
        "method_count_all_classes": len(all_methods),
        "unique_method_owner_count": len(unique_owners),
        "duplicate_non_dunder_method_names": duplicates,
        "modules": module_data,
        "method_owners": unique_owners,
    }


def render_markdown(payload: dict) -> str:
    lines = [
        "# CODE INDEX — быстрый индекс для Codex",
        "",
        "> GENERATED FILE. Не редактировать вручную: `python tools/generate_code_index.py`.",
        "",
        "Используй этот файл как `symbol -> owner -> line range -> dependencies`. Для продуктовой маршрутизации сначала смотри `AGENTS.md`.",
        "",
        "## Модули",
        "",
        "| Модуль | LOC | Назначение |",
        "|---|---:|---|",
    ]
    for module, data in payload["modules"].items():
        if module.endswith("/__init__.py"):
            continue
        lines.append(f"| `{module}` | {data['loc']} | {data['summary']} |")

    lines.extend(["", "## CODEX-PHASE якоря", ""])
    any_anchor = False
    for module, data in payload["modules"].items():
        anchors = data.get("phase_anchors") or []
        if not anchors:
            continue
        any_anchor = True
        lines.append(f"### `{module}`")
        lines.append("")
        for anchor in anchors:
            lines.append(
                f"- `{anchor['label']}` — строка {anchor['line']}: {anchor['description']}"
            )
        lines.append("")
    if not any_anchor:
        lines.append("- Нет.")

    lines.extend(["## Методы по owner-модулям", ""])
    for module, data in payload["modules"].items():
        method_rows = []
        for cls in data["classes"]:
            for method in cls["methods"]:
                if method["name"].startswith("__"):
                    continue
                method_rows.append(method)
        if not method_rows:
            continue
        lines.append(f"### `{module}`")
        lines.append("")
        lines.append("| Метод | Строки | Что делает | Вызывает `self.*` | Вызывается из |")
        lines.append("|---|---:|---|---|---|")
        for method in method_rows:
            calls = ", ".join(f"`{name}`" for name in method["calls"]) or "—"
            called_by = ", ".join(f"`{name}`" for name in method["called_by"]) or "—"
            doc = (method["doc"] or "").replace("|", "\\|")
            lines.append(
                f"| `{method['name']}()` | {method['line_start']}-{method['line_end']} | {doc} | {calls} | {called_by} |"
            )
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="Fail if generated artifacts are stale")
    args = parser.parse_args()
    payload = build_map()
    json_text = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    md_text = render_markdown(payload)
    if args.check:
        stale = []
        if not JSON_PATH.is_file() or JSON_PATH.read_text(encoding="utf-8") != json_text:
            stale.append(str(JSON_PATH.relative_to(ROOT)))
        if not MD_PATH.is_file() or MD_PATH.read_text(encoding="utf-8") != md_text:
            stale.append(str(MD_PATH.relative_to(ROOT)))
        if stale:
            print("STALE:", ", ".join(stale))
            return 1
        print("Code index is up to date")
        return 0
    JSON_PATH.write_text(json_text, encoding="utf-8")
    MD_PATH.write_text(md_text, encoding="utf-8")
    print(f"Wrote {JSON_PATH.relative_to(ROOT)} and {MD_PATH.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
