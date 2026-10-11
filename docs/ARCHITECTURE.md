# Архитектура ZeTer Media Converter

## Главная идея
Проект организован по **feature packages + responsibility owners**. Корневой `ZeTer Media Converter.py` запускает приложение, `videovaudio/app.py` только собирает публичный `VideoToAudioConverter`, а реальное поведение живёт в маленьких owner-модулях.

Это второй уровень рефакторинга исходного монолита (~8700 строк): вместо нескольких новых файлов по 1000–1400 строк появились тематические подпакеты `audio`, `video`, `diagnostics`, `storage`, `run`, `core`.

## Composition root
`APP_NAME` в `videovaudio/app.py` задаёт название **ZeTer Media Converter**
для заголовка окна, шапки интерфейса и новых диагностических документов.
Файл запуска — `ZeTer Media Converter.py`; имена пакета и публичного класса сохраняются для совместимости.

`videovaudio/app.py` наследует агрегирующие mixin-пакеты:

`UI -> Queue -> Core -> Diagnostics -> ProcessRunner -> Audio -> Video -> Run -> Storage`

Агрегаторы в `*/__init__.py` **не содержат бизнес-логику**. Они только собирают более узкие mixin-owners. Поэтому для изменения почти всегда открывай конкретный `.py`, а не `__init__.py`.

## Дерево ответственности
```text
ZeTer Media Converter.py        launcher
videovaudio/
  app.py                        constants + state initialization + composition
  ui.py                         Tkinter main UI
  notifications.py              persistent completion window + Explorer navigation
  dialogs.py                    multiple-folder dialog
  queues.py                     queue editing/validation
  process_runner.py             subprocess lifecycle / cancel / timeout

  core/
    paths.py                    paths/output naming
    ffmpeg.py                   shared FFmpeg helpers/failure diagnosis
    audio_contract.py           duration/profile invariants

  audio/
    file_conversion.py          one input video -> validated MP3
    folder_workflow.py          one full course folder orchestration
    split.py                    full MP3 -> <=10h parts
    probe.py                    audio FFprobe metadata

  video/
    profile.py                  probe/target profile/validation/commands
    operations.py               normalize/concat/split/group/publish primitives
    folder_workflow.py          one course folder orchestration

  run/
    audio.py                    audio queue start + execution
    video.py                    video queue start + execution
    lifecycle.py                common completion

  diagnostics/
    common.py                   time/hash helpers
    resources.py                CPU/RAM/disk aggregate metrics
    io_health.py                diagnostic-write health
    lifecycle.py                active state/heartbeat/crash/close
    events.py                   structured problems/recovery linkage
    codex_report.py             AI-oriented review/prioritization
    integrity.py                structural/semantic integrity checks
    health.py                   cross-run health history
    run_reports.py              summary/report/latest-run persistence

  storage/
    atomic.py                   atomic read/write/replace
    maintenance.py              retention/cleanup/compression
    runtime.py                  source/tool/runtime identity
    logging_setup.py            log tree/session setup
    media_scan.py               media scan/natural sort
```

## Почему часть workflow всё ещё длинная
`audio/folder_workflow.py::process_single_folder()` и `audio/split.py::split_file()` являются последовательными transaction-like workflows с большим количеством early-return, validation и recovery веток. В этой проходке их **не разрезали искусственно на helpers**, чтобы не менять рабочую FFmpeg/state semantics без полноценного Windows runtime regression suite.

Вместо этого внутри добавлены стабильные `CODEX-PHASE` anchors, а `docs/CODE_INDEX.md` содержит точные строки, calls и called_by. Это ускоряет навигацию без рискованной переписи алгоритма.

## Source identity
`storage/runtime.py::get_source_identity()` рекурсивно хэширует `ZeTer Media Converter.py` + все `videovaudio/**/*.py`, поэтому изменение launcher или вложенного owner-модуля меняет `build_id` в диагностике.

## Запуск, данные и проверка
`run/lifecycle.py::done` после восстановления управления передаёт UI точные
`output_files` успешных папок завершённой очереди. Для аудио список копируется
из `last_split_validation.parts` после публикации; видео уже содержит итоговый
manifest. Отменённый или аварийный запуск не показывает уведомление об успехе.
`ui.py` хранит один `CompletionNotification`: он не модален, не привязан к
минимизации главного окна, остаётся поверх окон и использует рабочую область
монитора программы без панели задач. Новые результаты добавляются в начало
прокручиваемого списка. Открытие Проводника не закрывает уведомление; исчезнувший
файл вызывает сообщение внутри него. Крестик очищает список; закрытие приложения
уничтожает его Tk-окна. Отдельных таймеров уведомление не создаёт.

Запуск и требования: [README](../README.md). Проверки: [VERIFICATION](VERIFICATION.md).
Настройки текущего сеанса инициализируются в `app.py`; запуск launcher создаёт UI
и диагностическое состояние. `storage/logging_setup.py` размещает `Логи проблем`
рядом с программой в source mode. Импорт классов сам по себе UI не запускает.

Аудиорезультаты и `__temp__` размещаются в обрабатываемой папке курса.
`audio/folder_workflow.py::preserve_previous_audio_outputs` перед повторной обработкой
копирует прежние результаты по явному manifest в резервную папку, проверяет байты
и только затем освобождает выходные имена. Сбой копирования останавливает обработку.
Расположение и ручная очистка резервных копий описаны в README.
`audio/file_conversion.py` проверяет временный MP3 и длительность до `os.replace`;
сравнение длительности выявляет грубое укорочение, но не доказывает полноту содержания.
`audio/split.py` создаёт набор частей во временной подпапке результата, проверяет
каждую часть и их общую длительность, затем переносит весь набор. Существующие
выходные имена не перезаписываются; ошибка переноса запускает откат уже перенесённых
частей. Ошибка отката сохраняет временную папку и записывается в диагностику.
`run/audio.py` возвращает управление UI даже при ошибках файлов диагностики;
уведомление об успехе отправляется только после завершения финализации.

## Generated navigation
- `docs/CODE_MAP.json` — machine-readable symbol ownership/call graph.
- `docs/CODE_INDEX.md` — human/Codex-friendly symbol index.
- Источник генерации: `tools/generate_code_index.py`.
- Проверка freshness входит в `tools/verify_project.py`.
