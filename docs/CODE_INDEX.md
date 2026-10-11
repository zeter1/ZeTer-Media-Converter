# CODE INDEX — быстрый индекс для Codex

> GENERATED FILE. Не редактировать вручную: `python tools/generate_code_index.py`.

Используй этот файл как `symbol -> owner -> line range -> dependencies`. Для продуктовой маршрутизации сначала смотри `AGENTS.md`.

## Модули

| Модуль | LOC | Назначение |
|---|---:|---|
| `videovaudio/app.py` | 147 | Application composition root. |
| `videovaudio/audio/file_conversion.py` | 506 | Single-video -> MP3 conversion, fallback and validation. |
| `videovaudio/audio/folder_workflow.py` | 988 | End-to-end workflow for one audio-course folder. |
| `videovaudio/audio/probe.py` | 148 | FFprobe parsing and audio metadata helpers. |
| `videovaudio/audio/split.py` | 715 | Split a full MP3 into validated <=10-hour outputs. |
| `videovaudio/core/audio_contract.py` | 98 | Audio invariants, duration tolerances and concat manifest helpers. |
| `videovaudio/core/ffmpeg.py` | 318 | Shared FFmpeg command helpers and failure classification. |
| `videovaudio/core/paths.py` | 122 | Path normalization, output naming and filesystem-facing helpers. |
| `videovaudio/diagnostics/codex_report.py` | 315 | Codex-focused prioritization and improvement report. |
| `videovaudio/diagnostics/common.py` | 40 | Time and source hashing helpers shared by diagnostics/runtime identity. |
| `videovaudio/diagnostics/events.py` | 428 | Structured problem events, deduplication and recovery linkage. |
| `videovaudio/diagnostics/health.py` | 172 | Compact cross-run health history and regression baseline. |
| `videovaudio/diagnostics/integrity.py` | 243 | Structural and semantic consistency checks for diagnostic artifacts. |
| `videovaudio/diagnostics/io_health.py` | 155 | Reliability monitoring for diagnostic files and atomic state writes. |
| `videovaudio/diagnostics/lifecycle.py` | 332 | Active-run state, heartbeat, exception hooks and shutdown lifecycle. |
| `videovaudio/diagnostics/resources.py` | 269 | Resource sampling and aggregated run metrics. |
| `videovaudio/diagnostics/run_reports.py` | 389 | Per-run diagnostic files, summary/report persistence and latest-run indexes. |
| `videovaudio/dialogs.py` | 218 | Custom Tkinter dialogs. |
| `videovaudio/notifications.py` | 114 | Persistent completion window and Windows Explorer navigation (Tk thread only). |
| `videovaudio/process_runner.py` | 380 | Subprocess lifecycle, cancellation, timeout and process log retention. |
| `videovaudio/queues.py` | 260 | Audio/video folder queues, validation and queue widgets state. |
| `videovaudio/run/audio.py` | 366 | Audio queue run orchestration and start action. |
| `videovaudio/run/lifecycle.py` | 51 | Shared run completion/UI restoration. |
| `videovaudio/run/video.py` | 301 | Video queue run orchestration and start action. |
| `videovaudio/storage/atomic.py` | 101 | Atomic file replacement/read-write primitives. |
| `videovaudio/storage/logging_setup.py` | 332 | Session directories, Python logging and diagnostic artifact setup. |
| `videovaudio/storage/maintenance.py` | 337 | Log retention, compression and stale artifact cleanup. |
| `videovaudio/storage/media_scan.py` | 132 | Supported-media discovery and natural ordering. |
| `videovaudio/storage/runtime.py` | 220 | Runtime/build identity, tool versions and log storage metrics. |
| `videovaudio/ui.py` | 297 | Tkinter interface construction and UI-thread helper methods. |
| `videovaudio/video/folder_workflow.py` | 369 | End-to-end workflow for one course folder in video-merge mode. |
| `videovaudio/video/operations.py` | 395 | Reusable video normalize/concat/split/group/publish operations. |
| `videovaudio/video/profile.py` | 369 | Video probing, target profile selection, FFmpeg normalization command and validation. |

## CODEX-PHASE якоря

### `videovaudio/audio/file_conversion.py`

- `CODEX-PHASE A1` — строка 37: build the primary/fallback FFmpeg command.
- `CODEX-PHASE A2` — строка 68: run the primary MP3 conversion attempt.
- `CODEX-PHASE A3` — строка 83: classify failure and execute the libmp3lame compatibility fallback when applicable.
- `CODEX-PHASE A4` — строка 249: validate staged audio before publishing the per-video MP3.
- `CODEX-PHASE A5` — строка 470: terminal invalid/missing output handling.

### `videovaudio/audio/folder_workflow.py`

- `CODEX-PHASE F1` — строка 97: initialize folder state, UI and summary.
- `CODEX-PHASE F2` — строка 139: scan/validate source media before creating outputs.
- `CODEX-PHASE F3` — строка 215: prepare directories and preserve previous outputs.
- `CODEX-PHASE F4` — строка 255: parallel per-video conversion and progress collection.
- `CODEX-PHASE F5` — строка 433: aggregate conversion metrics and validate MP3 profiles/skips.
- `CODEX-PHASE F6` — строка 512: concatenate all valid MP3 files; fallback to transcode if copy fails.
- `CODEX-PHASE F7` — строка 636: verify concat duration and repair timeline mismatch if needed.
- `CODEX-PHASE F8` — строка 884: split validated full audio into <=10-hour final parts.
- `CODEX-PHASE F9` — строка 956: unconditional temp cleanup and final active-state update.

### `videovaudio/audio/split.py`

- `CODEX-PHASE S1` — строка 98: establish duration contract and target part length.
- `CODEX-PHASE S2` — строка 156: create each part with copy-first / transcode-fallback logic.
- `CODEX-PHASE S3` — строка 620: verify that at least one part was produced.
- `CODEX-PHASE S4` — строка 631: validate total duration across all generated parts.
- `CODEX-PHASE S5` — строка 686: publish successful split validation summary.

### `videovaudio/process_runner.py`

- `CODEX-PHASE P1` — строка 139: finalize process output, retention and slow-process diagnostics.
- `CODEX-PHASE P2` — строка 218: launch child process and register live process context.
- `CODEX-PHASE P3` — строка 263: poll cancel/fatal-output/timeout/process-exit conditions.
- `CODEX-PHASE P4` — строка 340: persist footer, classify timeout and return CompletedProcess metadata.

### `videovaudio/video/folder_workflow.py`

- `CODEX-PHASE V1` — строка 102: scan and validate the course folder.
- `CODEX-PHASE V2` — строка 141: probe each input and build duration/profile items.
- `CODEX-PHASE V3` — строка 181: choose target profile and pack videos into <=10-hour groups.
- `CODEX-PHASE V4` — строка 220: build and validate each staged output group.
- `CODEX-PHASE V5` — строка 297: atomically publish the complete validated output set.
- `CODEX-PHASE V6` — строка 352: cleanup staging directory and finalize folder state.

## Методы по owner-модулям

### `videovaudio/audio/file_conversion.py`

| Метод | Строки | Что делает | Вызывает `self.*` | Вызывается из |
|---|---:|---|---|---|
| `convert_single_file()` | 20-506 | Многопоточная конвертация одного видео с честной диагностикой ffmpeg. | `build_output_path`, `command_to_text`, `diagnose_ffmpeg_failure`, `duration_mismatch`, `ffmpeg_base_command`, `get_audio_info`, `mark_problem_recovered`, `mark_problem_unresolved`, `path_facts`, `run_process`, `write_problem` | — |

### `videovaudio/audio/folder_workflow.py`

| Метод | Строки | Что делает | Вызывает `self.*` | Вызывается из |
|---|---:|---|---|---|
| `process_single_folder()` | 63-988 | Обработка одной папки. Успех возвращается только если все этапы реально выполнены. | `audio_profile_key`, `audio_profile_matches_target`, `build_audio_split_output_path`, `command_to_text`, `duration_mismatch`, `escape_concat_path`, `expected_audio_profile`, `ffmpeg_base_command`, `format_duration`, `get_audio_info`, `log_message`, `mark_problem_recovered`, `mark_problem_unresolved`, `normalize_folder_path`, `normalize_returncode`, `now_iso`, `path_facts`, `run_process`, `save_concat_input_manifest`, `scan_media_files`, `set_status`, `split_file`, `trim_text`, `ui_after`, `update_active_state`, `update_progress`, `write_problem` | `process_queue` |

### `videovaudio/audio/probe.py`

| Метод | Строки | Что делает | Вызывает `self.*` | Вызывается из |
|---|---:|---|---|---|
| `extract_ffprobe_json()` | 16-31 | Извлекает JSON ffprobe из process-log с добавленным служебным заголовком. | — | `get_audio_info`, `get_video_info` |
| `get_audio_info()` | 33-139 | Возвращает длительность и фактический аудиопрофиль через один вызов ffprobe. | `command_to_text`, `extract_ffprobe_json`, `run_process`, `trim_text`, `write_problem` | `convert_single_file`, `get_duration`, `process_single_folder` |
| `get_duration()` | 141-143 | Возвращает длительность файла через ffprobe и логирует реальные причины ошибок. | `get_audio_info` | `_split_file_into_stage` |
| `format_duration()` | 145-148 |  | — | `_split_file_into_stage`, `process_single_folder`, `process_video_folder` |

### `videovaudio/audio/split.py`

| Метод | Строки | Что делает | Вызывает `self.*` | Вызывается из |
|---|---:|---|---|---|
| `split_file()` | 17-91 | Проверяет полный набор временных частей и затем публикует без перезаписи. | `_split_file_into_stage`, `write_problem` | `process_single_folder` |
| `_split_file_into_stage()` | 93-715 | Точная разбивка ≤10 часов. Возвращает True только если все части созданы. | `build_audio_split_output_path`, `command_to_text`, `duration_mismatch`, `ffmpeg_base_command`, `format_duration`, `get_duration`, `log_message`, `mark_problem_recovered`, `mark_problem_unresolved`, `run_process`, `trim_text`, `update_progress`, `write_problem` | `split_file` |

### `videovaudio/core/audio_contract.py`

| Метод | Строки | Что делает | Вызывает `self.*` | Вызывается из |
|---|---:|---|---|---|
| `duration_mismatch()` | 14-24 | Возвращает предел и величину недопустимого расхождения длительностей. | — | `_split_file_into_stage`, `convert_single_file`, `process_single_folder`, `split_long_video_to_outputs`, `validate_merged_video` |
| `expected_audio_profile()` | 26-33 | Единый профиль MP3, обязательный для безопасной concat-склейки. | — | `process_single_folder` |
| `audio_profile_key()` | 35-41 | Компактный ключ аудиопрофиля для JSON-сводки. | — | `process_single_folder` |
| `audio_profile_matches_target()` | 43-50 | Проверяет важные для concat параметры фактически созданного MP3. | — | `process_single_folder` |
| `save_concat_input_manifest()` | 52-98 | Сохраняет полный компактный порядок MP3 только при проблеме склейки. | `atomic_write_json`, `safe_log_fragment` | `process_single_folder` |

### `videovaudio/core/ffmpeg.py`

| Метод | Строки | Что делает | Вызывает `self.*` | Вызывается из |
|---|---:|---|---|---|
| `trim_text()` | 14-24 | Обрезает длинный текст, сохраняя важное начало или окончание. | — | `_split_file_into_stage`, `diagnostic_excerpt`, `get_audio_info`, `process_single_folder`, `record_diagnostic_failure`, `sanitize_problem_value`, `write_problem` |
| `diagnostic_excerpt()` | 26-71 | Убирает из вывода FFmpeg повторяющийся служебный шум и оставляет причину. | `trim_text` | `sanitize_problem_value` |
| `normalize_returncode()` | 73-77 | Преобразует беззнаковый Windows-код FFmpeg в обычное отрицательное число. | — | `process_single_folder`, `run_process`, `write_problem` |
| `ensure_windows_child_error_mode()` | 79-105 | Не даёт Windows Error Reporting удерживать упавшие FFmpeg и их файлы. | — | `run_process` |
| `is_libmp3lame_joint_stereo_assertion()` | 107-116 | Распознаёт фатальный assertion LAME, после которого процесс может зависнуть в Windows. | — | `diagnose_ffmpeg_failure`, `run_process` |
| `diagnose_ffmpeg_failure()` | 118-283 | Классифицирует типовые причины FFmpeg и даёт Codex направление исправления. | `is_libmp3lame_joint_stereo_assertion`, `path_facts` | `convert_single_file` |
| `ffmpeg_base_command()` | 285-292 | Базовые параметры FFmpeg без баннера, прогресса и многомегабайтного шума. | — | `_split_file_into_stage`, `build_video_normalize_command`, `concat_video_files_copy`, `convert_single_file`, `process_single_folder` |
| `extract_duration_seconds()` | 294-307 | Достаёт числовую длительность из вывода ffprobe, даже если вывод лежит в process-log. | — | — |
| `command_to_text()` | 309-318 | Пишет команду ffmpeg/ffprobe в понятном виде без запуска через shell. | — | `_split_file_into_stage`, `convert_single_file`, `get_audio_info`, `process_single_folder`, `run_process`, `write_problem` |

### `videovaudio/core/paths.py`

| Метод | Строки | Что делает | Вызывает `self.*` | Вызывается из |
|---|---:|---|---|---|
| `path_facts()` | 14-42 | Компактные факты о пути, полезные при ошибках доступа и длинных путях. | — | `convert_single_file`, `diagnose_ffmpeg_failure`, `process_single_folder` |
| `build_output_path()` | 44-53 | Формирует понятное имя результата, но не превышает безопасную длину пути. | `safe_output_stem` | `build_audio_split_output_path`, `convert_single_file` |
| `build_audio_split_output_path()` | 55-73 | Именует одиночный MP3 по курсу, а набор — пронумерованными частями. | `build_output_path`, `safe_output_stem` | `_split_file_into_stage`, `process_single_folder` |
| `read_text_tail()` | 75-92 | Читает хвост большого лога процесса без риска загрузить гигабайтный файл. | — | `run_process` |
| `safe_log_fragment()` | 94-100 | Безопасный фрагмент имени файла для логов ffmpeg/ffprobe. | — | `concat_video_files_copy`, `make_process_log_path`, `process_video_folder`, `save_concat_input_manifest` |
| `safe_output_stem()` | 102-109 | Безопасное имя MP3 без слишком длинных путей Windows. | — | `build_audio_split_output_path`, `build_output_path` |
| `normalize_folder_key()` | 111-113 | Ключ для сравнения путей очереди без дублей вида C:\A и c:\a\. | — | `_add_folder_to_queue`, `_remove_duplicates`, `process_queue`, `process_video_queue` |
| `normalize_folder_path()` | 115-117 | Возвращает единый абсолютный Windows-путь для очереди и логов. | — | `_add_folder_to_queue`, `process_single_folder`, `process_video_folder`, `scan_media_files` |
| `escape_concat_path()` | 119-122 | Экранирует путь для ffmpeg concat demuxer. | — | `concat_video_files_copy`, `process_single_folder` |

### `videovaudio/diagnostics/codex_report.py`

| Метод | Строки | Что делает | Вызывает `self.*` | Вызывается из |
|---|---:|---|---|---|
| `diagnostic_status_counts()` | 16-29 | Считает восстановленные, ожидаемые и нерешённые события. | — | `build_health_record`, `diagnostics_integrity`, `run_index_payload`, `save_run_summary` |
| `compact_event_for_report()` | 31-62 | Оставляет в Codex-отчёте только поля, нужные для приоритизации. | — | `build_codex_report` |
| `build_codex_report()` | 64-315 | Формирует конкретный порядок анализа, а не общий список советов. | `compact_event_for_report`, `diagnostic_health_snapshot`, `read_recent_health_records` | `save_run_summary` |

### `videovaudio/diagnostics/common.py`

| Метод | Строки | Что делает | Вызывает `self.*` | Вызывается из |
|---|---:|---|---|---|
| `now_iso()` | 23-25 | Локальное время с часовым поясом для сопоставления разных компьютеров. | — | `begin_run_diagnostics`, `build_health_record`, `finish_active_run`, `install_exception_hooks`, `on_close`, `process_queue`, `process_single_folder`, `process_video_folder`, `process_video_queue`, `record_diagnostic_failure`, `run_index_payload`, `run_process`, `setup_logging`, `update_active_state`, `write_problem` |
| `utc_now_iso()` | 27-29 | UTC-время события для машинной сортировки. | — | `begin_run_diagnostics`, `finish_active_run`, `on_close`, `run_index_payload`, `setup_logging`, `update_active_state`, `write_problem` |
| `sha256_file()` | 31-40 | Потоково вычисляет отпечаток программы без загрузки файла целиком. | — | `get_source_identity` |

### `videovaudio/diagnostics/events.py`

| Метод | Строки | Что делает | Вызывает `self.*` | Вызывается из |
|---|---:|---|---|---|
| `problem_guidance()` | 23-81 | Единые пояснения, чтобы Codex видел влияние и следующий шаг. | — | `write_problem` |
| `sanitize_problem_value()` | 83-128 | Не даёт одной ошибке раздуть JSONL до мегабайт. | `diagnostic_excerpt`, `sanitize_problem_value`, `trim_text` | `sanitize_problem_value`, `write_problem` |
| `error_signature()` | 130-164 | Стабильная сигнатура группирует одинаковые сбои без привязки к путям. | — | `write_problem` |
| `default_resolution_status()` | 166-178 | Отделяет реальные дефекты программы от ожидаемых пропусков и повторов. | — | `write_problem` |
| `write_problem()` | 180-396 | Записывает структурированное событие, дедуплицирует повторы и возвращает event_id. | `command_to_text`, `default_resolution_status`, `error_signature`, `normalize_returncode`, `now_iso`, `problem_guidance`, `record_diagnostic_failure`, `resource_snapshot`, `sanitize_problem_value`, `trim_text`, `utc_now_iso` | `__init__`, `_split_file_into_stage`, `convert_single_file`, `create_video_group_output`, `get_audio_info`, `get_video_info`, `install_exception_hooks`, `mark_problem_recovered`, `mark_problem_unresolved`, `normalize_video_file`, `process_queue`, `process_single_folder`, `process_video_folder`, `process_video_queue`, `run_process`, `save_run_summary`, `scan_media_files`, `setup_logging`, `split_file`, `split_long_video_to_outputs`, `start`, `start_video_merge` |
| `mark_problem_recovered()` | 398-412 | Связывает исходную проблему с успешным результатом повторной попытки. | `write_problem` | `_split_file_into_stage`, `convert_single_file`, `create_video_group_output`, `process_single_folder` |
| `mark_problem_unresolved()` | 414-428 | Фиксирует неуспешное восстановление с привязкой к исходному событию. | `write_problem` | `_split_file_into_stage`, `convert_single_file`, `create_video_group_output`, `process_single_folder` |

### `videovaudio/diagnostics/health.py`

| Метод | Строки | Что делает | Вызывает `self.*` | Вызывается из |
|---|---:|---|---|---|
| `read_recent_health_records()` | 16-35 | Читает небольшой хвост истории качества без загрузки лишних данных. | — | `append_health_record`, `build_codex_report` |
| `build_health_record()` | 37-148 | Одна компактная строка на запуск для поиска регрессий. | `diagnostic_status_counts`, `get_log_storage_stats`, `now_iso` | `save_run_summary` |
| `append_health_record()` | 150-172 | Хранит до 120 дней компактной истории качества. | `atomic_write_text`, `read_recent_health_records` | `save_run_summary` |

### `videovaudio/diagnostics/integrity.py`

| Метод | Строки | Что делает | Вызывает `self.*` | Вызывается из |
|---|---:|---|---|---|
| `diagnostics_integrity()` | 16-243 | Проверяет синтаксис файлов и смысловую согласованность итогов. | `diagnostic_health_snapshot`, `diagnostic_status_counts` | `save_run_summary` |

### `videovaudio/diagnostics/io_health.py`

| Метод | Строки | Что делает | Вызывает `self.*` | Вызывается из |
|---|---:|---|---|---|
| `ensure_diagnostic_io_state()` | 23-32 | Лениво создаёт блокировки и счётчики для служебной диагностики. | — | `diagnostic_health_snapshot`, `record_diagnostic_failure`, `record_diagnostic_retry`, `reset_run_diagnostics`, `update_active_state` |
| `active_state_temp_files()` | 34-58 | Возвращает только временные файлы active_run_state этой программы. | — | `diagnostic_health_snapshot` |
| `record_diagnostic_failure()` | 60-110 | Агрегирует сбои самой диагностики без рекурсивной записи в JSONL. | `ensure_diagnostic_io_state`, `now_iso`, `trim_text` | `cleanup_own_atomic_temp`, `update_active_state`, `write_problem` |
| `record_diagnostic_retry()` | 112-118 | Считает успешные повторы атомарной замены без лишних строк лога. | `ensure_diagnostic_io_state` | `update_active_state` |
| `diagnostic_health_snapshot()` | 120-155 | Формирует компактный итог надёжности служебных файлов запуска. | `active_state_temp_files`, `ensure_diagnostic_io_state` | `build_codex_report`, `diagnostics_integrity`, `save_run_summary` |

### `videovaudio/diagnostics/lifecycle.py`

| Метод | Строки | Что делает | Вызывает `self.*` | Вызывается из |
|---|---:|---|---|---|
| `update_active_state()` | 23-96 | Атомарно обновляет небольшой снимок выполняемой операции. | `atomic_write_json`, `ensure_diagnostic_io_state`, `now_iso`, `record_diagnostic_failure`, `record_diagnostic_retry`, `utc_now_iso` | `finish_active_run`, `heartbeat_loop`, `install_exception_hooks`, `on_close`, `process_queue`, `process_single_folder`, `process_video_folder`, `process_video_queue`, `run_process`, `setup_logging` |
| `heartbeat_loop()` | 98-104 | Перезаписывает active_run_state.json, не создавая растущий лог. | `sample_run_resources`, `update_active_state` | — |
| `start_heartbeat()` | 106-119 | Запускает один фоновый heartbeat на время очереди. | — | `process_queue`, `process_video_queue` |
| `stop_heartbeat()` | 121-132 | Останавливает heartbeat до записи окончательного состояния. | — | `finish_active_run`, `on_close` |
| `clear_active_transient_state()` | 134-163 | Убирает временные пути и PID после завершения, оставляя краткий итог. | — | `finish_active_run`, `on_close` |
| `finish_active_run()` | 165-176 | Фиксирует терминальное состояние и останавливает heartbeat. | `clear_active_transient_state`, `now_iso`, `stop_heartbeat`, `update_active_state`, `utc_now_iso` | `on_close`, `process_queue`, `process_video_queue` |
| `install_exception_hooks()` | 178-271 | Ловит необработанные ошибки главного, Tkinter и рабочих потоков. | `now_iso`, `original_sys_excepthook`, `original_threading_excepthook`, `update_active_state`, `write_problem` | `__init__` |
| `on_close()` | 273-332 | Корректно помечает обычное закрытие, чтобы не спутать его с падением. | `clear_active_transient_state`, `finish_active_run`, `now_iso`, `request_cancel`, `stop_heartbeat`, `terminate_active_processes`, `update_active_state`, `update_current_session`, `utc_now_iso` | — |

### `videovaudio/diagnostics/resources.py`

| Метод | Строки | Что делает | Вызывает `self.*` | Вызывается из |
|---|---:|---|---|---|
| `system_resource_sample()` | 23-108 | Снимает память, CPU и свободное место без внешних зависимостей. | — | `resource_snapshot`, `sample_run_resources` |
| `resource_snapshot()` | 110-118 | Компактные ресурсы системы в момент проблемы. | `system_resource_sample` | `write_problem` |
| `reset_run_resource_metrics()` | 120-137 | Начинает компактное агрегирование ресурсов для текущей очереди. | `sample_run_resources` | `process_queue`, `process_video_queue` |
| `sample_run_resources()` | 139-219 | Обновляет агрегаты; отдельные heartbeat-снимки в лог не добавляет. | `system_resource_sample` | `heartbeat_loop`, `reset_run_resource_metrics`, `run_resource_metrics_summary` |
| `run_resource_metrics_summary()` | 221-269 | Возвращает только итоговые агрегаты, сохраняя лог маленьким. | `sample_run_resources` | `process_queue`, `process_video_queue` |

### `videovaudio/diagnostics/run_reports.py`

| Метод | Строки | Что делает | Вызывает `self.*` | Вызывается из |
|---|---:|---|---|---|
| `reset_run_diagnostics()` | 16-28 | Начинает независимый набор событий для новой очереди. | `ensure_diagnostic_io_state` | `begin_run_diagnostics` |
| `begin_run_diagnostics()` | 30-67 | Создаёт отдельные problem/summary/report-файлы для текущего run_id. | `atomic_write_json`, `atomic_write_text`, `now_iso`, `reset_run_diagnostics`, `utc_now_iso` | `process_queue`, `process_video_queue` |
| `run_index_payload()` | 69-141 | Компактный индекс файлов и итоговых счётчиков запуска. | `diagnostic_status_counts`, `now_iso`, `utc_now_iso` | `update_current_session`, `update_latest_run` |
| `update_current_session()` | 143-150 | Обновляет состояние открытого приложения, не затирая последний итог. | `atomic_write_json`, `run_index_payload` | `on_close`, `process_queue`, `process_video_queue`, `setup_logging`, `update_latest_run` |
| `update_latest_run()` | 152-157 | Сохраняет постоянный указатель только на завершённый запуск. | `atomic_write_json`, `run_index_payload`, `update_current_session` | `save_run_summary` |
| `build_markdown_report()` | 159-307 | Формирует короткий человекочитаемый итог без тяжёлой диагностики. | — | `save_run_summary` |
| `save_run_summary()` | 309-389 | Сохраняет итог запуска в JSON, чтобы нейросети было легко понять состояние. | `append_health_record`, `atomic_write_json`, `atomic_write_text`, `build_codex_report`, `build_health_record`, `build_markdown_report`, `diagnostic_health_snapshot`, `diagnostic_status_counts`, `diagnostics_integrity`, `get_log_storage_stats`, `update_latest_run`, `write_problem` | `process_queue`, `process_video_queue` |

### `videovaudio/dialogs.py`

| Метод | Строки | Что делает | Вызывает `self.*` | Вызывается из |
|---|---:|---|---|---|
| `browse_folder()` | 95-99 | Выбор базовой папки для просмотра | `load_folders` | — |
| `load_folders()` | 101-122 | Загрузка папок из выбранного пути | — | `__init__`, `browse_folder` |
| `on_selection_changed()` | 124-127 | Обновление информации о выборе | — | — |
| `select_all()` | 129-132 | Выбрать все папки | — | — |
| `deselect_all()` | 134-136 | Снять выбор со всех папок | — | — |
| `add_selected()` | 138-218 | Добавить выбранные папки в очередь | — | — |

### `videovaudio/notifications.py`

| Метод | Строки | Что делает | Вызывает `self.*` | Вызывается из |
|---|---:|---|---|---|
| `show()` | 48-102 |  | `open_file` | — |
| `open_file()` | 104-110 |  | — | `show` |
| `close()` | 112-114 |  | — | — |

### `videovaudio/process_runner.py`

| Метод | Строки | Что делает | Вызывает `self.*` | Вызывается из |
|---|---:|---|---|---|
| `compact_process_log()` | 16-47 | Ограничивает сохранённый ошибочный вывод процесса без потери начала и хвоста. | — | `run_process` |
| `remove_success_process_log()` | 49-60 | Успешный служебный вывод не хранится: полезные метрики уже есть в итоговом JSON. | — | `run_process` |
| `make_process_log_path()` | 62-70 | Создаёт отдельный файл под полный вывод конкретного процесса. | `safe_log_fragment` | `run_process` |
| `completed_process()` | 72-77 | CompletedProcess с метаданными, нужными для диагностики Codex. | — | `run_process` |
| `terminate_process()` | 79-104 | Мгновенно останавливает ffmpeg/ffprobe процесс и дочерние процессы. | — | `run_process`, `terminate_active_processes` |
| `terminate_active_processes()` | 106-112 | Останавливает все текущие ffmpeg-процессы при нажатии отмены. | `terminate_process` | `done`, `on_close`, `request_cancel` |
| `request_cancel()` | 114-121 | Обработчик кнопки отмены. | `log_message`, `set_status`, `terminate_active_processes` | `on_close` |
| `run_process()` | 123-380 | Запускает процесс без PIPE-зависаний; хранит полный вывод только при сбое. | `command_to_text`, `compact_process_log`, `completed_process`, `ensure_windows_child_error_mode`, `is_libmp3lame_joint_stereo_assertion`, `make_process_log_path`, `normalize_returncode`, `now_iso`, `read_text_tail`, `remove_success_process_log`, `terminate_process`, `update_active_state`, `write_problem` | `_split_file_into_stage`, `concat_video_files_copy`, `convert_single_file`, `get_audio_info`, `get_video_info`, `normalize_video_file`, `process_single_folder`, `split_long_video_to_outputs` |

### `videovaudio/queues.py`

| Метод | Строки | Что делает | Вызывает `self.*` | Вызывается из |
|---|---:|---|---|---|
| `guard_queue_edit()` | 14-22 | Запрещает менять очередь во время фоновой обработки. | — | `_add_folder_to_queue`, `_clear_queue`, `_remove_duplicates`, `_remove_selected_from_queue`, `add_multiple_folders`, `add_multiple_video_folders` |
| `set_queue_controls_state()` | 24-27 | Включить/выключить кнопки изменения очереди. | — | `done`, `start`, `start_video_merge` |
| `set_video_settings_state()` | 29-33 | Блокирует настройки на время любой фоновой обработки. | — | `done`, `start`, `start_video_merge` |
| `capture_video_settings()` | 35-51 | Проверяет и фиксирует настройки до запуска рабочего потока. | — | `start_video_merge` |
| `get_folder_queue()` | 53-57 | Возвращает независимую очередь выбранного режима. | — | `_add_folder_to_queue`, `_clear_queue`, `_remove_duplicates`, `_remove_selected_from_queue`, `update_queue_display` |
| `get_queue_widgets()` | 59-63 | Возвращает список и информационную строку нужной вкладки. | — | `_remove_selected_from_queue`, `update_queue_display` |
| `_add_folder_to_queue()` | 65-108 |  | `get_folder_queue`, `guard_queue_edit`, `log_message`, `normalize_folder_key`, `normalize_folder_path`, `scan_media_files`, `update_queue_display` | `add_folder_to_queue`, `add_video_folder_to_queue` |
| `add_folder_to_queue()` | 110-112 | Добавить одну папку в очередь | `_add_folder_to_queue` | — |
| `add_video_folder_to_queue()` | 114-116 | Добавить папку курса в очередь объединения видео. | `_add_folder_to_queue` | — |
| `add_multiple_folders()` | 118-123 | Добавить несколько папок через кастомное окно выбора | `guard_queue_edit` | — |
| `add_multiple_video_folders()` | 125-129 | Добавить несколько курсов в очередь объединения видео. | `guard_queue_edit` | — |
| `_remove_selected_from_queue()` | 131-147 |  | `get_folder_queue`, `get_queue_widgets`, `guard_queue_edit`, `log_message`, `update_queue_display` | `remove_selected_from_queue`, `remove_selected_from_video_queue` |
| `remove_selected_from_queue()` | 149-151 | Удалить выбранные папки из очереди | `_remove_selected_from_queue` | — |
| `remove_selected_from_video_queue()` | 153-155 | Удалить выбранные курсы из видео-очереди. | `_remove_selected_from_queue` | — |
| `_clear_queue()` | 157-171 |  | `get_folder_queue`, `guard_queue_edit`, `log_message`, `update_queue_display` | `clear_queue`, `clear_video_queue` |
| `clear_queue()` | 173-175 | Очистить всю очередь | `_clear_queue` | — |
| `clear_video_queue()` | 177-179 | Очистить очередь объединения видео. | `_clear_queue` | — |
| `_remove_duplicates()` | 181-225 |  | `get_folder_queue`, `guard_queue_edit`, `log_message`, `normalize_folder_key`, `update_queue_display` | `remove_duplicates`, `remove_video_duplicates` |
| `remove_duplicates()` | 227-229 | Удалить дубликаты и несуществующие папки из очереди | `_remove_duplicates` | — |
| `remove_video_duplicates()` | 231-233 | Очистить видео-очередь от дубликатов и пропавших папок. | `_remove_duplicates` | — |
| `update_queue_display()` | 235-260 | Обновить отображение очереди | `get_files`, `get_folder_queue`, `get_queue_widgets` | `_add_folder_to_queue`, `_clear_queue`, `_remove_duplicates`, `_remove_selected_from_queue`, `process_video_queue` |

### `videovaudio/run/audio.py`

| Метод | Строки | Что делает | Вызывает `self.*` | Вызывается из |
|---|---:|---|---|---|
| `process_queue()` | 18-325 | Обработка всей очереди папок по снимку очереди на момент старта. | `begin_run_diagnostics`, `finish_active_run`, `log_message`, `normalize_folder_key`, `now_iso`, `process_single_folder`, `reset_run_resource_metrics`, `run_resource_metrics_summary`, `save_run_summary`, `start_heartbeat`, `ui_after`, `update_active_state`, `update_current_session`, `write_problem` | — |
| `start()` | 327-366 |  | `log_message`, `set_queue_controls_state`, `set_status`, `set_video_settings_state`, `write_problem` | — |

### `videovaudio/run/lifecycle.py`

| Метод | Строки | Что делает | Вызывает `self.*` | Вызывается из |
|---|---:|---|---|---|
| `done()` | 18-51 |  | `set_queue_controls_state`, `set_status`, `set_video_settings_state`, `show_completion_notification`, `terminate_active_processes`, `update_progress` | — |

### `videovaudio/run/video.py`

| Метод | Строки | Что делает | Вызывает `self.*` | Вызывается из |
|---|---:|---|---|---|
| `process_video_queue()` | 18-238 | Фоновая обработка независимой очереди объединения видео. | `begin_run_diagnostics`, `finish_active_run`, `log_message`, `normalize_folder_key`, `now_iso`, `process_video_folder`, `reset_run_resource_metrics`, `run_resource_metrics_summary`, `save_run_summary`, `start_heartbeat`, `ui_after`, `update_active_state`, `update_current_session`, `update_queue_display`, `write_problem` | — |
| `start_video_merge()` | 240-301 | Запускает независимую очередь объединения видео. | `capture_video_settings`, `log_message`, `set_queue_controls_state`, `set_status`, `set_video_settings_state`, `write_problem` | — |

### `videovaudio/storage/atomic.py`

| Метод | Строки | Что делает | Вызывает `self.*` | Вызывается из |
|---|---:|---|---|---|
| `is_retryable_atomic_replace_error()` | 26-32 | Определяет временные блокировки файла, характерные для Windows. | — | `atomic_replace_with_retry` |
| `atomic_replace_with_retry()` | 34-49 | Ограниченно повторяет атомарную замену при временной блокировке. | `is_retryable_atomic_replace_error` | `atomic_write_json`, `atomic_write_text`, `publish_video_outputs` |
| `cleanup_own_atomic_temp()` | 51-62 | Удаляет только временный файл текущей операции записи. | `record_diagnostic_failure` | `atomic_write_json`, `atomic_write_text` |
| `atomic_write_json()` | 64-77 | Записывает важный JSON через временный файл и атомарную замену. | `atomic_replace_with_retry`, `cleanup_own_atomic_temp` | `begin_run_diagnostics`, `save_concat_input_manifest`, `save_run_summary`, `setup_logging`, `update_active_state`, `update_current_session`, `update_latest_run` |
| `atomic_write_text()` | 79-92 | Атомарно сохраняет небольшой текстовый служебный файл. | `atomic_replace_with_retry`, `cleanup_own_atomic_temp` | `append_health_record`, `begin_run_diagnostics`, `save_run_summary`, `write_schema_guide` |
| `read_json_file()` | 94-101 | Безопасно читает JSON, возвращая пустой словарь при повреждении. | — | `setup_logging` |

### `videovaudio/storage/logging_setup.py`

| Метод | Строки | Что делает | Вызывает `self.*` | Вызывается из |
|---|---:|---|---|---|
| `write_schema_guide()` | 26-83 | Пишет стабильную краткую карту диагностических файлов для Codex. | `atomic_write_text` | `setup_logging` |
| `setup_logging()` | 85-332 | Создаёт компактные логи проблем рядом с программой. | `atomic_write_json`, `cleanup_old_problem_logs`, `cleanup_stale_atomic_temp_files`, `cleanup_unreferenced_process_logs`, `compress_old_detailed_logs`, `get_runtime_context`, `now_iso`, `read_json_file`, `update_active_state`, `update_current_session`, `utc_now_iso`, `write_problem`, `write_schema_guide` | `__init__` |

### `videovaudio/storage/maintenance.py`

| Метод | Строки | Что делает | Вызывает `self.*` | Вызывается из |
|---|---:|---|---|---|
| `compress_old_detailed_logs()` | 26-104 | Сжимает старые подробные текстовые логи, сохраняя имена ссылок через .gz. | — | `setup_logging` |
| `is_process_running()` | 106-160 | Без сторонних зависимостей проверяет, существует ли процесс. | — | `cleanup_stale_atomic_temp_files` |
| `cleanup_stale_atomic_temp_files()` | 162-215 | Удаляет старые временные active-state файлы только мёртвых процессов. | `is_process_running` | `setup_logging` |
| `cleanup_old_problem_logs()` | 217-266 | Удаляет только журналы этой программы старше 120 дней. | — | `setup_logging` |
| `collect_referenced_process_logs()` | 268-298 | Находит process-log, на которые ссылаются реальные проблемные события. | — | `cleanup_unreferenced_process_logs` |
| `cleanup_unreferenced_process_logs()` | 300-337 | Удаляет старые логи успешных процессов, оставляя детали реальных проблем. | `collect_referenced_process_logs` | `setup_logging` |

### `videovaudio/storage/media_scan.py`

| Метод | Строки | Что делает | Вызывает `self.*` | Вызывается из |
|---|---:|---|---|---|
| `natural_sort_key()` | 26-29 | Естественная сортировка: 1, 2, 10 вместо 1, 10, 2. | — | — |
| `scan_media_files()` | 31-125 | Сканирует видео и отдельно сообщает ошибки чтения. | `normalize_folder_path`, `write_problem` | `_add_folder_to_queue`, `get_files`, `process_single_folder`, `process_video_folder` |
| `get_files()` | 127-132 | Возвращает видео для интерфейса без записи диагностических событий. | `scan_media_files` | `update_queue_display` |

### `videovaudio/storage/runtime.py`

| Метод | Строки | Что делает | Вызывает `self.*` | Вызывается из |
|---|---:|---|---|---|
| `get_tool_version()` | 26-44 | Читает только первую строку версии без создания отдельного process-log. | — | `get_runtime_context` |
| `get_source_identity()` | 46-118 | Хэширует весь модульный source tree, чтобы build_id менялся вместе с кодом. | `sha256_file` | `get_runtime_context` |
| `get_runtime_context()` | 120-167 |  | `get_source_identity`, `get_tool_version` | `setup_logging` |
| `get_log_storage_stats()` | 169-220 |  | — | `build_health_record`, `save_run_summary` |

### `videovaudio/ui.py`

| Метод | Строки | Что делает | Вызывает `self.*` | Вызывается из |
|---|---:|---|---|---|
| `show_completion_notification()` | 14-18 | Показать постоянное уведомление; вызывается из UI-потока. | — | `done` |
| `create_interface()` | 20-262 |  | — | `__init__` |
| `ui_after()` | 264-275 | Безопасно планирует действие в Tkinter, даже если окно уже закрывается. | — | `log_message`, `process_queue`, `process_single_folder`, `process_video_folder`, `process_video_queue`, `set_status`, `update_progress` |
| `log_message()` | 277-291 | Пишет сообщение в окно; повторяющиеся успехи можно не сохранять в файл. | `ui_after` | `_add_folder_to_queue`, `_clear_queue`, `_remove_duplicates`, `_remove_selected_from_queue`, `_split_file_into_stage`, `create_video_group_output`, `process_queue`, `process_single_folder`, `process_video_folder`, `process_video_queue`, `request_cancel`, `start`, `start_video_merge` |
| `set_status()` | 293-294 |  | `ui_after` | `done`, `process_single_folder`, `process_video_folder`, `request_cancel`, `start`, `start_video_merge` |
| `update_progress()` | 296-297 |  | `ui_after` | `_split_file_into_stage`, `done`, `process_single_folder`, `process_video_folder` |

### `videovaudio/video/folder_workflow.py`

| Метод | Строки | Что делает | Вызывает `self.*` | Вызывается из |
|---|---:|---|---|---|
| `process_video_folder()` | 16-369 | Объединяет один курс в проверенные MP4-части до 10 часов. | `build_video_groups`, `choose_video_target_profile`, `create_video_group_output`, `format_duration`, `get_video_info`, `log_message`, `normalize_folder_path`, `now_iso`, `publish_video_outputs`, `safe_log_fragment`, `scan_media_files`, `set_status`, `split_long_video_to_outputs`, `ui_after`, `update_active_state`, `update_progress`, `write_problem` | `process_video_queue` |

### `videovaudio/video/operations.py`

| Метод | Строки | Что делает | Вызывает `self.*` | Вызывается из |
|---|---:|---|---|---|
| `concat_video_files_copy()` | 16-46 | Быстро склеивает уже совместимые MP4 без потери качества. | `escape_concat_path`, `ffmpeg_base_command`, `run_process`, `safe_log_fragment` | `create_video_group_output` |
| `normalize_video_file()` | 48-88 | Нормализует один ролик и проверяет, что его содержимое не потеряно. | `build_video_normalize_command`, `run_process`, `validate_merged_video`, `write_problem` | `create_video_group_output` |
| `create_video_group_output()` | 90-224 | Создаёт одну часть: copy при совместимости, иначе нормализация. | `concat_video_files_copy`, `log_message`, `mark_problem_recovered`, `mark_problem_unresolved`, `normalize_video_file`, `validate_merged_video`, `video_group_can_copy`, `write_problem` | `process_video_folder` |
| `split_long_video_to_outputs()` | 226-318 | Перекодирует одиночное видео длиннее лимита сразу в части ≤10 часов. | `build_video_normalize_command`, `duration_mismatch`, `get_video_info`, `run_process`, `validate_merged_video`, `write_problem` | `process_video_folder` |
| `build_video_groups()` | 320-343 | Укладывает целые уроки в части до 10 часов без разреза между кадрами. | — | `process_video_folder` |
| `publish_video_outputs()` | 345-395 | Публикует только проверенный полный набор с rollback старых частей. | `atomic_replace_with_retry` | `process_video_folder` |

### `videovaudio/video/profile.py`

| Метод | Строки | Что делает | Вызывает `self.*` | Вызывается из |
|---|---:|---|---|---|
| `parse_frame_rate()` | 16-29 | Преобразует ffprobe-частоту вида 30000/1001 в число. | — | `choose_video_target_profile` |
| `get_video_info()` | 31-170 | Читает длительность и параметры первого видео/аудиопотока. | `extract_ffprobe_json`, `run_process`, `write_problem` | `process_video_folder`, `split_long_video_to_outputs`, `validate_merged_video` |
| `video_stream_copy_key()` | 172-188 | Параметры, которые должны совпасть для безопасной быстрой склейки. | — | `video_group_can_copy` |
| `video_group_can_copy()` | 190-204 | Разрешает copy только для одинаковых, интернет-совместимых MP4-потоков. | `video_stream_copy_key` | `create_video_group_output` |
| `choose_video_target_profile()` | 206-251 | Формирует единый профиль из настроек и частоты кадров курса. | `parse_frame_rate` | `process_video_folder` |
| `video_filter_for_target()` | 253-262 |  | — | `build_video_normalize_command` |
| `build_video_normalize_command()` | 264-313 | Строит единый H.264/AAC профиль, добавляя тишину при отсутствии звука. | `ffmpeg_base_command`, `video_filter_for_target` | `normalize_video_file`, `split_long_video_to_outputs` |
| `validate_merged_video()` | 315-369 | Проверяет контейнер, кодеки, длительность и лимит готовой части. | `duration_mismatch`, `get_video_info` | `create_video_group_output`, `normalize_video_file`, `split_long_video_to_outputs` |
