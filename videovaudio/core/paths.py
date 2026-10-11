"""Path normalization, output naming and filesystem-facing helpers.

CODEX ROUTE: open this file only when the task matches this responsibility.
Methods are moved whole from the previous owner module; behavior is intentionally unchanged.
"""

import os
import re
import hashlib
from datetime import datetime


class PathUtilsMixin:
    def path_facts(self, path):
        """Компактные факты о пути, полезные при ошибках доступа и длинных путях."""
        if not path:
            return {}
        try:
            absolute = os.path.abspath(path)
            exists = os.path.exists(absolute)
            is_file = os.path.isfile(absolute)
            return {
                "path": absolute,
                "path_length": len(absolute),
                "exists": exists,
                "is_file": is_file,
                "suffix": os.path.splitext(absolute)[1].lower(),
                "size_bytes": os.path.getsize(absolute) if is_file else None,
                "modified_at": (
                    datetime.fromtimestamp(os.path.getmtime(absolute))
                    .astimezone()
                    .isoformat(timespec="seconds")
                    if exists
                    else None
                ),
                "parent_exists": os.path.isdir(os.path.dirname(absolute)),
            }
        except Exception as e:
            return {
                "path": str(path),
                "inspection_error": f"{type(e).__name__}: {e}",
            }

    def build_output_path(self, directory, prefix, source_name, extension=".mp3"):
        """Формирует понятное имя результата, но не превышает безопасную длину пути."""
        absolute_dir = os.path.abspath(directory)
        reserved = len(absolute_dir) + 1 + len(prefix) + len(extension)
        available = max(8, min(120, self.SAFE_WINDOWS_PATH_LENGTH - reserved))
        stem = self.safe_output_stem(source_name, fallback="audio", limit=available)
        candidate = os.path.join(directory, f"{prefix}{stem}{extension}")
        if len(os.path.abspath(candidate)) > self.SAFE_WINDOWS_PATH_LENGTH:
            candidate = os.path.join(directory, f"{prefix.rstrip('_')}{extension}")
        return candidate

    def build_audio_split_output_path(
        self,
        directory,
        label,
        part_number,
        expected_parts,
    ):
        """Именует одиночный MP3 по курсу, а набор — пронумерованными частями."""
        safe_label = self.safe_output_stem(label, fallback="Audio", limit=80)
        prefix = (
            ""
            if expected_parts == 1
            else f"Часть {part_number:02d} - "
        )
        return self.build_output_path(
            directory,
            prefix,
            f"{safe_label}.mp3",
        )

    def read_text_tail(self, file_path, limit_bytes=24000):
        """Читает хвост большого лога процесса без риска загрузить гигабайтный файл."""
        try:
            if not file_path or not os.path.exists(file_path):
                return ""

            size = os.path.getsize(file_path)
            with open(file_path, "rb") as f:
                if size > limit_bytes:
                    f.seek(-limit_bytes, os.SEEK_END)
                    data = f.read()
                    prefix = f"... [показан хвост файла, всего байт: {size}]\n"
                else:
                    data = f.read()
                    prefix = ""
            return prefix + data.decode("utf-8", errors="replace")
        except Exception as e:
            return f"Не удалось прочитать лог процесса: {type(e).__name__}: {e}"

    def safe_log_fragment(self, value, fallback="process", limit=90):
        """Безопасный фрагмент имени файла для логов ffmpeg/ffprobe."""
        cleaned = "".join(c if c.isalnum() or c in " -_.()" else "_" for c in str(value))
        cleaned = re.sub(r"_+", "_", cleaned).strip(" ._")
        if not cleaned:
            cleaned = fallback
        return cleaned[:limit]

    def safe_output_stem(self, value, fallback="audio", limit=120):
        """Безопасное имя MP3 без слишком длинных путей Windows."""
        stem = os.path.splitext(os.path.basename(str(value)))[0]
        cleaned = "".join(c for c in stem if c.isalnum() or c in " -_.()").strip()
        cleaned = re.sub(r"\s+", " ", cleaned).strip(" .")
        if not cleaned:
            cleaned = fallback
        return cleaned[:limit].rstrip(" .")

    def normalize_folder_key(self, folder):
        """Ключ для сравнения путей очереди без дублей вида C:\\A и c:\\a\\."""
        return os.path.normcase(os.path.abspath(os.path.normpath(folder)))

    def normalize_folder_path(self, folder):
        """Возвращает единый абсолютный Windows-путь для очереди и логов."""
        return os.path.abspath(os.path.normpath(str(folder)))

    def escape_concat_path(self, path):
        """Экранирует путь для ffmpeg concat demuxer."""
        normalized = os.path.abspath(path).replace("\\", "/")
        return normalized.replace("'", "'\\''")
