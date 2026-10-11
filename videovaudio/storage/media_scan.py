"""Supported-media discovery and natural ordering.

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


class MediaScanMixin:
    def natural_sort_key(self, value):
        """Естественная сортировка: 1, 2, 10 вместо 1, 10, 2."""
        normalized = os.path.normcase(os.path.normpath(str(value))).lower()
        return [int(part) if part.isdigit() else part for part in re.split(r"(\d+)", normalized)]

    def scan_media_files(self, path, report_problems=True):
        """Сканирует видео и отдельно сообщает ошибки чтения.

        Пустая папка и неполное сканирование не смешиваются: при любой ошибке
        вызывающий код может остановиться до удаления старых результатов.
        """
        result = {
            "status": "ok",
            "root": self.normalize_folder_path(path) if path else "",
            "files": [],
            "errors": [],
            "problem_event_ids": [],
        }
        if not path:
            return result

        video_exts = (
            ".mp4", ".avi", ".mkv", ".mov", ".wmv", ".flv", ".webm",
            ".mpeg", ".mpg", ".3gp", ".m4v", ".ts",
        )
        skip_dirs = {
            "__temp__",
            self.VIDEO_TEMP_FOLDER,
            "_codex_test_media",
            "Аудио для каждого видео",
            "Все видео в аудио по 10 часов",
            self.VIDEO_OUTPUT_FOLDER,
            "logs",
            "logs_conversion",
            "Логи проблем",
            "process_output",
        }
        skip_dir_keys = {os.path.normcase(name) for name in skip_dirs}
        root_path = result["root"]

        def register_error(kind, message, error):
            error_path = self.normalize_folder_path(
                getattr(error, "filename", None) or root_path
            )
            error_info = {
                "path": error_path,
                "exception": f"{type(error).__name__}: {error}",
            }
            result["errors"].append(error_info)
            if report_problems:
                event_id = self.write_problem(
                    kind,
                    message,
                    folder=error_path,
                    exception=error_info["exception"],
                )
                result["problem_event_ids"].append(event_id)

        def on_walk_error(error):
            register_error(
                "scan_subfolder_failed",
                "Не удалось просканировать подпапку; обработка папки остановлена, чтобы не создать неполный результат.",
                error,
            )

        try:
            for current_root, dirs, files in os.walk(
                root_path,
                onerror=on_walk_error,
            ):
                dirs[:] = [
                    directory
                    for directory in dirs
                    if os.path.normcase(directory) not in skip_dir_keys
                ]
                for name in files:
                    if name.lower().endswith(video_exts):
                        result["files"].append(
                            self.normalize_folder_path(
                                os.path.join(current_root, name)
                            )
                        )
        except Exception as error:
            register_error(
                "scan_folder_failed",
                "Не удалось просканировать папку с видео; обработка остановлена.",
                error,
            )

        result["files"] = sorted(
            result["files"],
            key=self.natural_sort_key,
        )
        if result["errors"]:
            result["status"] = (
                "partial"
                if result["files"]
                else "failed"
            )
        return result

    def get_files(self, path):
        """Возвращает видео для интерфейса без записи диагностических событий."""
        return self.scan_media_files(
            path,
            report_problems=False,
        )["files"]
