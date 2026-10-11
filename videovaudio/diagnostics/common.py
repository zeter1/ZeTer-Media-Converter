"""Time and source hashing helpers shared by diagnostics/runtime identity.

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


class DiagnosticsCommonMixin:
    def now_iso(self):
        """Локальное время с часовым поясом для сопоставления разных компьютеров."""
        return datetime.now().astimezone().isoformat(timespec="seconds")

    def utc_now_iso(self):
        """UTC-время события для машинной сортировки."""
        return datetime.now(timezone.utc).isoformat(timespec="seconds")

    def sha256_file(self, file_path):
        """Потоково вычисляет отпечаток программы без загрузки файла целиком."""
        try:
            digest = hashlib.sha256()
            with open(file_path, "rb") as source:
                for block in iter(lambda: source.read(1024 * 1024), b""):
                    digest.update(block)
            return digest.hexdigest()
        except Exception as e:
            return f"unavailable:{type(e).__name__}:{e}"
