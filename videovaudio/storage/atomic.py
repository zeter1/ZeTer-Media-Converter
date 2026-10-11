"""Atomic file replacement/read-write primitives.

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


class AtomicStorageMixin:
    @staticmethod
    def is_retryable_atomic_replace_error(error):
        """Определяет временные блокировки файла, характерные для Windows."""
        return (
            isinstance(error, PermissionError)
            or getattr(error, "winerror", None) in {5, 32, 33}
        )

    def atomic_replace_with_retry(self, temp_path, file_path):
        """Ограниченно повторяет атомарную замену при временной блокировке."""
        for attempt in range(1, self.ATOMIC_REPLACE_MAX_ATTEMPTS + 1):
            try:
                os.replace(temp_path, file_path)
                return attempt - 1
            except OSError as error:
                if (
                    attempt >= self.ATOMIC_REPLACE_MAX_ATTEMPTS
                    or not self.is_retryable_atomic_replace_error(error)
                ):
                    raise
                time.sleep(
                    self.ATOMIC_REPLACE_RETRY_DELAY_SECONDS * attempt
                )
        return 0

    def cleanup_own_atomic_temp(self, temp_path, target_path):
        """Удаляет только временный файл текущей операции записи."""
        try:
            if os.path.exists(temp_path):
                os.remove(temp_path)
        except OSError as error:
            self.record_diagnostic_failure(
                "atomic_temp_cleanup_failed",
                error,
                file_path=temp_path,
                target_file=target_path,
            )

    def atomic_write_json(self, file_path, data):
        """Записывает важный JSON через временный файл и атомарную замену."""
        file_path = os.fspath(file_path)
        temp_path = (
            f"{file_path}.{os.getpid()}.{threading.get_ident()}.tmp"
        )
        try:
            with open(temp_path, "w", encoding="utf-8") as target:
                json.dump(data, target, ensure_ascii=False, indent=2, default=str)
                target.flush()
                os.fsync(target.fileno())
            return self.atomic_replace_with_retry(temp_path, file_path)
        finally:
            self.cleanup_own_atomic_temp(temp_path, file_path)

    def atomic_write_text(self, file_path, text):
        """Атомарно сохраняет небольшой текстовый служебный файл."""
        file_path = os.fspath(file_path)
        temp_path = (
            f"{file_path}.{os.getpid()}.{threading.get_ident()}.tmp"
        )
        try:
            with open(temp_path, "w", encoding="utf-8", newline="\n") as target:
                target.write(str(text))
                target.flush()
                os.fsync(target.fileno())
            return self.atomic_replace_with_retry(temp_path, file_path)
        finally:
            self.cleanup_own_atomic_temp(temp_path, file_path)

    def read_json_file(self, file_path):
        """Безопасно читает JSON, возвращая пустой словарь при повреждении."""
        try:
            with open(file_path, "r", encoding="utf-8") as source:
                data = json.load(source)
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}
