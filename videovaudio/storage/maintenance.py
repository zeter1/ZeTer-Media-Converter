"""Log retention, compression and stale artifact cleanup.

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


class LogMaintenanceMixin:
    def compress_old_detailed_logs(self):
        """Сжимает старые подробные текстовые логи, сохраняя имена ссылок через .gz."""
        cutoff_timestamp = (
            time.time() - self.COMPRESS_DETAILED_LOGS_AFTER_DAYS * 86400
        )
        stats = {
            "after_days": self.COMPRESS_DETAILED_LOGS_AFTER_DAYS,
            "compressed_files": 0,
            "source_bytes": 0,
            "compressed_bytes": 0,
            "saved_bytes": 0,
            "errors": [],
        }
        candidates = []
        try:
            for name in os.listdir(self.log_dir):
                if re.match(
                    r"^(conversion|crash)_.+\.log$",
                    name,
                    flags=re.IGNORECASE,
                ):
                    candidates.append(os.path.join(self.log_dir, name))
            if os.path.isdir(self.process_output_dir):
                for name in os.listdir(self.process_output_dir):
                    if name.lower().endswith(".log"):
                        candidates.append(
                            os.path.join(self.process_output_dir, name)
                        )
        except Exception as e:
            stats["errors"].append(f"scan: {type(e).__name__}: {e}")
            return stats

        for source_path in candidates:
            temp_path = f"{source_path}.gz.{os.getpid()}.tmp"
            gzip_path = f"{source_path}.gz"
            try:
                if (
                    os.path.getmtime(source_path) >= cutoff_timestamp
                    or os.path.exists(gzip_path)
                ):
                    continue
                source_size = os.path.getsize(source_path)
                source_mtime = os.path.getmtime(source_path)
                with open(source_path, "rb") as source:
                    with gzip.GzipFile(
                        temp_path,
                        mode="wb",
                        compresslevel=6,
                        mtime=0,
                    ) as target:
                        shutil.copyfileobj(
                            source,
                            target,
                            length=1024 * 1024,
                        )
                with gzip.open(temp_path, "rb") as check:
                    while check.read(1024 * 1024):
                        pass
                os.replace(temp_path, gzip_path)
                os.utime(gzip_path, (source_mtime, source_mtime))
                compressed_size = os.path.getsize(gzip_path)
                os.remove(source_path)
                stats["compressed_files"] += 1
                stats["source_bytes"] += source_size
                stats["compressed_bytes"] += compressed_size
                stats["saved_bytes"] += max(
                    0,
                    source_size - compressed_size,
                )
            except Exception as e:
                stats["errors"].append(
                    f"{source_path}: {type(e).__name__}: {e}"
                )
                try:
                    if os.path.exists(temp_path):
                        os.remove(temp_path)
                except OSError:
                    pass
        return stats

    @staticmethod
    def is_process_running(process_id):
        """Без сторонних зависимостей проверяет, существует ли процесс."""
        try:
            process_id = int(process_id)
        except (TypeError, ValueError):
            return False
        if process_id <= 0:
            return False
        if process_id == os.getpid():
            return True
        if os.name == "nt":
            try:
                import ctypes

                process_query_limited_information = 0x1000
                still_active = 259
                kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
                kernel32.OpenProcess.argtypes = [
                    ctypes.c_ulong,
                    ctypes.c_int,
                    ctypes.c_ulong,
                ]
                kernel32.OpenProcess.restype = ctypes.c_void_p
                kernel32.GetExitCodeProcess.argtypes = [
                    ctypes.c_void_p,
                    ctypes.POINTER(ctypes.c_ulong),
                ]
                kernel32.GetExitCodeProcess.restype = ctypes.c_int
                kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
                kernel32.CloseHandle.restype = ctypes.c_int
                handle = kernel32.OpenProcess(
                    process_query_limited_information,
                    False,
                    process_id,
                )
                if not handle:
                    return ctypes.get_last_error() == 5
                try:
                    exit_code = ctypes.c_ulong()
                    if not kernel32.GetExitCodeProcess(
                        handle,
                        ctypes.byref(exit_code),
                    ):
                        return True
                    return exit_code.value == still_active
                finally:
                    kernel32.CloseHandle(handle)
            except Exception:
                return True
        try:
            os.kill(process_id, 0)
            return True
        except OSError:
            return False

    def cleanup_stale_atomic_temp_files(self):
        """Удаляет старые временные active-state файлы только мёртвых процессов."""
        stats = {
            "minimum_age_seconds": self.STALE_ATOMIC_TEMP_MIN_AGE_SECONDS,
            "scanned_files": 0,
            "deleted_files": 0,
            "skipped_active_process": 0,
            "skipped_recent": 0,
            "failed_files": 0,
            "errors": [],
        }
        state_file = getattr(self, "active_state_file", "")
        if not state_file:
            return stats
        directory = os.path.dirname(os.path.abspath(state_file))
        base_name = os.path.basename(state_file)
        pattern = re.compile(
            rf"^{re.escape(base_name)}\.(\d+)\.(\d+)\.tmp$",
            re.IGNORECASE,
        )
        try:
            entries = list(os.scandir(directory))
        except OSError as error:
            stats["failed_files"] = 1
            stats["errors"].append(
                f"{directory}: {type(error).__name__}: {error}"
            )
            return stats

        now = time.time()
        for entry in entries:
            match = pattern.fullmatch(entry.name)
            if not match:
                continue
            try:
                if not entry.is_file(follow_symlinks=False):
                    continue
                stats["scanned_files"] += 1
                age_seconds = max(0.0, now - entry.stat().st_mtime)
                if age_seconds < self.STALE_ATOMIC_TEMP_MIN_AGE_SECONDS:
                    stats["skipped_recent"] += 1
                    continue
                if self.is_process_running(int(match.group(1))):
                    stats["skipped_active_process"] += 1
                    continue
                os.remove(entry.path)
                stats["deleted_files"] += 1
            except OSError as error:
                stats["failed_files"] += 1
                if len(stats["errors"]) < 20:
                    stats["errors"].append(
                        f"{entry.path}: {type(error).__name__}: {error}"
                    )
        return stats

    def cleanup_old_problem_logs(self):
        """Удаляет только журналы этой программы старше 120 дней."""
        cutoff = datetime.now() - timedelta(days=self.PROBLEM_LOG_RETENTION_DAYS)
        stats = {"retention_days": self.PROBLEM_LOG_RETENTION_DAYS, "deleted_files": 0, "freed_bytes": 0, "errors": []}
        root_patterns = (
            re.compile(r"^conversion_.+\.log(?:\.gz)?$", re.IGNORECASE),
            re.compile(r"^problems_.+\.jsonl$", re.IGNORECASE),
            re.compile(r"^summary_.+\.json$", re.IGNORECASE),
            re.compile(r"^report_.+\.md$", re.IGNORECASE),
            re.compile(r"^crash_.+\.log(?:\.gz)?$", re.IGNORECASE),
        )

        candidates = []
        try:
            for name in os.listdir(self.log_dir):
                path = os.path.join(self.log_dir, name)
                if os.path.isfile(path) and any(pattern.match(name) for pattern in root_patterns):
                    candidates.append(path)
            if os.path.isdir(self.process_output_dir):
                for name in os.listdir(self.process_output_dir):
                    path = os.path.join(self.process_output_dir, name)
                    if (
                        os.path.isfile(path)
                        and (
                            name.lower().endswith(".log")
                            or name.lower().endswith(".log.gz")
                            or re.match(
                                r"^concat_manifest_.+\.json$",
                                name,
                                flags=re.IGNORECASE,
                            )
                        )
                    ):
                        candidates.append(path)
        except Exception as e:
            stats["errors"].append(f"scan: {type(e).__name__}: {e}")
            return stats

        for path in candidates:
            try:
                modified = datetime.fromtimestamp(os.path.getmtime(path))
                if modified >= cutoff:
                    continue
                size = os.path.getsize(path)
                os.remove(path)
                stats["deleted_files"] += 1
                stats["freed_bytes"] += size
            except Exception as e:
                stats["errors"].append(f"{path}: {type(e).__name__}: {e}")
        return stats

    def collect_referenced_process_logs(self):
        """Находит process-log, на которые ссылаются реальные проблемные события."""
        referenced = set()

        def visit(value):
            if isinstance(value, dict):
                for key, child in value.items():
                    if key == "process_log_file" and isinstance(child, str) and child:
                        referenced.add(os.path.normcase(os.path.abspath(child)))
                    else:
                        visit(child)
            elif isinstance(value, list):
                for child in value:
                    visit(child)

        try:
            for name in os.listdir(self.log_dir):
                if not re.match(r"^problems_.+\.jsonl$", name, flags=re.IGNORECASE):
                    continue
                path = os.path.join(self.log_dir, name)
                with open(path, "r", encoding="utf-8") as f:
                    for line in f:
                        if not line.strip():
                            continue
                        try:
                            visit(json.loads(line))
                        except (ValueError, TypeError):
                            continue
        except Exception:
            return referenced
        return referenced

    def cleanup_unreferenced_process_logs(self, minimum_age_hours=24):
        """Удаляет старые логи успешных процессов, оставляя детали реальных проблем."""
        stats = {"deleted_files": 0, "freed_bytes": 0, "errors": []}
        if not os.path.isdir(self.process_output_dir):
            return stats

        referenced = self.collect_referenced_process_logs()
        cutoff_timestamp = time.time() - minimum_age_hours * 3600
        for name in os.listdir(self.process_output_dir):
            path = os.path.join(self.process_output_dir, name)
            if (
                not os.path.isfile(path)
                or not (
                    name.lower().endswith(".log")
                    or name.lower().endswith(".log.gz")
                )
            ):
                continue
            normalized = os.path.normcase(os.path.abspath(path))
            reference_key = (
                normalized[:-3]
                if normalized.lower().endswith(".gz")
                else normalized
            )
            try:
                if (
                    reference_key in referenced
                    or normalized in referenced
                    or os.path.getmtime(path) >= cutoff_timestamp
                ):
                    continue
                size = os.path.getsize(path)
                os.remove(path)
                stats["deleted_files"] += 1
                stats["freed_bytes"] += size
            except Exception as e:
                stats["errors"].append(f"{path}: {type(e).__name__}: {e}")
        return stats
