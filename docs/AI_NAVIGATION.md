# ZeTer Media Converter — навигация по коду

## 1. Не начинай с полного чтения
Для обычного бага/feature не открывай все файлы. Используй progressive disclosure:

1. `AGENTS.md` -> task owner.
2. `python tools/find_owner.py "симптом или функция"` -> shortlist symbols.
3. `docs/CODE_INDEX.md` -> точные строки + `calls/called_by`.
4. Открыть owner-файл только вокруг нужного метода/`CODEX-PHASE`.
5. Соседний owner читать только если текущий метод реально его вызывает или он вызывает текущий метод.

## 2. Быстрые примеры
```bash
python tools/find_owner.py "ffmpeg зависает timeout отмена"
python tools/find_owner.py "разбивка аудио больше 10 часов"
python tools/find_owner.py "объединение видео разрешение bitrate"
python tools/find_owner.py "логи проблем codex report"
```

## 3. Symbol lookup
Если известен метод:
```bash
# ripgrep по generated index быстрее полного source search
rg "`run_process\\(\\)`" docs/CODE_INDEX.md
rg "`process_single_folder\\(\\)`" docs/CODE_INDEX.md
```

В `CODE_INDEX.md` рядом сразу видны:
- owner-module;
- line range;
- docstring;
- какие `self.*` методы он вызывает;
- кто его вызывает.

## 4. Workflow phase lookup
Если owner найден, но метод длинный:
```bash
rg "CODEX-PHASE" videovaudio/audio/folder_workflow.py
rg "CODEX-PHASE" videovaudio/audio/split.py
rg "CODEX-PHASE" videovaudio/process_runner.py
```

Не нужно читать предыдущие фазы, если изменение локально и их contract не затрагивается.

## 5. Когда расширять контекст
Расширяй чтение только при одном из сигналов:
- меняется общий invariant (duration/profile/path/atomic state);
- меняется public/shared method;
- текущий method вызывает соседний owner, и bug может быть внутри него;
- изменение затрагивает cancel/thread/subprocess lifecycle;
- меняется format/schema логов или persisted files;
- targeted verification показывает regression вне owner-а.

## 6. Generated files
`docs/CODE_MAP.json` и `docs/CODE_INDEX.md` не редактировать вручную. После rename/move/new method:
```bash
python tools/generate_code_index.py
python tools/verify_project.py
```
