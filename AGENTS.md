# AGENTS.md — ZeTer Media Converter: быстрый роутер для Codex

## Цель структуры
Обзор проекта и границы данных: [архитектура](docs/ARCHITECTURE.md).
Не читать весь проект подряд. Сначала сузить задачу до **одного owner-модуля**, затем открывать соседние файлы только по реальным вызовам из `docs/CODE_INDEX.md`.

## Старт за 30 секунд
1. Определи тип изменения по таблице ниже.
2. Если формулировка расплывчатая: `python tools/find_owner.py "ключевые слова задачи"`.
3. Для точного symbol/caller lookup используй `docs/CODE_INDEX.md` или `docs/CODE_MAP.json`.
4. Открой основной owner и только его прямые `calls/called_by`.
5. Для длинных workflow ищи `CODEX-PHASE` — не листай файл целиком.
6. После изменения: `python tools/verify_project.py` + targeted runtime-проверка затронутого flow.

## Task -> owner
| Что меняем / симптом | Открыть первым |
|---|---|
| Кнопки, вкладки, прогресс, текст UI | `videovaudio/ui.py` |
| Постоянное уведомление / переход к готовому файлу | `videovaudio/notifications.py` → `run/lifecycle.py` |
| Очередь папок, add/remove/duplicates | `videovaudio/queues.py` |
| Пути, имена output, Windows path | `videovaudio/core/paths.py` |
| Классификация ошибок FFmpeg, общие команды | `videovaudio/core/ffmpeg.py` |
| Длительности/профиль MP3/concat contract | `videovaudio/core/audio_contract.py` |
| Один видеофайл -> MP3 | `videovaudio/audio/file_conversion.py` |
| Вся папка: convert -> concat -> split | `videovaudio/audio/folder_workflow.py` |
| Разбивка MP3 <=10 часов | `videovaudio/audio/split.py` |
| FFprobe аудио / duration | `videovaudio/audio/probe.py` |
| FFprobe видео, resolution/fps/target profile | `videovaudio/video/profile.py` |
| normalize/concat/split/publish MP4 | `videovaudio/video/operations.py` |
| Полный workflow видео-папки | `videovaudio/video/folder_workflow.py` |
| Зависание FFmpeg, timeout, cancel, taskkill | `videovaudio/process_runner.py` |
| Старт/обработка audio queue | `videovaudio/run/audio.py` |
| Старт/обработка video queue | `videovaudio/run/video.py` |
| Завершение run и UI restore | `videovaudio/run/lifecycle.py` |
| problem events / signatures / recovery | `videovaudio/diagnostics/events.py` |
| heartbeat / active state / crash hooks | `videovaudio/diagnostics/lifecycle.py` |
| CPU/RAM/disk metrics | `videovaudio/diagnostics/resources.py` |
| надёжность diagnostic I/O | `videovaudio/diagnostics/io_health.py` |
| Codex report / приоритеты | `videovaudio/diagnostics/codex_report.py` |
| integrity diagnostic artifacts | `videovaudio/diagnostics/integrity.py` |
| health history / regression baseline | `videovaudio/diagnostics/health.py` |
| summary/report/latest-run files | `videovaudio/diagnostics/run_reports.py` |
| atomic file writes | `videovaudio/storage/atomic.py` |
| retention/cleanup/compression logs | `videovaudio/storage/maintenance.py` |
| build/source identity, ffmpeg versions | `videovaudio/storage/runtime.py` |
| setup папки `Логи проблем` / logger | `videovaudio/storage/logging_setup.py` |
| поиск media files / natural sort | `videovaudio/storage/media_scan.py` |
| константы, state initialization, composition | `videovaudio/app.py` |
| multiple-folder dialog | `videovaudio/dialogs.py` |

## Критические cross-owner маршруты
- **FFmpeg bug:** feature owner -> `process_runner.py` -> `core/ffmpeg.py`.
- **Audio duration/concat bug:** `audio/folder_workflow.py` -> `core/audio_contract.py` -> `audio/probe.py`.
- **Video merge quality/codec bug:** `video/folder_workflow.py` -> `video/operations.py` -> `video/profile.py`.
- **Log/diagnostics bug:** нужный `diagnostics/*` -> `storage/atomic.py`/`storage/logging_setup.py` только если проблема физической записи.
- **Cancel/close bug:** `process_runner.py` + `diagnostics/lifecycle.py` + соответствующий `run/*` только по call graph.

## Длинные workflow
Не переписывать их ради размера. Используй якоря:
- `audio/file_conversion.py`: `CODEX-PHASE A1..A5`
- `audio/folder_workflow.py`: `CODEX-PHASE F1..F9`
- `audio/split.py`: `CODEX-PHASE S1..S5`
- `video/folder_workflow.py`: `CODEX-PHASE V1..V6`
- `process_runner.py`: `CODEX-PHASE P1..P4`

## Инварианты
- Название продукта задаёт `APP_NAME` в `videovaudio/app.py`; интерфейс и новые диагностические отчёты используют эту константу.
- `ZeTer Media Converter.py` — только launcher; feature logic туда не возвращать.
- Tkinter/UI state остаётся в UI thread; workers общаются через существующие helpers.
- Cancel/timeout должны освобождать subprocess и не оставлять stale active state.
- Исходники не терять; проверенный output публиковать после validation.
- Atomic writes, bounded logs и 120-day retention не ослаблять без явной задачи.
- Audio/video части соблюдают <=10h contract с существующими tolerance.
- Публичный `VideoToAudioConverter` и его текущие методы сохранять, если пользователь явно не просит API change.

## Проверка
```bash
python tools/verify_project.py
python tools/find_owner.py "ffmpeg timeout"
python "ZeTer Media Converter.py"
```
Последняя команда — runtime UI smoke; FFmpeg flows проверять на Windows с реальными `ffmpeg`/`ffprobe` и короткими тестовыми media.
