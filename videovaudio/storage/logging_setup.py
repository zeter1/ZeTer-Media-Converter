"""Session directories, Python logging and diagnostic artifact setup.

CODEX ROUTE: open this file only when the task matches this responsibility.
Methods are moved whole from the previous owner module; behavior is intentionally unchanged.
"""

import os
import sys
import re
import threading
import subprocess
import time
import logging
import platform
import hashlib
import gzip
import uuid
from collections import Counter
from datetime import datetime, timedelta
import json
import shutil
from shutil import which


class LoggingSetupMixin:
    def write_schema_guide(self):
        """Пишет стабильную краткую карту диагностических файлов для Codex."""
        guide = f"""# Диагностика {self.APP_NAME}

Версия схемы: {self.LOG_SCHEMA_VERSION}
Хранение: {self.PROBLEM_LOG_RETENTION_DAYS} дней.

## С чего начать

1. Откройте `latest_problem_summary.md` для короткого человеческого итога.
2. Затем откройте `latest_run.json` и указанный там `summary_file`.
3. Сначала изучите `codex_report.confirmed_bugs` и `recommended_review_order`.
4. `expected_skip` с уровнем `info` означает видео без звука или папку без видео. Проблемные
   повреждённые файлы остаются `warning`; исправные видео продолжают обработку.
5. Для подробностей найдите `event_id` в `problem_file`.

## Файлы

- `latest_run.json` и `latest_completed_run.json` — постоянные ссылки на
  последний завершённый запуск; простое открытие приложения их не затирает.
- `current_session.json` — состояние текущего открытого приложения или очереди.
- `latest_problem_summary.md` — короткий читаемый итог последнего запуска.
- `active_run_state.json` — перезаписываемый heartbeat текущего этапа и процессов.
- `summary_*.json` — отдельный итог каждого `run_id`, метрики этапов/ресурсов,
  проверки длительности и Codex-отчёт.
- `report_*.md` — короткий читаемый отчёт конкретного запуска.
- `problems_*.jsonl` — отдельные структурированные события каждого `run_id`.
- `conversion_*.log` — короткая человекочитаемая хронология.
- `process_output/*.log[.gz]` — ограниченный вывод FFmpeg/FFprobe только для
  ошибок и очень медленных процессов.
- `process_output/concat_manifest_*.json` — полный порядок и ожидаемые границы
  входов; создаётся только при проблеме склейки.
- `health_history.jsonl` — одна компактная строка на запуск для регрессий.
- `crash_*.log[.gz]` — только реальные аварийные стеки низкого уровня;
  пустой служебный файл удаляется при нормальном закрытии.

## Связи и статусы

- `session_id` обозначает запуск приложения, `run_id` — конкретный запуск очереди.
- `event_id` и `attempt_id` идентифицируют событие/попытку.
- `parent_event_id` связывает fallback с исходной проблемой.
- `resolution_status`: `unresolved`, `retrying`, `recovered`, `expected_skip`.
- `error_signature` объединяет одинаковые причины; после
  {self.MAX_DETAILED_EVENTS_PER_SIGNATURE} полных событий повторы считаются в
  сводке без раздувания JSONL.
- Для ожидаемого `info`-пропуска хранится не более
  {self.MAX_EXPECTED_SKIP_DETAILS_PER_SIGNATURE} компактной подробной записи
  на сигнатуру; полный список остаётся в итогах папок.
- `diagnostics_integrity.structural_ok` проверяет JSON и ссылки, а
  `semantic_ok` — согласованность статуса и счётчиков.
- `diagnostic_health.diagnostics_degraded` показывает сбои записи служебных
  файлов; `diagnostics_integrity.operational_ok` учитывает эту надёжность.
- Ссылка на `.log` может физически находиться как `.log.gz` после
  {self.COMPRESS_DETAILED_LOGS_AFTER_DAYS} дней.

Секреты и переменные окружения целиком в диагностику не записываются.
"""
        self.atomic_write_text(self.schema_guide_file, guide)

    def setup_logging(self):
        """Создаёт компактные логи проблем рядом с программой."""
        if not hasattr(self, "log_lock"):
            self.log_lock = threading.Lock()
        if not hasattr(self, "process_lock"):
            self.process_lock = threading.Lock()
        if not hasattr(self, "state_lock"):
            self.state_lock = threading.Lock()
        if not hasattr(self, "active_state_write_lock"):
            self.active_state_write_lock = threading.Lock()
        if not hasattr(self, "diagnostic_failure_lock"):
            self.diagnostic_failure_lock = threading.Lock()
        if not hasattr(self, "resource_metrics_lock"):
            self.resource_metrics_lock = threading.Lock()
        if not hasattr(self, "run_resource_metrics"):
            self.run_resource_metrics = {}
        if not hasattr(self, "previous_cpu_times"):
            self.previous_cpu_times = None
        if not hasattr(self, "crash_log_initial_size"):
            self.crash_log_initial_size = 0
        if not hasattr(self, "session_started_monotonic"):
            self.session_started_monotonic = time.monotonic()

        if getattr(sys, "frozen", False):
            self.app_dir = os.path.dirname(os.path.abspath(sys.executable))
        else:
            self.app_dir = os.path.dirname(
                os.path.dirname(os.path.abspath(__file__))
            )

        self.log_dir = os.path.join(self.app_dir, "Логи проблем")
        self.process_output_dir = os.path.join(self.log_dir, "process_output")
        os.makedirs(self.log_dir, exist_ok=True)
        os.makedirs(self.process_output_dir, exist_ok=True)
        self.active_state_file = os.path.join(
            self.log_dir,
            "active_run_state.json",
        )
        self.latest_run_file = os.path.join(self.log_dir, "latest_run.json")
        self.latest_completed_run_file = os.path.join(
            self.log_dir,
            "latest_completed_run.json",
        )
        self.current_session_file = os.path.join(
            self.log_dir,
            "current_session.json",
        )
        self.latest_problem_summary_file = os.path.join(
            self.log_dir,
            "latest_problem_summary.md",
        )
        self.health_history_file = os.path.join(
            self.log_dir,
            "health_history.jsonl",
        )
        self.schema_guide_file = os.path.join(
            self.log_dir,
            "README_FOR_CODEX.md",
        )
        previous_active_state = self.read_json_file(self.active_state_file)

        self.process_log_counter = 0
        self.problem_counter = 0
        self.problem_counts = Counter()
        self.problem_severity_counts = Counter()
        self.codex_priorities = {}
        self.problem_signature_stats = {}
        self.event_records = {}
        self.event_status = {}
        self.process_contexts = {}
        self.diagnostic_failures = {}
        self.diagnostic_retry_counts = Counter()
        self.active_state = {}
        if not hasattr(self, "active_processes"):
            self.active_processes = set()
        if not hasattr(self, "heartbeat_stop_event"):
            self.heartbeat_stop_event = threading.Event()
        if not hasattr(self, "heartbeat_thread"):
            self.heartbeat_thread = None

        legacy_log_dir = os.path.join(self.app_dir, "logs_conversion")
        try:
            if os.path.isdir(legacy_log_dir) and not os.listdir(legacy_log_dir):
                os.rmdir(legacy_log_dir)
        except OSError:
            pass

        stale_atomic_cleanup = self.cleanup_stale_atomic_temp_files()
        retention_cleanup = self.cleanup_old_problem_logs()
        success_log_cleanup = self.cleanup_unreferenced_process_logs()
        compression_cleanup = self.compress_old_detailed_logs()

        self.session_id = (
            f"{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}"
            f"_{os.getpid()}_{uuid.uuid4().hex[:8]}"
        )
        self.current_run_id = f"startup-{self.session_id}"
        self.log_file = os.path.join(self.log_dir, f"conversion_{self.session_id}.log")
        self.problem_log_file = os.path.join(
            self.log_dir,
            f"problems_startup_{self.session_id}.jsonl",
        )
        self.summary_log_file = os.path.join(
            self.log_dir,
            f"summary_startup_{self.session_id}.json",
        )
        self.report_file = os.path.join(
            self.log_dir,
            f"report_startup_{self.session_id}.md",
        )
        self.crash_log_file = os.path.join(
            self.log_dir,
            f"crash_{self.session_id}.log",
        )

        self.logger = logging.getLogger(f"VideoToAudioConverter_{self.session_id}_{id(self)}")
        self.logger.setLevel(logging.INFO)
        self.logger.propagate = False
        self.logger.handlers.clear()

        handler = logging.FileHandler(self.log_file, encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(asctime)s | %(levelname)s | %(message)s"))
        self.logger.addHandler(handler)

        self.logger.info("=== START SESSION ===")
        self.runtime_context = self.get_runtime_context()
        self.cleanup_stats = {
            "stale_atomic_temps": stale_atomic_cleanup,
            "retention": retention_cleanup,
            "successful_process_logs": success_log_cleanup,
            "compression": compression_cleanup,
        }
        self.logger.info(
            "SESSION_CONTEXT %s",
            json.dumps(self.runtime_context, ensure_ascii=False),
        )
        self.logger.info(
            "LOG_CLEANUP %s",
            json.dumps(self.cleanup_stats, ensure_ascii=False),
        )

        for file_path in (self.problem_log_file, self.summary_log_file):
            try:
                if file_path.endswith(".json"):
                    self.atomic_write_json(
                        file_path,
                        {
                            "schema_version": self.LOG_SCHEMA_VERSION,
                            "status": "started",
                            "session_id": self.session_id,
                            "app_version": self.APP_VERSION,
                            "build_id": self.build_id,
                            "created_at": self.now_iso(),
                            "created_at_utc": self.utc_now_iso(),
                            "log_file": self.log_file,
                            "problem_log_file": self.problem_log_file,
                            "active_state_file": self.active_state_file,
                            "latest_run_file": self.latest_run_file,
                            "health_history_file": self.health_history_file,
                            "schema_guide_file": self.schema_guide_file,
                            "retained_process_failures_dir": self.process_output_dir,
                            "runtime": self.runtime_context,
                            "cleanup": self.cleanup_stats,
                        },
                    )
                else:
                    with open(file_path, "w", encoding="utf-8"):
                        pass
            except Exception as e:
                self.logger.critical(
                    "INITIAL_LOG_CREATE_FAILED file=%s error=%s: %s",
                    file_path,
                    type(e).__name__,
                    e,
                )

        try:
            self.write_schema_guide()
        except Exception as e:
            self.logger.warning(
                "SCHEMA_GUIDE_WRITE_FAILED %s: %s",
                type(e).__name__,
                e,
            )

        self.update_active_state(
            "ready",
            status="idle",
            started_at=self.now_iso(),
            started_at_utc=self.utc_now_iso(),
            summary_file=self.summary_log_file,
            problem_file=self.problem_log_file,
            conversion_log_file=self.log_file,
            build_id=self.build_id,
        )

        previous_status = str(previous_active_state.get("status") or "")
        if previous_status in {"running", "crashed"}:
            heartbeat_age_seconds = None
            try:
                previous_updated = datetime.fromisoformat(
                    str(previous_active_state.get("updated_at"))
                )
                if previous_updated.tzinfo is None:
                    previous_updated = previous_updated.astimezone()
                heartbeat_age_seconds = max(
                    0,
                    (
                        datetime.now().astimezone() - previous_updated
                    ).total_seconds(),
                )
            except Exception:
                pass
            self.write_problem(
                "previous_session_incomplete",
                "Предыдущий запуск не записал нормальное завершение; вероятно, программа или компьютер были аварийно остановлены.",
                severity="error",
                previous_session_id=previous_active_state.get("session_id"),
                previous_status=previous_status,
                previous_stage=previous_active_state.get("stage"),
                previous_folder=previous_active_state.get("folder"),
                previous_file=previous_active_state.get("file"),
                previous_active_processes=previous_active_state.get(
                    "active_processes",
                    [],
                ),
                previous_summary_file=previous_active_state.get(
                    "summary_file",
                ),
                previous_problem_file=previous_active_state.get(
                    "problem_file",
                ),
                previous_updated_at=previous_active_state.get("updated_at"),
                heartbeat_age_seconds=heartbeat_age_seconds,
                previous_state_snapshot=previous_active_state,
                codex={
                    "impact": "Предыдущая операция могла остаться незавершённой, а временный или итоговый файл — неполным.",
                    "likely_cause": "Жёсткое закрытие процесса, сбой Python, отключение питания или зависший внешний процесс.",
                    "codex_action": "Начать с previous_stage и previous_active_processes, затем открыть ссылки на логи предыдущей сессии.",
                    "user_action": "Повторить незавершённую папку; исходные видео программа не удаляет.",
                },
            )

        self.update_current_session({
            "status": "ready",
            "previous_incomplete_session_detected": previous_status
            in {"running", "crashed"},
        })
