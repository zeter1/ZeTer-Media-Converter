"""Per-run diagnostic files, summary/report persistence and latest-run indexes.

CODEX ROUTE: open this file only when the task matches this responsibility.
Methods are moved whole from the previous owner module; behavior is intentionally unchanged.
"""

import os
import re
import traceback
from collections import Counter
from datetime import datetime, timedelta
import json


class RunReportsMixin:
    def reset_run_diagnostics(self):
        """Начинает независимый набор событий для новой очереди."""
        self.ensure_diagnostic_io_state()
        self.problem_counts = Counter()
        self.problem_severity_counts = Counter()
        self.codex_priorities = {}
        self.problem_signature_stats = {}
        self.event_records = {}
        self.event_status = {}
        self.process_contexts = {}
        with self.diagnostic_failure_lock:
            self.diagnostic_failures = {}
            self.diagnostic_retry_counts = Counter()

    def begin_run_diagnostics(self):
        """Создаёт отдельные problem/summary/report-файлы для текущего run_id."""
        run_token = re.sub(
            r"[^0-9A-Za-z_-]+",
            "_",
            str(getattr(self, "current_run_id", "") or "run"),
        )
        file_token = f"{self.session_id}_{run_token}"
        self.problem_log_file = os.path.join(
            self.log_dir,
            f"problems_{file_token}.jsonl",
        )
        self.summary_log_file = os.path.join(
            self.log_dir,
            f"summary_{file_token}.json",
        )
        self.report_file = os.path.join(
            self.log_dir,
            f"report_{file_token}.md",
        )
        self.reset_run_diagnostics()
        self.atomic_write_text(self.problem_log_file, "")
        self.atomic_write_json(
            self.summary_log_file,
            {
                "schema_version": self.LOG_SCHEMA_VERSION,
                "app_version": self.APP_VERSION,
                "build_id": getattr(self, "build_id", ""),
                "session_id": self.session_id,
                "run_id": self.current_run_id,
                "status": "running",
                "created_at": self.now_iso(),
                "created_at_utc": self.utc_now_iso(),
                "problem_log_file": self.problem_log_file,
                "conversion_log_file": self.log_file,
                "report_file": self.report_file,
            },
        )

    def run_index_payload(self, summary):
        """Компактный индекс файлов и итоговых счётчиков запуска."""
        status_counts = self.diagnostic_status_counts()
        payload = {
            "schema_version": self.LOG_SCHEMA_VERSION,
            "app_version": self.APP_VERSION,
            "build_id": getattr(self, "build_id", ""),
            "session_id": self.session_id,
            "run_id": getattr(self, "current_run_id", ""),
            "status": summary.get("status"),
            "updated_at": self.now_iso(),
            "updated_at_utc": self.utc_now_iso(),
            "summary_file": self.summary_log_file,
            "problem_file": self.problem_log_file,
            "report_file": getattr(self, "report_file", ""),
            "latest_problem_summary_file": self.latest_problem_summary_file,
            "conversion_log_file": self.log_file,
            "active_state_file": self.active_state_file,
            "current_session_file": self.current_session_file,
            "latest_completed_run_file": self.latest_completed_run_file,
            "health_history_file": self.health_history_file,
            "schema_guide_file": self.schema_guide_file,
            "process_output_dir": self.process_output_dir,
            "queue_total_at_start": summary.get("queue_total_at_start"),
            "processed_count": summary.get("processed_count"),
            "success_count": summary.get("success_count"),
            "skipped_folder_count": summary.get(
                "skipped_folder_count",
                0,
            ),
            "failed_count": summary.get("failed_count"),
            "skipped_media_count": summary.get("skipped_media_count"),
            "skipped_no_audio_count": summary.get(
                "skipped_no_audio_count"
            ),
            "skipped_problem_count": summary.get(
                "skipped_problem_count"
            ),
            "actionable_problem_count": status_counts["unresolved"],
            "expected_skip_count": status_counts["expected_skip"],
            "unresolved_problems": status_counts["unresolved"],
            "recovered_problems": status_counts["recovered"],
            "run_consistency_ok": (
                (summary.get("diagnostics_integrity") or {}).get(
                    "semantic_ok"
                )
            ),
            "diagnostics_operational_ok": (
                (summary.get("diagnostics_integrity") or {}).get(
                    "operational_ok"
                )
            ),
            "diagnostics_degraded": bool(
                (summary.get("diagnostic_health") or {}).get(
                    "diagnostics_degraded"
                )
            ),
            "diagnostic_failure_count": int(
                (summary.get("diagnostic_health") or {}).get(
                    "failure_count",
                    0,
                )
                or 0
            ),
        }
        for field in (
            "previous_incomplete_session_detected",
            "cancelled",
            "error",
        ):
            if field in summary:
                payload[field] = summary.get(field)
        return payload

    def update_current_session(self, summary):
        """Обновляет состояние открытого приложения, не затирая последний итог."""
        current = self.run_index_payload(summary)
        current["application_status"] = (
            getattr(self, "active_state", {}).get("status")
            or summary.get("status")
        )
        self.atomic_write_json(self.current_session_file, current)

    def update_latest_run(self, summary):
        """Сохраняет постоянный указатель только на завершённый запуск."""
        latest = self.run_index_payload(summary)
        self.atomic_write_json(self.latest_run_file, latest)
        self.atomic_write_json(self.latest_completed_run_file, latest)
        self.update_current_session(summary)

    def build_markdown_report(self, summary):
        """Формирует короткий человекочитаемый итог без тяжёлой диагностики."""
        status_labels = {
            "completed": "Завершено успешно",
            "completed_with_skips": "Завершено с ожидаемыми пропусками",
            "completed_with_errors": "Завершено с ошибками",
            "cancelled": "Отменено пользователем",
            "crashed": "Аварийно завершено",
        }
        status = str(summary.get("status") or "unknown")
        folders = (
            summary.get("folders")
            if isinstance(summary.get("folders"), list)
            else []
        )
        skipped_folders = [
            folder
            for folder in folders
            if folder.get("outcome") == "skipped"
        ]
        failed_folders = [
            folder
            for folder in folders
            if folder.get("outcome") == "failed"
        ]
        confirmed = (
            (summary.get("codex_report") or {}).get("confirmed_bugs")
            or []
        )
        recovered = (
            (summary.get("codex_report") or {}).get("recovered_problems")
            or []
        )
        skipped_problem_files = []
        for folder in folders:
            details = folder.get("skipped_file_details")
            if not isinstance(details, list):
                continue
            for item in details:
                if (
                    isinstance(item, dict)
                    and item.get("skip_code") != "no_audio_stream"
                ):
                    skipped_problem_files.append(item)
        status_counts = (
            (summary.get("diagnostics") or {}).get("by_resolution")
            or {}
        )
        diagnostic_health = summary.get("diagnostic_health") or {}

        lines = [
            f"# Итог {self.APP_NAME}",
            "",
            f"- Результат: **{status_labels.get(status, status)}**",
            f"- Начало: {summary.get('started_at') or 'не указано'}",
            f"- Завершение: {summary.get('finished_at') or 'не указано'}",
            f"- Обработано папок: {summary.get('processed_count', 0)}",
            f"- Успешно папок: {summary.get('success_count', 0)}",
            f"- Пропущено папок без видео: {summary.get('skipped_folder_count', 0)}",
            f"- Папок с ошибками: {summary.get('failed_count', 0)}",
            f"- Видео без звука: {summary.get('skipped_no_audio_count', 0)}",
            f"- Других проблемных видео: {summary.get('skipped_problem_count', 0)}",
            f"- Нерешённых проблем: {status_counts.get('unresolved', 0)}",
            (
                "- Служебная диагностика: **НАРУШЕНА** "
                f"(сбоев записи: {diagnostic_health.get('failure_count', 0)})"
                if diagnostic_health.get("diagnostics_degraded")
                else "- Служебная диагностика: исправна"
            ),
            "",
        ]

        lines.extend(["## Что требует внимания", ""])
        if confirmed:
            for item in confirmed[:10]:
                lines.append(
                    f"- **{item.get('kind') or 'problem'}**: "
                    f"{item.get('message') or item.get('likely_cause') or 'см. JSONL'}"
                )
                if item.get("file") or item.get("folder"):
                    lines.append(
                        f"  - Объект: {item.get('file') or item.get('folder')}"
                    )
                if item.get("codex_action"):
                    lines.append(
                        f"  - Действие: {item.get('codex_action')}"
                    )
        elif failed_folders:
            for folder in failed_folders[:20]:
                lines.append(
                    f"- {folder.get('folder_name') or folder.get('folder')}: "
                    f"{folder.get('error') or folder.get('status')}"
                )
        else:
            lines.append("- Реальных ошибок программы в этом запуске не зафиксировано.")

        lines.extend(["", "## Автоматически восстановлено", ""])
        if recovered:
            for item in recovered[:10]:
                lines.append(
                    f"- {item.get('message') or item.get('likely_cause') or item.get('kind') or 'Проблема устранена fallback-режимом.'}"
                )
                if item.get("file"):
                    lines.append(f"  - Файл: {item.get('file')}")
        else:
            lines.append("- Нет.")

        lines.extend(["", "## Ожидаемые пропуски", ""])
        if skipped_folders:
            for folder in skipped_folders[:20]:
                lines.append(
                    f"- Папка: {folder.get('folder')} — "
                    f"{folder.get('skip_reason') or folder.get('status')}"
                )
        if int(summary.get("skipped_no_audio_count", 0) or 0):
            lines.append(
                f"- Видео без звуковой дорожки: "
                f"{summary.get('skipped_no_audio_count', 0)}"
            )
        if skipped_problem_files:
            lines.append("- Другие пропущенные проблемные видео:")
            for item in skipped_problem_files[:20]:
                lines.append(
                    f"  - {item.get('file') or item.get('name') or 'неизвестный файл'}: "
                    f"{item.get('reason') or item.get('skip_code') or 'причина не указана'}"
                )
        if (
            not skipped_folders
            and not int(summary.get("skipped_media_count", 0) or 0)
        ):
            lines.append("- Нет.")

        integrity = summary.get("diagnostics_integrity") or {}
        lines.extend([
            "",
            "## Целостность диагностики",
            "",
            f"- JSON/ссылки: {'OK' if integrity.get('structural_ok') else 'ОШИБКА'}",
            f"- Согласованность итогов: {'OK' if integrity.get('semantic_ok') else 'ОШИБКА'}",
            f"- Служебная запись: {'OK' if integrity.get('operational_ok') else 'ОШИБКА'}",
            "",
            "## Файлы",
            "",
            f"- JSON-итог: `{self.summary_log_file}`",
            f"- События JSONL: `{self.problem_log_file}`",
            f"- Обычный лог: `{self.log_file}`",
            "",
        ])
        return "\n".join(lines)

    def save_run_summary(self, summary):
        """Сохраняет итог запуска в JSON, чтобы нейросети было легко понять состояние."""
        try:
            summary["schema_version"] = self.LOG_SCHEMA_VERSION
            summary["app_version"] = self.APP_VERSION
            summary["session_id"] = self.session_id
            summary["run_id"] = getattr(self, "current_run_id", "")
            summary["runtime"] = getattr(self, "runtime_context", {})
            summary["diagnostic_health"] = self.diagnostic_health_snapshot()
            status_counts = self.diagnostic_status_counts()
            summary["diagnostics"] = {
                "event_count": sum(self.problem_counts.values()),
                "by_kind": dict(self.problem_counts),
                "by_severity": dict(self.problem_severity_counts),
                "by_resolution": status_counts,
                "signatures": list(self.problem_signature_stats.values()),
                "codex_review_priorities": list(self.codex_priorities.values()),
            }
            summary["codex_report"] = self.build_codex_report(summary)
            summary["report_file"] = self.report_file
            summary["diagnostics_integrity"] = self.diagnostics_integrity(
                summary
            )
            summary["log_policy"] = {
                "retention_days": self.PROBLEM_LOG_RETENTION_DAYS,
                "successful_process_logs_retained": False,
                "slow_success_process_logs_retained": True,
                "max_failure_process_log_bytes": self.MAX_PROCESS_LOG_BYTES,
                "max_retained_process_log_bytes": self.MAX_PROCESS_LOG_BYTES,
                "max_detailed_events_per_signature": self.MAX_DETAILED_EVENTS_PER_SIGNATURE,
                "max_expected_skip_details_per_signature": self.MAX_EXPECTED_SKIP_DETAILS_PER_SIGNATURE,
                "max_reproduction_argv_items": self.MAX_REPRODUCTION_ARGV_ITEMS,
                "diagnostic_files_are_per_run": True,
                "semantic_integrity_checks_enabled": True,
                "latest_completed_run_is_startup_stable": True,
                "heartbeat_interval_seconds": self.HEARTBEAT_INTERVAL_SECONDS,
                "atomic_replace_max_attempts": self.ATOMIC_REPLACE_MAX_ATTEMPTS,
                "atomic_replace_retry_delay_seconds": self.ATOMIC_REPLACE_RETRY_DELAY_SECONDS,
                "diagnostic_failure_log_samples": sorted(
                    self.DIAGNOSTIC_FAILURE_LOG_SAMPLES
                ),
                "resource_sampling_is_aggregated": True,
                "compress_detailed_logs_after_days": self.COMPRESS_DETAILED_LOGS_AFTER_DAYS,
                "strict_split_max_overage_seconds": self.SPLIT_MAX_OVERAGE_SECONDS,
                "ffmpeg_log_level": "error",
                "ffmpeg_stats_enabled": False,
                "cleanup": getattr(self, "cleanup_stats", {}),
                "storage_before_summary_write": self.get_log_storage_stats(),
            }
            if summary["diagnostic_health"].get("diagnostics_degraded"):
                try:
                    self.logger.warning(
                        "DIAGNOSTICS_DEGRADED total_failures=%s kinds=%s",
                        summary["diagnostic_health"].get("failure_count", 0),
                        ",".join(
                            item.get("kind", "")
                            for item in summary["diagnostic_health"].get(
                                "failures",
                                [],
                            )
                        ),
                    )
                except Exception:
                    pass
            self.atomic_write_json(self.summary_log_file, summary)
            markdown_report = self.build_markdown_report(summary)
            self.atomic_write_text(self.report_file, markdown_report)
            self.atomic_write_text(
                self.latest_problem_summary_file,
                markdown_report,
            )
            health_record = self.build_health_record(summary)
            self.append_health_record(health_record)
            self.update_latest_run(summary)
        except Exception as e:
            self.write_problem(
                "summary_save_failed",
                "Не удалось сохранить JSON-итог запуска.",
                exception=f"{type(e).__name__}: {e}",
                traceback=traceback.format_exc(),
            )
