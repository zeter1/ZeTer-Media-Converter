"""FFprobe parsing and audio metadata helpers.

CODEX ROUTE: open this file only when the task matches this responsibility.
Methods are moved whole from the previous owner module; behavior is intentionally unchanged.
"""

import os
import traceback
import subprocess
import json
import math
import re


class AudioProbeMixin:
    def extract_ffprobe_json(self, text):
        """Извлекает JSON ffprobe из process-log с добавленным служебным заголовком."""
        value = str(text or "")
        decoder = json.JSONDecoder()
        # FFprobe starts its JSON object on a new line. Paths in the process
        # header/footer may contain braces; raw_decode also tolerates the footer
        # without treating braces within JSON strings as object boundaries.
        for match in re.finditer(r"(?m)^[ \t\ufeff]*\{", value):
            start = match.end() - 1
            try:
                payload, _ = decoder.raw_decode(value, start)
            except ValueError:
                continue
            if isinstance(payload, dict) and any(key in payload for key in ("streams", "format", "error")):
                return payload
        return {}

    def get_audio_info(self, file):
        """Возвращает длительность и фактический аудиопрофиль через один вызов ffprobe."""
        empty_info = {
            "duration_seconds": 0,
            "duration_source": None,
            "sample_rate_hz": None,
            "channels": None,
            "channel_layout": None,
            "codec_name": None,
            "bit_rate": None,
        }
        try:
            if not file or not os.path.isfile(file) or os.path.getsize(file) == 0:
                return empty_info.copy()

            c_flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
            cmd = [
                "ffprobe",
                "-v", "error",
                "-select_streams", "a:0",
                "-show_entries",
                "stream=codec_name,sample_rate,channels,channel_layout,bit_rate,duration:format=duration,bit_rate",
                "-of", "json",
                file,
            ]
            r = self.run_process(
                cmd,
                c_flags=c_flags,
                timeout=30,
                operation="ffprobe_audio_info",
                file_path=file,
            )

            if r.returncode != 0:
                if r.returncode != -999:
                    self.write_problem(
                        "ffprobe_duration_failed",
                        "FFprobe не смог определить длительность файла.",
                        file=file,
                        returncode=r.returncode,
                        elapsed_seconds=getattr(r, "elapsed_seconds", None),
                        process_log_file=getattr(r, "process_log_file", ""),
                        command=self.command_to_text(cmd),
                        command_argv=cmd,
                        stderr_tail=self.trim_text(r.stderr, 8000),
                        stdout_tail=self.trim_text(r.stdout, 2000),
                    )
                return empty_info.copy()

            payload = self.extract_ffprobe_json(r.stdout) or self.extract_ffprobe_json(r.stderr)
            format_info = payload.get("format") if isinstance(payload.get("format"), dict) else {}
            streams = payload.get("streams") if isinstance(payload.get("streams"), list) else []
            stream_info = streams[0] if streams and isinstance(streams[0], dict) else {}

            duration = 0
            duration_source = None
            # N/A and non-finite stream values must not mask a usable container
            # duration. A video-only container is never an audio result.
            if stream_info:
                for source, raw_duration in (("stream", stream_info.get("duration")), ("format", format_info.get("duration"))):
                    try:
                        candidate = float(raw_duration)
                    except (TypeError, ValueError):
                        continue
                    if math.isfinite(candidate) and candidate > 0:
                        duration = candidate
                        duration_source = source
                        break

            info = empty_info.copy()
            info["duration_seconds"] = duration if duration > 0 else 0
            info["duration_source"] = duration_source
            for output_key, source_key in (
                ("sample_rate_hz", "sample_rate"),
                ("channels", "channels"),
                ("bit_rate", "bit_rate"),
            ):
                try:
                    raw_value = stream_info.get(source_key)
                    if raw_value in (None, "") and output_key == "bit_rate":
                        raw_value = format_info.get("bit_rate")
                    info[output_key] = int(raw_value) if raw_value not in (None, "") else None
                except (TypeError, ValueError):
                    info[output_key] = None
            info["channel_layout"] = stream_info.get("channel_layout") or None
            info["codec_name"] = stream_info.get("codec_name") or None

            if duration <= 0:
                self.write_problem(
                    "ffprobe_duration_parse_failed",
                    "FFprobe завершился успешно, но длительность не удалось извлечь из вывода.",
                    file=file,
                    command=self.command_to_text(cmd),
                    command_argv=cmd,
                    process_log_file=getattr(r, "process_log_file", ""),
                    output_tail=self.trim_text(r.stderr, 8000),
                )
            return info
        except Exception as e:
            self.write_problem(
                "duration_unhandled_exception",
                "Внутренняя ошибка при определении длительности.",
                file=file,
                exception=f"{type(e).__name__}: {e}",
                traceback=traceback.format_exc(),
            )
            return empty_info.copy()

    def get_duration(self, file):
        """Возвращает длительность файла через ffprobe и логирует реальные причины ошибок."""
        return float(self.get_audio_info(file).get("duration_seconds", 0) or 0)

    def format_duration(self, sec):
        h, r = divmod(int(sec), 3600)
        m, s = divmod(r, 60)
        return f"{h:02d}:{m:02d}:{s:02d}"
