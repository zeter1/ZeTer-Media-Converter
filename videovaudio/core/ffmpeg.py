"""Shared FFmpeg command helpers and failure classification.

CODEX ROUTE: open this file only when the task matches this responsibility.
Methods are moved whole from the previous owner module; behavior is intentionally unchanged.
"""

import os
import re
import hashlib
from datetime import datetime


class FFmpegUtilsMixin:
    def trim_text(self, value, limit=4000, keep_tail=False):
        """Обрезает длинный текст, сохраняя важное начало или окончание."""
        if value is None:
            return ""
        value = str(value)
        if len(value) <= limit:
            return value
        marker = f"\n... [обрезано, всего символов: {len(value)}]\n"
        if keep_tail:
            return marker + value[-limit:]
        return value[:limit] + marker

    def diagnostic_excerpt(self, value, limit=None):
        """Убирает из вывода FFmpeg повторяющийся служебный шум и оставляет причину."""
        if not value:
            return ""

        limit = limit or self.MAX_PROBLEM_TEXT_CHARS
        ignored_prefixes = (
            "ffmpeg version ",
            "ffprobe version ",
            "built with ",
            "configuration:",
            "libavutil ",
            "libavcodec ",
            "libavformat ",
            "libavdevice ",
            "libavfilter ",
            "libswscale ",
            "libswresample ",
            "=== process start ===",
            "time=",
            "operation=",
            "timeout_seconds=",
            "command=",
            "metadata:",
            "handler_name",
            "vendor_id",
            "encoder",
            "major_brand",
            "minor_version",
            "compatible_brands",
            "creation_time",
        )
        useful_lines = []
        for raw_line in str(value).splitlines():
            line = raw_line.strip("\ufeff")
            lowered = line.lower().lstrip()
            if not line.strip():
                continue
            if any(lowered.startswith(prefix) for prefix in ignored_prefixes):
                continue
            if lowered.startswith("size=") and "error" not in lowered:
                continue
            useful_lines.append(line)

        excerpt = "\n".join(useful_lines[-120:])
        return self.trim_text(excerpt, limit, keep_tail=True)

    def normalize_returncode(self, returncode):
        """Преобразует беззнаковый Windows-код FFmpeg в обычное отрицательное число."""
        if isinstance(returncode, int) and returncode > 0x7FFFFFFF:
            return returncode - 0x100000000
        return returncode

    def ensure_windows_child_error_mode(self):
        """Не даёт Windows Error Reporting удерживать упавшие FFmpeg и их файлы."""
        if os.name != "nt" or self.__class__.windows_error_mode_configured:
            return
        with self.__class__.windows_error_mode_lock:
            if self.__class__.windows_error_mode_configured:
                return
            try:
                import ctypes

                kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
                kernel32.GetErrorMode.restype = ctypes.c_uint
                kernel32.SetErrorMode.argtypes = [ctypes.c_uint]
                kernel32.SetErrorMode.restype = ctypes.c_uint
                current_mode = int(kernel32.GetErrorMode())
                kernel32.SetErrorMode(
                    current_mode | self.WINDOWS_CHILD_ERROR_MODE_FLAGS
                )
                self.__class__.windows_error_mode_configured = True
            except Exception as error:
                logger = getattr(self, "logger", None)
                if logger:
                    logger.warning(
                        "WINDOWS_ERROR_MODE_SETUP_FAILED %s: %s",
                        type(error).__name__,
                        error,
                    )

    @staticmethod
    def is_libmp3lame_joint_stereo_assertion(output_text):
        """Распознаёт фатальный assertion LAME, после которого процесс может зависнуть в Windows."""
        lowered = str(output_text or "").lower()
        return (
            "assertion failed:" in lowered
            and "libmp3lame" in lowered
            and "part2_3_length" in lowered
            and "targ_bits" in lowered
        )

    def diagnose_ffmpeg_failure(self, output_text, input_path=None, output_path=None):
        """Классифицирует типовые причины FFmpeg и даёт Codex направление исправления."""
        text = str(output_text or "")
        lowered = text.lower()
        diagnosis = {
            "code": "ffmpeg_failed",
            "likely_cause": "FFmpeg завершился с ошибкой; точная причина находится в diagnostic_excerpt.",
            "codex_action": "Проверить diagnostic_excerpt, команду и факты входного/выходного пути.",
            "user_action": "Повторить файл после проверки исходника и свободного места.",
            "retryable": False,
        }

        if self.is_libmp3lame_joint_stereo_assertion(text):
            diagnosis.update({
                "code": "libmp3lame_joint_stereo_assertion",
                "likely_cause": (
                    "Внутренний сбой joint-stereo режима libmp3lame на "
                    "конкретных аудиоданных."
                ),
                "codex_action": (
                    "Удалить неполный MP3 и один раз повторить кодирование "
                    "тем же libmp3lame с -joint_stereo 0 и сохранением "
                    "временной шкалы аудио."
                ),
                "user_action": (
                    "Ничего делать не нужно: программа должна применить "
                    "безопасный резервный режим автоматически."
                ),
                "retryable": True,
            })
        elif (
            "output file does not contain any stream" in lowered
            or "matches no streams" in lowered
            or "stream map" in lowered and "no streams" in lowered
        ):
            diagnosis.update({
                "code": "no_audio_stream",
                "likely_cause": "В контейнере нет звуковой дорожки.",
                "codex_action": "Это не сбой конвертера: пропустить файл и продолжить остальные.",
                "user_action": "Ничего делать не нужно, если в этом видео действительно нет звука.",
            })
        elif "moov atom not found" in lowered:
            diagnosis.update({
                "code": "missing_moov_atom",
                "likely_cause": "MP4-файл не докачан, обрезан или повреждён: отсутствует служебный блок moov.",
                "codex_action": "Не пытаться склеивать частичный результат; пропустить файл и показать его путь.",
                "user_action": "Заново скачать или восстановить исходное видео.",
            })
        elif "no space left on device" in lowered or "not enough space" in lowered:
            diagnosis.update({
                "code": "disk_full",
                "likely_cause": "На диске недостаточно свободного места.",
                "codex_action": "Добавить предварительную проверку свободного места и безопасно остановить запись.",
                "user_action": "Освободить место на диске и повторить обработку.",
                "retryable": True,
            })
        elif (
            "being used by another process" in lowered
            or "resource busy" in lowered
            or "sharing violation" in lowered
        ):
            diagnosis.update({
                "code": "file_in_use",
                "likely_cause": "Исходный или выходной файл занят другой программой.",
                "codex_action": "Не удалять исходник; показать занятый путь и разрешить повтор после освобождения файла.",
                "user_action": "Закрыть проигрыватель, редактор или другое приложение, использующее файл.",
                "retryable": True,
            })
        elif "permission denied" in lowered or "access is denied" in lowered:
            diagnosis.update({
                "code": "permission_denied",
                "likely_cause": "Нет прав на чтение исходника или запись результата.",
                "codex_action": "Проверить доступность входного файла и родительской папки результата.",
                "user_action": "Проверить права папки и повторить обработку.",
                "retryable": True,
            })
        elif (
            "filename or extension is too long" in lowered
            or "path too long" in lowered
            or "winerror 206" in lowered
        ):
            diagnosis.update({
                "code": "output_path_too_long",
                "likely_cause": "Путь входного или выходного файла превышает безопасный предел Windows.",
                "codex_action": "Сократить только создаваемое имя и использовать короткую временную папку.",
                "user_action": "После обновления повторить папку; переносить исходники обычно не требуется.",
                "retryable": True,
            })
        elif "cannot allocate memory" in lowered or "out of memory" in lowered:
            diagnosis.update({
                "code": "out_of_memory",
                "likely_cause": "FFmpeg или Python не смог выделить память.",
                "codex_action": "Уменьшить параллелизм, проверить размер входа и отсутствие накопления данных в памяти.",
                "user_action": "Закрыть тяжёлые программы и повторить обработку.",
                "retryable": True,
            })
        elif (
            "unknown decoder" in lowered
            or "decoder not found" in lowered
            or "unsupported codec" in lowered
            or "codec not currently supported" in lowered
        ):
            diagnosis.update({
                "code": "unsupported_codec",
                "likely_cause": "Установленная сборка FFmpeg не поддерживает кодек исходного файла.",
                "codex_action": "Проверить codec_name и возможности используемой сборки FFmpeg.",
                "user_action": "Обновить FFmpeg либо предварительно преобразовать исходный файл.",
            })
        elif (
            "unknown encoder" in lowered
            or "error initializing output stream" in lowered
            or "error while opening encoder" in lowered
        ):
            diagnosis.update({
                "code": "encoder_initialization_failed",
                "likely_cause": "Не удалось запустить MP3-кодировщик с выбранными параметрами.",
                "codex_action": "Проверить libmp3lame, частоту, каналы и фактическую команду.",
                "user_action": "Обновить FFmpeg и повторить обработку.",
            })
        elif (
            "non monotonically increasing dts" in lowered
            or "invalid dts" in lowered
            or "timestamp discontinuity" in lowered
        ):
            diagnosis.update({
                "code": "invalid_timestamps",
                "likely_cause": "Во входном потоке есть разрывы или сбросы DTS/PTS.",
                "codex_action": "Нормализовать временную шкалу до concat и проверить длительность результата.",
                "user_action": "Повторить файл после обновления программы.",
                "retryable": True,
            })
        elif "no such file or directory" in lowered:
            output_facts = self.path_facts(output_path)
            if output_facts.get("path_length", 0) >= self.SAFE_WINDOWS_PATH_LENGTH:
                diagnosis.update({
                    "code": "output_path_too_long",
                    "likely_cause": "Путь временного или итогового MP3 слишком длинный для используемого Windows API.",
                    "codex_action": "Использовать короткую временную папку и динамически сокращать имя результата.",
                    "user_action": "После обновления повторить папку; переносить исходники не требуется.",
                    "retryable": True,
                })
            else:
                diagnosis.update({
                    "code": "path_not_found",
                    "likely_cause": "Исходный путь исчез либо родительская папка результата недоступна.",
                    "codex_action": "Проверить существование обоих путей непосредственно перед запуском FFmpeg.",
                    "user_action": "Проверить, что диск подключён и исходная папка не перемещена.",
                    "retryable": True,
                })
        elif (
            "error submitting packet to decoder" in lowered
            or "error while decoding" in lowered
            or "invalid argument" in lowered and "decoder" in lowered
            or "packet corrupt" in lowered
            or "invalid data found when processing input" in lowered
        ):
            diagnosis.update({
                "code": "corrupt_media_data",
                "likely_cause": "В медиапотоке есть повреждённые или неподдерживаемые данные.",
                "codex_action": "Пропустить файл, не считать папку полностью нерабочей; сохранить точный фрагмент ошибки.",
                "user_action": "Перекачать или предварительно восстановить проблемное видео.",
            })

        diagnosis["input"] = self.path_facts(input_path)
        diagnosis["output"] = self.path_facts(output_path)
        return diagnosis

    def ffmpeg_base_command(self):
        """Базовые параметры FFmpeg без баннера, прогресса и многомегабайтного шума."""
        return [
            "ffmpeg",
            "-hide_banner",
            "-loglevel", "error",
            "-nostats",
        ]

    def extract_duration_seconds(self, text):
        """Достаёт числовую длительность из вывода ffprobe, даже если вывод лежит в process-log."""
        if not text:
            return 0

        for line in reversed(str(text).splitlines()):
            value = line.strip()
            if re.fullmatch(r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)", value):
                try:
                    duration = float(value)
                    return duration if duration > 0 else 0
                except ValueError:
                    continue
        return 0

    def command_to_text(self, cmd):
        """Пишет команду ffmpeg/ffprobe в понятном виде без запуска через shell."""
        parts = []
        for part in cmd:
            part = str(part)
            if any(ch.isspace() for ch in part):
                parts.append(f'"{part}"')
            else:
                parts.append(part)
        return " ".join(parts)
