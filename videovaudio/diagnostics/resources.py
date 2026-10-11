"""Resource sampling and aggregated run metrics.

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


class DiagnosticsResourcesMixin:
    def system_resource_sample(self, related_path=None):
        """Снимает память, CPU и свободное место без внешних зависимостей."""
        sample = {"cpu_count": os.cpu_count()}
        try:
            if os.name == "nt":
                import ctypes
                from ctypes import wintypes

                class MemoryStatus(ctypes.Structure):
                    _fields_ = [
                        ("length", ctypes.c_ulong),
                        ("memory_load_percent", ctypes.c_ulong),
                        ("total_physical_bytes", ctypes.c_ulonglong),
                        ("available_physical_bytes", ctypes.c_ulonglong),
                        ("total_page_file_bytes", ctypes.c_ulonglong),
                        ("available_page_file_bytes", ctypes.c_ulonglong),
                        ("total_virtual_bytes", ctypes.c_ulonglong),
                        ("available_virtual_bytes", ctypes.c_ulonglong),
                        ("available_extended_virtual_bytes", ctypes.c_ulonglong),
                    ]

                memory = MemoryStatus()
                memory.length = ctypes.sizeof(MemoryStatus)
                if ctypes.windll.kernel32.GlobalMemoryStatusEx(
                    ctypes.byref(memory)
                ):
                    sample["memory"] = {
                        "load_percent": int(memory.memory_load_percent),
                        "total_physical_bytes": int(
                            memory.total_physical_bytes
                        ),
                        "available_physical_bytes": (
                            int(memory.available_physical_bytes)
                        ),
                    }
                idle = wintypes.FILETIME()
                kernel = wintypes.FILETIME()
                user = wintypes.FILETIME()
                if ctypes.windll.kernel32.GetSystemTimes(
                    ctypes.byref(idle),
                    ctypes.byref(kernel),
                    ctypes.byref(user),
                ):
                    def filetime_value(value):
                        return (
                            int(value.dwHighDateTime) << 32
                        ) | int(value.dwLowDateTime)

                    sample["_cpu_times"] = {
                        "idle": filetime_value(idle),
                        "kernel": filetime_value(kernel),
                        "user": filetime_value(user),
                    }
            elif hasattr(os, "sysconf"):
                page_size = int(os.sysconf("SC_PAGE_SIZE"))
                total_pages = int(os.sysconf("SC_PHYS_PAGES"))
                available_pages = int(os.sysconf("SC_AVPHYS_PAGES"))
                sample["memory"] = {
                    "total_physical_bytes": page_size * total_pages,
                    "available_physical_bytes": (
                        page_size * available_pages
                    ),
                }
        except Exception as e:
            sample["memory"] = {
                "inspection_error": f"{type(e).__name__}: {e}",
            }
        candidate = related_path
        if candidate and not os.path.isdir(candidate):
            candidate = os.path.dirname(os.path.abspath(candidate))
        if not candidate or not os.path.isdir(candidate):
            candidate = getattr(self, "app_dir", os.getcwd())
        try:
            usage = shutil.disk_usage(candidate)
            sample["disk"] = {
                "path": os.path.abspath(candidate),
                "total_bytes": usage.total,
                "used_bytes": usage.used,
                "free_bytes": usage.free,
            }
        except Exception as e:
            sample["disk"] = {
                "path": str(candidate),
                "inspection_error": f"{type(e).__name__}: {e}",
            }
        return sample

    def resource_snapshot(self, related_path=None):
        """Компактные ресурсы системы в момент проблемы."""
        snapshot = self.system_resource_sample(related_path)
        snapshot.pop("_cpu_times", None)
        snapshot.update({
            "process_pid": os.getpid(),
            "thread_name": threading.current_thread().name,
        })
        return snapshot

    def reset_run_resource_metrics(self):
        """Начинает компактное агрегирование ресурсов для текущей очереди."""
        with self.resource_metrics_lock:
            self.run_resource_metrics = {
                "samples": 0,
                "cpu_samples": 0,
                "cpu_percent_sum": 0.0,
                "cpu_percent_max": 0.0,
                "memory_samples": 0,
                "memory_load_percent_sum": 0.0,
                "memory_load_percent_max": 0.0,
                "minimum_available_memory_bytes": None,
                "minimum_free_disk_bytes": None,
                "active_process_count_sum": 0,
                "active_process_count_max": 0,
            }
            self.previous_cpu_times = None
        return self.sample_run_resources()

    def sample_run_resources(self):
        """Обновляет агрегаты; отдельные heartbeat-снимки в лог не добавляет."""
        sample = self.system_resource_sample(
            getattr(self, "app_dir", None)
        )
        with self.process_lock:
            active_process_count = len(self.active_processes)
        cpu_percent = None
        current_cpu_times = sample.pop("_cpu_times", None)
        with self.resource_metrics_lock:
            metrics = self.run_resource_metrics
            if not metrics:
                return sample
            metrics["samples"] += 1
            metrics["active_process_count_sum"] += active_process_count
            metrics["active_process_count_max"] = max(
                metrics["active_process_count_max"],
                active_process_count,
            )
            previous = self.previous_cpu_times
            if current_cpu_times:
                self.previous_cpu_times = current_cpu_times
            if previous and current_cpu_times:
                idle_delta = (
                    current_cpu_times["idle"] - previous["idle"]
                )
                total_delta = (
                    current_cpu_times["kernel"]
                    + current_cpu_times["user"]
                    - previous["kernel"]
                    - previous["user"]
                )
                if total_delta > 0:
                    cpu_percent = max(
                        0.0,
                        min(
                            100.0,
                            (total_delta - idle_delta)
                            / total_delta
                            * 100.0,
                        ),
                    )
                    metrics["cpu_samples"] += 1
                    metrics["cpu_percent_sum"] += cpu_percent
                    metrics["cpu_percent_max"] = max(
                        metrics["cpu_percent_max"],
                        cpu_percent,
                    )
            memory = sample.get("memory")
            if isinstance(memory, dict):
                load = memory.get("load_percent")
                available = memory.get("available_physical_bytes")
                if isinstance(load, (int, float)):
                    metrics["memory_samples"] += 1
                    metrics["memory_load_percent_sum"] += load
                    metrics["memory_load_percent_max"] = max(
                        metrics["memory_load_percent_max"],
                        load,
                    )
                if isinstance(available, (int, float)):
                    current_minimum = metrics[
                        "minimum_available_memory_bytes"
                    ]
                    metrics["minimum_available_memory_bytes"] = (
                        available
                        if current_minimum is None
                        else min(current_minimum, available)
                    )
            disk = sample.get("disk")
            if isinstance(disk, dict):
                free_bytes = disk.get("free_bytes")
                if isinstance(free_bytes, (int, float)):
                    current_minimum = metrics["minimum_free_disk_bytes"]
                    metrics["minimum_free_disk_bytes"] = (
                        free_bytes
                        if current_minimum is None
                        else min(current_minimum, free_bytes)
                    )
        sample["cpu_percent_since_previous_sample"] = cpu_percent
        sample["active_process_count"] = active_process_count
        return sample

    def run_resource_metrics_summary(self):
        """Возвращает только итоговые агрегаты, сохраняя лог маленьким."""
        self.sample_run_resources()
        with self.resource_metrics_lock:
            metrics = dict(self.run_resource_metrics)
        cpu_samples = int(metrics.get("cpu_samples", 0) or 0)
        memory_samples = int(metrics.get("memory_samples", 0) or 0)
        samples = int(metrics.get("samples", 0) or 0)
        payload = {
            "sample_count": samples,
            "sample_interval_seconds": self.HEARTBEAT_INTERVAL_SECONDS,
            "average_cpu_percent": (
                metrics.get("cpu_percent_sum", 0.0) / cpu_samples
                if cpu_samples
                else None
            ),
            "maximum_cpu_percent": (
                metrics.get("cpu_percent_max")
                if cpu_samples
                else None
            ),
            "average_memory_load_percent": (
                metrics.get("memory_load_percent_sum", 0.0)
                / memory_samples
                if memory_samples
                else None
            ),
            "maximum_memory_load_percent": (
                metrics.get("memory_load_percent_max")
                if memory_samples
                else None
            ),
            "minimum_available_memory_bytes": metrics.get(
                "minimum_available_memory_bytes"
            ),
            "minimum_free_disk_bytes": metrics.get(
                "minimum_free_disk_bytes"
            ),
            "average_active_process_count": (
                metrics.get("active_process_count_sum", 0) / samples
                if samples
                else None
            ),
            "maximum_active_process_count": metrics.get(
                "active_process_count_max",
                0,
            ),
        }
        return payload
