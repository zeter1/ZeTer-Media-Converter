"""Reliability monitoring for diagnostic files and atomic state writes.

CODEX ROUTE: open this file only when the task matches this responsibility.
Methods are moved whole from the previous owner module; behavior is intentionally unchanged.
"""

import os
import sys
import re
import traceback
import threading
import time
import logging
import hashlib
import faulthandler
from collections import Counter
from datetime import datetime, timezone
import json
import shutil


class DiagnosticsIOHealthMixin:
    def ensure_diagnostic_io_state(self):
        """Лениво создаёт блокировки и счётчики для служебной диагностики."""
        if not hasattr(self, "active_state_write_lock"):
            self.active_state_write_lock = threading.Lock()
        if not hasattr(self, "diagnostic_failure_lock"):
            self.diagnostic_failure_lock = threading.Lock()
        if not hasattr(self, "diagnostic_failures"):
            self.diagnostic_failures = {}
        if not hasattr(self, "diagnostic_retry_counts"):
            self.diagnostic_retry_counts = Counter()

    def active_state_temp_files(self, current_process_only=True):
        """Возвращает только временные файлы active_run_state этой программы."""
        state_file = getattr(self, "active_state_file", "")
        if not state_file:
            return []
        directory = os.path.dirname(os.path.abspath(state_file))
        base_name = os.path.basename(state_file)
        pattern = re.compile(
            rf"^{re.escape(base_name)}\.(\d+)\.(\d+)\.tmp$",
            re.IGNORECASE,
        )
        found = []
        try:
            names = os.listdir(directory)
        except OSError:
            return found
        current_pid = os.getpid()
        for name in names:
            match = pattern.fullmatch(name)
            if not match:
                continue
            if current_process_only and int(match.group(1)) != current_pid:
                continue
            found.append(os.path.join(directory, name))
        return sorted(found)

    def record_diagnostic_failure(self, kind, error, file_path="", **details):
        """Агрегирует сбои самой диагностики без рекурсивной записи в JSONL."""
        self.ensure_diagnostic_io_state()
        now = self.now_iso()
        error_type = type(error).__name__
        error_text = self.trim_text(error, 800)
        with self.diagnostic_failure_lock:
            item = self.diagnostic_failures.setdefault(
                str(kind),
                {
                    "kind": str(kind),
                    "count": 0,
                    "first_seen": now,
                    "last_seen": now,
                    "error_type": error_type,
                    "error": error_text,
                    "file": str(file_path or ""),
                    "sample_details": {},
                },
            )
            item["count"] += 1
            item["last_seen"] = now
            item["error_type"] = error_type
            item["error"] = error_text
            if file_path:
                item["file"] = str(file_path)
            if details:
                item["sample_details"] = {
                    key: self.trim_text(value, 500)
                    for key, value in details.items()
                    if value not in (None, "")
                }
            count = item["count"]

        should_log = (
            count in self.DIAGNOSTIC_FAILURE_LOG_SAMPLES
            or count % 250 == 0
        )
        logger = getattr(self, "logger", None)
        if should_log and logger:
            try:
                logger.warning(
                    "%s count=%s %s: %s file=%s",
                    str(kind).upper(),
                    count,
                    error_type,
                    error_text,
                    str(file_path or ""),
                )
            except Exception:
                pass

    def record_diagnostic_retry(self, kind, retry_count):
        """Считает успешные повторы атомарной замены без лишних строк лога."""
        if not retry_count:
            return
        self.ensure_diagnostic_io_state()
        with self.diagnostic_failure_lock:
            self.diagnostic_retry_counts[str(kind)] += int(retry_count)

    def diagnostic_health_snapshot(self):
        """Формирует компактный итог надёжности служебных файлов запуска."""
        self.ensure_diagnostic_io_state()
        with self.diagnostic_failure_lock:
            failures = [
                dict(item)
                for item in self.diagnostic_failures.values()
            ]
            retry_counts = dict(self.diagnostic_retry_counts)
        failures.sort(key=lambda item: (-int(item.get("count", 0)), item["kind"]))
        current_temp_files = self.active_state_temp_files(
            current_process_only=True,
        )
        stale_cleanup = (
            getattr(self, "cleanup_stats", {}).get("stale_atomic_temps", {})
            if isinstance(getattr(self, "cleanup_stats", {}), dict)
            else {}
        )
        cleanup_failure_count = int(stale_cleanup.get("failed_files", 0) or 0)
        failure_count = sum(int(item.get("count", 0) or 0) for item in failures)
        degraded = bool(
            failure_count
            or current_temp_files
            or cleanup_failure_count
        )
        return {
            "operational_ok": not degraded,
            "diagnostics_degraded": degraded,
            "failure_count": failure_count,
            "failures": failures,
            "successful_retry_count": sum(retry_counts.values()),
            "successful_retries_by_kind": retry_counts,
            "active_state_temp_file_count": len(current_temp_files),
            "active_state_temp_files": current_temp_files[:20],
            "stale_temp_cleanup_failure_count": cleanup_failure_count,
        }
