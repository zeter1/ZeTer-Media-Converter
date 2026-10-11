"""Video probing, target profile selection, FFmpeg normalization command and validation.

CODEX ROUTE: open this file only when the task matches this responsibility.
Methods are moved whole from the previous owner module; behavior is intentionally unchanged.
"""

import os
import traceback
import subprocess
import time
from collections import Counter
import shutil


class VideoProfileMixin:
    @staticmethod
    def parse_frame_rate(value):
        """Преобразует ffprobe-частоту вида 30000/1001 в число."""
        try:
            text = str(value or "")
            if "/" in text:
                numerator, denominator = text.split("/", 1)
                denominator_value = float(denominator)
                if denominator_value == 0:
                    return 0.0
                return float(numerator) / denominator_value
            return float(text)
        except (TypeError, ValueError, ZeroDivisionError):
            return 0.0

    def get_video_info(self, file):
        """Читает длительность и параметры первого видео/аудиопотока."""
        empty_info = {
            "duration_seconds": 0.0,
            "has_video": False,
            "video_codec": None,
            "video_profile": None,
            "video_level": None,
            "width": None,
            "height": None,
            "pixel_format": None,
            "frame_rate": None,
            "time_base": None,
            "has_audio": False,
            "audio_codec": None,
            "audio_sample_rate_hz": None,
            "audio_channels": None,
            "audio_channel_layout": None,
        }
        try:
            if not file or not os.path.isfile(file) or os.path.getsize(file) < 1024:
                return empty_info.copy()

            cmd = [
                "ffprobe",
                "-v", "error",
                "-show_entries",
                (
                    "stream=codec_type,codec_name,profile,level,width,height,"
                    "pix_fmt,avg_frame_rate,r_frame_rate,time_base,sample_rate,"
                    "channels,channel_layout,duration:format=duration"
                ),
                "-of", "json",
                file,
            ]
            c_flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
            result = self.run_process(
                cmd,
                c_flags=c_flags,
                timeout=60,
                operation="ffprobe_video_info",
                file_path=file,
                report_process_failure=False,
            )
            if result.returncode != 0:
                if result.returncode != -999:
                    self.write_problem(
                        "video_ffprobe_failed",
                        "Не удалось прочитать параметры видео для объединения.",
                        file=file,
                        returncode=result.returncode,
                        command_argv=cmd,
                        process_log_file=getattr(result, "process_log_file", ""),
                        diagnostic_excerpt=result.stderr,
                    )
                return empty_info.copy()

            payload = (
                self.extract_ffprobe_json(result.stdout)
                or self.extract_ffprobe_json(result.stderr)
            )
            streams = payload.get("streams")
            if not isinstance(streams, list):
                streams = []
            format_info = payload.get("format")
            if not isinstance(format_info, dict):
                format_info = {}
            video_stream = next(
                (
                    stream for stream in streams
                    if isinstance(stream, dict)
                    and stream.get("codec_type") == "video"
                ),
                {},
            )
            audio_stream = next(
                (
                    stream for stream in streams
                    if isinstance(stream, dict)
                    and stream.get("codec_type") == "audio"
                ),
                {},
            )

            info = empty_info.copy()
            try:
                duration = float(
                    format_info.get("duration")
                    or video_stream.get("duration")
                    or 0
                )
            except (TypeError, ValueError):
                duration = 0.0
            info["duration_seconds"] = duration if duration > 0 else 0.0
            info["has_video"] = bool(video_stream)
            info["video_codec"] = video_stream.get("codec_name") or None
            info["video_profile"] = video_stream.get("profile") or None
            info["video_level"] = video_stream.get("level")
            info["pixel_format"] = video_stream.get("pix_fmt") or None
            info["frame_rate"] = (
                video_stream.get("avg_frame_rate")
                or video_stream.get("r_frame_rate")
                or None
            )
            info["time_base"] = video_stream.get("time_base") or None
            for key in ("width", "height"):
                try:
                    raw_value = video_stream.get(key)
                    info[key] = int(raw_value) if raw_value not in (None, "") else None
                except (TypeError, ValueError):
                    info[key] = None

            info["has_audio"] = bool(audio_stream)
            info["audio_codec"] = audio_stream.get("codec_name") or None
            info["audio_channel_layout"] = (
                audio_stream.get("channel_layout") or None
            )
            for output_key, source_key in (
                ("audio_sample_rate_hz", "sample_rate"),
                ("audio_channels", "channels"),
            ):
                try:
                    raw_value = audio_stream.get(source_key)
                    info[output_key] = (
                        int(raw_value)
                        if raw_value not in (None, "")
                        else None
                    )
                except (TypeError, ValueError):
                    info[output_key] = None
            return info
        except Exception as error:
            self.write_problem(
                "video_probe_unhandled_exception",
                "Внутренняя ошибка чтения параметров видео.",
                file=file,
                exception=f"{type(error).__name__}: {error}",
                traceback=traceback.format_exc(),
            )
            return empty_info.copy()

    def video_stream_copy_key(self, info):
        """Параметры, которые должны совпасть для безопасной быстрой склейки."""
        return (
            info.get("video_codec"),
            info.get("video_profile"),
            info.get("video_level"),
            info.get("width"),
            info.get("height"),
            info.get("pixel_format"),
            info.get("frame_rate"),
            info.get("time_base"),
            info.get("has_audio"),
            info.get("audio_codec"),
            info.get("audio_sample_rate_hz"),
            info.get("audio_channels"),
            info.get("audio_channel_layout"),
        )

    def video_group_can_copy(self, items):
        """Разрешает copy только для одинаковых, интернет-совместимых MP4-потоков."""
        if not items:
            return False
        profiles = [item.get("info", {}) for item in items]
        first_key = self.video_stream_copy_key(profiles[0])
        return all(
            profile.get("has_video")
            and profile.get("video_codec") == "h264"
            and profile.get("pixel_format") in {"yuv420p", "yuvj420p"}
            and profile.get("has_audio")
            and profile.get("audio_codec") == "aac"
            and self.video_stream_copy_key(profile) == first_key
            for profile in profiles
        )

    def choose_video_target_profile(self, items):
        """Формирует единый профиль из настроек и частоты кадров курса."""
        frame_rates = Counter()
        for item in items:
            info = item.get("info", {})
            fps = self.parse_frame_rate(info.get("frame_rate"))
            if fps > 0:
                frame_rates[round(fps, 3)] += 1

        settings = dict(getattr(self, "active_video_settings", {}) or {})
        resolution = settings.get("resolution", self.DEFAULT_VIDEO_RESOLUTION)
        width, height = self.VIDEO_RESOLUTIONS.get(
            resolution,
            self.VIDEO_RESOLUTIONS[self.DEFAULT_VIDEO_RESOLUTION],
        )
        width = max(2, width - width % 2)
        height = max(2, height - height % 2)

        if frame_rates:
            fps = max(
                frame_rates,
                key=lambda value: (frame_rates[value], value),
            )
        else:
            fps = 30.0
        fps = min(60.0, max(15.0, float(fps)))
        return {
            "width": width,
            "height": height,
            "fps": fps,
            "resolution": resolution,
            "video_bitrate": settings.get(
                "video_bitrate",
                self.DEFAULT_VIDEO_BITRATE,
            ),
            "audio_bitrate": settings.get(
                "audio_bitrate",
                self.DEFAULT_VIDEO_AUDIO_BITRATE,
            ),
            "force_encode": bool(settings.get("force_encode", True)),
            "video_codec": "h264",
            "pixel_format": "yuv420p",
            "audio_codec": "aac",
            "audio_sample_rate_hz": self.VIDEO_AUDIO_SAMPLE_RATE_HZ,
            "audio_channels": self.VIDEO_AUDIO_CHANNELS,
        }

    def video_filter_for_target(self, target):
        width = int(target["width"])
        height = int(target["height"])
        fps = float(target["fps"])
        return (
            f"scale={width}:{height}:force_original_aspect_ratio=decrease:"
            "flags=lanczos,"
            f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:color=black,"
            f"setsar=1,fps={fps:.3f},format=yuv420p"
        )

    def build_video_normalize_command(
        self,
        source,
        output,
        source_info,
        target,
        segment_seconds=None,
    ):
        """Строит единый H.264/AAC профиль, добавляя тишину при отсутствии звука."""
        cmd = [*self.ffmpeg_base_command(), "-nostdin", "-y", "-i", source]
        has_audio = bool(source_info.get("has_audio"))
        if not has_audio:
            cmd.extend([
                "-f", "lavfi",
                "-i", (
                    "anullsrc=channel_layout=stereo:"
                    f"sample_rate={self.VIDEO_AUDIO_SAMPLE_RATE_HZ}"
                ),
            ])
        cmd.extend(["-map", "0:v:0", "-map", "0:a:0" if has_audio else "1:a:0"])
        cmd.extend([
            "-vf", self.video_filter_for_target(target),
            "-af", "apad",
            "-c:v", "libx264",
            "-preset", self.VIDEO_NORMALIZE_PRESET,
            "-b:v", str(target["video_bitrate"]),
            "-pix_fmt", "yuv420p",
            "-c:a", "aac",
            "-b:a", str(target["audio_bitrate"]),
            "-ar", str(self.VIDEO_AUDIO_SAMPLE_RATE_HZ),
            "-ac", str(self.VIDEO_AUDIO_CHANNELS),
            "-shortest",
            "-sn", "-dn",
            "-max_muxing_queue_size", "4096",
        ])
        if segment_seconds is None:
            cmd.extend(["-movflags", "+faststart", output])
        else:
            cmd.extend([
                "-force_key_frames",
                f"expr:gte(t,n_forced*{segment_seconds:.3f})",
                "-f", "segment",
                "-segment_time", f"{segment_seconds:.3f}",
                "-reset_timestamps", "1",
                "-segment_start_number", "1",
                "-segment_format", "mp4",
                "-segment_format_options", "movflags=+faststart",
                output,
            ])
        return cmd

    def validate_merged_video(
        self,
        output,
        expected_duration,
        max_duration=None,
        target=None,
    ):
        """Проверяет контейнер, кодеки, длительность и лимит готовой части."""
        info = self.get_video_info(output)
        issues = []
        if not info.get("has_video"):
            issues.append("no_video_stream")
        if info.get("video_codec") != "h264":
            issues.append("video_codec_not_h264")
        if not info.get("has_audio"):
            issues.append("no_audio_stream")
        if info.get("audio_codec") != "aac":
            issues.append("audio_codec_not_aac")
        if target:
            expected_size = (
                int(target.get("width") or 0),
                int(target.get("height") or 0),
            )
            actual_size = (
                int(info.get("width") or 0),
                int(info.get("height") or 0),
            )
            if actual_size != expected_size:
                issues.append("resolution_mismatch")
        actual_duration = float(info.get("duration_seconds") or 0)
        if actual_duration <= 0:
            issues.append("duration_unknown")
        mismatch, difference, tolerance = self.duration_mismatch(
            expected_duration,
            actual_duration,
        )
        if mismatch:
            issues.append("duration_mismatch")
        if (
            max_duration is not None
            and actual_duration
            > float(max_duration) + self.VIDEO_MAX_DURATION_OVERAGE_SECONDS
        ):
            issues.append("duration_over_limit")
        return {
            "ok": not issues,
            "issues": issues,
            "expected_duration_seconds": float(expected_duration or 0),
            "actual_duration_seconds": actual_duration,
            "difference_seconds": difference,
            "tolerance_seconds": tolerance,
            "max_duration_seconds": max_duration,
            "target_profile": target,
            "info": info,
        }
