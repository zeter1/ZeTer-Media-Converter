"""Compact cross-run health history and regression baseline.

CODEX ROUTE: open this file only when the task matches this responsibility.
Methods are moved whole from the previous owner module; behavior is intentionally unchanged.
"""

import os
import re
import traceback
from collections import Counter
from datetime import datetime, timedelta
import json


class DiagnosticsHealthHistoryMixin:
    def read_recent_health_records(self, limit=20):
        """Читает небольшой хвост истории качества без загрузки лишних данных."""
        records = []
        health_file = getattr(self, "health_history_file", "")
        if not health_file or not os.path.isfile(health_file):
            return records
        try:
            with open(health_file, "r", encoding="utf-8") as source:
                for line in source:
                    if not line.strip():
                        continue
                    try:
                        item = json.loads(line)
                        if isinstance(item, dict):
                            records.append(item)
                    except (TypeError, ValueError):
                        continue
        except OSError:
            return []
        return records[-limit:]

    def build_health_record(self, summary):
        """Одна компактная строка на запуск для поиска регрессий."""
        folders = summary.get("folders") if isinstance(summary.get("folders"), list) else []
        conversion_seconds = sum(
            float(
                (folder.get("stage_metrics") or {}).get(
                    "conversion_wall_seconds",
                    0,
                )
                or 0
            )
            for folder in folders
        )
        worker_seconds = sum(
            float(
                (folder.get("conversion_metrics") or {}).get(
                    "total_elapsed_worker_seconds",
                    0,
                )
                or 0
            )
            for folder in folders
        )
        total_input_bytes = sum(
            int(
                (folder.get("conversion_metrics") or {}).get(
                    "total_input_bytes",
                    0,
                )
                or 0
            )
            for folder in folders
        )
        total_output_bytes = sum(
            int(
                (folder.get("conversion_metrics") or {}).get(
                    "total_output_bytes",
                    0,
                )
                or 0
            )
            for folder in folders
        )
        audio_seconds = sum(
            float(folder.get("original_duration_seconds", 0) or 0)
            for folder in folders
        )
        return {
            "schema_version": self.LOG_SCHEMA_VERSION,
            "session_id": self.session_id,
            "run_id": getattr(self, "current_run_id", ""),
            "time": self.now_iso(),
            "app_version": self.APP_VERSION,
            "build_id": getattr(self, "build_id", ""),
            "status": summary.get("status"),
            "elapsed_seconds": summary.get("elapsed_seconds"),
            "input_files": sum(int(folder.get("input_files", 0) or 0) for folder in folders),
            "converted_files": sum(int(folder.get("converted_files", 0) or 0) for folder in folders),
            "skipped_files": sum(int(folder.get("skipped_files", 0) or 0) for folder in folders),
            "skipped_folders": int(
                summary.get("skipped_folder_count", 0) or 0
            ),
            "failed_folders": int(summary.get("failed_count", 0) or 0),
            "event_count": sum(self.problem_counts.values()),
            "unresolved_count": self.diagnostic_status_counts()["unresolved"],
            "semantic_integrity_ok": (
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
            "fallback_count": sum(
                count
                for kind, count in self.problem_counts.items()
                if "retry" in kind or "fallback" in kind
            ),
            "audio_duration_seconds": audio_seconds,
            "conversion_wall_seconds": conversion_seconds,
            "total_worker_seconds": worker_seconds,
            "worker_pool_utilization_percent": (
                worker_seconds
                / (conversion_seconds * self.max_workers)
                * 100
                if conversion_seconds > 0 and self.max_workers > 0
                else None
            ),
            "total_input_bytes": total_input_bytes,
            "total_output_bytes": total_output_bytes,
            "audio_hours_per_wall_minute": (
                (audio_seconds / 3600) / (conversion_seconds / 60)
                if conversion_seconds > 0
                else None
            ),
            "resource_metrics": summary.get("resource_metrics", {}),
            "log_storage_bytes": self.get_log_storage_stats().get("total_bytes", 0),
        }

    def append_health_record(self, record):
        """Хранит до 120 дней компактной истории качества."""
        cutoff = datetime.now().astimezone() - timedelta(
            days=self.PROBLEM_LOG_RETENTION_DAYS
        )
        records = self.read_recent_health_records(limit=1000)
        records.append(record)
        kept = []
        for item in records:
            try:
                stamp = datetime.fromisoformat(str(item.get("time")))
                if stamp.tzinfo is None:
                    stamp = stamp.astimezone()
                if stamp >= cutoff:
                    kept.append(item)
            except Exception:
                kept.append(item)
        kept = kept[-500:]
        text = "".join(
            json.dumps(item, ensure_ascii=False, default=str) + "\n"
            for item in kept
        )
        self.atomic_write_text(self.health_history_file, text)
