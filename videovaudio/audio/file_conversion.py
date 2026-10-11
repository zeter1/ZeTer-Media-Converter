"""Single-video -> MP3 conversion, fallback and validation.

CODEX ROUTE: open this file only when the task matches this responsibility.
Methods are moved whole from the previous owner module; behavior is intentionally unchanged.
"""

import os
import re
import traceback
import subprocess
import time
from collections import Counter
import json
import shutil
import math
from concurrent.futures import ThreadPoolExecutor, as_completed


class AudioFileConversionMixin:
    def convert_single_file(self, file_data):
        """Многопоточная конвертация одного видео с честной диагностикой ffmpeg."""
        index, file_path, temp_dir, separate_dir, c_flags = file_data

        if self.cancel_requested:
            return {"success": False, "cancelled": True, "index": index, "file": file_path}

        base_name = os.path.basename(file_path)

        file_id = f"{index + 1:03d}"
        out_path = os.path.join(temp_dir, f"{file_id}.mp3")
        final_separate = self.build_output_path(
            separate_dir,
            f"{file_id}_",
            base_name,
        )

        # CODEX-PHASE A1: build the primary/fallback FFmpeg command.
        def build_conversion_command(disable_joint_stereo=False):
            audio_filter = (
                f"aresample={self.OUTPUT_SAMPLE_RATE_HZ}:async=1:first_pts=0"
                if disable_joint_stereo
                else f"aresample={self.OUTPUT_SAMPLE_RATE_HZ},asetpts=N/SR/TB"
            )
            command = [
                *self.ffmpeg_base_command(),
                "-nostdin", "-y", "-i", file_path,
                "-map", "0:a:0",
                "-vn",
                "-af", audio_filter,
                "-ar", str(self.OUTPUT_SAMPLE_RATE_HZ),
                "-ac", str(self.OUTPUT_CHANNELS),
                "-c:a", "libmp3lame",
            ]
            if disable_joint_stereo:
                command.extend(["-joint_stereo", "0"])
            command.extend([
                "-b:a", self.bitrate,
                "-map_metadata", "0",
                out_path,
            ])
            return command

        cmd = build_conversion_command()
        fallback_mode = ""
        fallback_event_id = None
        fallback_recovery_details = {}

        # CODEX-PHASE A2: run the primary MP3 conversion attempt.
        result = self.run_process(
            cmd,
            c_flags=c_flags,
            timeout=1800,
            operation="convert_single_file",
            file_path=file_path,
            report_process_failure=False,
        )

        if result.returncode == -999:
            return {"success": False, "cancelled": True, "index": index, "file": file_path}

        if result.returncode != 0:
            diagnosis = self.diagnose_ffmpeg_failure(result.stderr, file_path, out_path)
            # CODEX-PHASE A3: classify failure and execute the libmp3lame compatibility fallback when applicable.
            if (
                diagnosis.get("code") == "libmp3lame_joint_stereo_assertion"
                and not self.cancel_requested
            ):
                initial_result = result
                fallback_event_id = self.write_problem(
                    "libmp3lame_joint_stereo_assertion_retry",
                    (
                        "Кодировщик MP3 аварийно остановился в joint-stereo режиме. "
                        "Пробую один совместимый повтор без joint stereo."
                    ),
                    severity="warning",
                    file=file_path,
                    output=out_path,
                    returncode=initial_result.returncode,
                    elapsed_seconds=getattr(initial_result, "elapsed_seconds", None),
                    process_log_file=getattr(initial_result, "process_log_file", ""),
                    command=self.command_to_text(cmd),
                    command_argv=cmd,
                    diagnosis=diagnosis,
                    diagnostic_excerpt=initial_result.stderr,
                )

                partial_cleanup_error = ""
                try:
                    if os.path.exists(out_path):
                        os.remove(out_path)
                except OSError as error:
                    partial_cleanup_error = f"{type(error).__name__}: {error}"
                    self.logger.warning(
                        "LAME_FALLBACK_PARTIAL_CLEANUP_FAILED file=%s output=%s error=%s",
                        file_path,
                        out_path,
                        partial_cleanup_error,
                    )

                fallback_cmd = build_conversion_command(disable_joint_stereo=True)
                fallback_result = self.run_process(
                    fallback_cmd,
                    c_flags=c_flags,
                    timeout=1800,
                    operation="convert_single_file_lame_compatibility_fallback",
                    file_path=file_path,
                    report_process_failure=False,
                )
                combined_elapsed = sum(
                    float(getattr(item, "elapsed_seconds", 0) or 0)
                    for item in (initial_result, fallback_result)
                )
                fallback_result.elapsed_seconds = combined_elapsed

                if fallback_result.returncode == -999:
                    return {
                        "success": False,
                        "cancelled": True,
                        "index": index,
                        "file": file_path,
                    }

                if fallback_result.returncode == 0:
                    fallback_mode = "libmp3lame_no_joint_stereo"
                    fallback_recovery_details = {
                        "file": file_path,
                        "output": out_path,
                        "elapsed_seconds": combined_elapsed,
                        "fallback_mode": fallback_mode,
                        "command_argv": fallback_cmd,
                        "initial_returncode": initial_result.returncode,
                        "fallback_returncode": fallback_result.returncode,
                        "initial_process_log_file": getattr(
                            initial_result,
                            "process_log_file",
                            "",
                        ),
                    }
                    if partial_cleanup_error:
                        fallback_recovery_details[
                            "partial_output_cleanup_error"
                        ] = partial_cleanup_error
                    result = fallback_result
                    cmd = fallback_cmd
                else:
                    fallback_diagnosis = self.diagnose_ffmpeg_failure(
                        fallback_result.stderr,
                        file_path,
                        out_path,
                    )
                    failure_details = {
                        "file": file_path,
                        "output": out_path,
                        "returncode": fallback_result.returncode,
                        "elapsed_seconds": combined_elapsed,
                        "process_log_file": getattr(
                            fallback_result,
                            "process_log_file",
                            "",
                        ),
                        "command_argv": fallback_cmd,
                        "diagnosis": fallback_diagnosis,
                        "diagnostic_excerpt": fallback_result.stderr,
                    }
                    if partial_cleanup_error:
                        failure_details[
                            "partial_output_cleanup_error"
                        ] = partial_cleanup_error
                    self.mark_problem_unresolved(
                        fallback_event_id,
                        "libmp3lame_no_joint_stereo",
                        **failure_details,
                    )
                    result = fallback_result
                    cmd = fallback_cmd
                    diagnosis = fallback_diagnosis

            if result.returncode != 0:
                no_audio = diagnosis.get("code") == "no_audio_stream"
                retained_process_log = getattr(result, "process_log_file", "")
                if diagnosis.get("code") not in {
                    "ffmpeg_failed",
                    "libmp3lame_joint_stereo_assertion",
                }:
                    try:
                        if retained_process_log and os.path.isfile(retained_process_log):
                            os.remove(retained_process_log)
                        retained_process_log = ""
                    except OSError:
                        pass
                problem_kind = "input_skipped_no_audio" if no_audio else "media_file_skipped"
                message = (
                    "В видео нет звуковой дорожки; файл пропущен, остальные видео продолжают обрабатываться."
                    if no_audio
                    else "Проблемное видео пропущено; остальные исправные видео продолжают обрабатываться."
                )
                self.write_problem(
                    problem_kind,
                    message,
                    severity="info" if no_audio else "warning",
                    parent_event_id=fallback_event_id,
                    file=file_path,
                    output=out_path,
                    returncode=result.returncode,
                    elapsed_seconds=getattr(result, "elapsed_seconds", None),
                    process_log_file=retained_process_log,
                    command=self.command_to_text(cmd),
                    command_argv=cmd,
                    diagnosis=diagnosis,
                    codex={
                        "likely_cause": diagnosis.get("likely_cause"),
                        "codex_action": diagnosis.get("codex_action"),
                        "user_action": diagnosis.get("user_action"),
                        "impact": "Файл пропущен; обработка остальных видео продолжается.",
                    },
                    diagnostic_excerpt=result.stderr,
                )
                return {
                    "success": False,
                    "skipped": True,
                    "skip_code": diagnosis.get("code"),
                    "index": index,
                    "file": file_path,
                    "name": base_name,
                    "reason": diagnosis.get("likely_cause"),
                    "process_log_file": retained_process_log,
                }

        # CODEX-PHASE A4: validate staged audio before publishing the per-video MP3.
        if os.path.exists(out_path) and os.path.getsize(out_path) > 0:
            try:
                audio_info = self.get_audio_info(out_path)
                duration_seconds = float(audio_info.get("duration_seconds", 0) or 0)
                if not math.isfinite(duration_seconds) or duration_seconds <= 0:
                    if fallback_event_id:
                        self.mark_problem_unresolved(
                            fallback_event_id,
                            fallback_mode,
                            file=file_path,
                            output=out_path,
                            reason="fallback_output_duration_unknown",
                        )
                    self.write_problem(
                        "media_file_skipped",
                        "MP3 создан, но его длительность не определяется; файл исключён из склейки.",
                        severity="warning",
                        parent_event_id=fallback_event_id,
                        file=file_path,
                        output=out_path,
                        output_facts=self.path_facts(out_path),
                        codex={
                            "impact": "Только этот файл исключён; остальные видео продолжают обрабатываться.",
                            "likely_cause": "Получившийся MP3 пуст, повреждён или не читается FFprobe.",
                            "codex_action": "Проверить связанное событие ffprobe и вывод исходной конвертации.",
                        },
                    )
                    try:
                        os.remove(out_path)
                    except OSError:
                        pass
                    return {
                        "success": False,
                        "skipped": True,
                        "skip_code": "output_duration_unknown",
                        "index": index,
                        "file": file_path,
                        "name": base_name,
                        "reason": "Длительность созданного MP3 не определяется",
                    }
                if fallback_event_id:
                    input_audio_info = self.get_audio_info(file_path)
                    input_duration_seconds = float(
                        input_audio_info.get("duration_seconds", 0) or 0
                    )
                    if input_audio_info.get("duration_source") == "format":
                        input_duration_seconds = 0
                    mismatch = False
                    difference_seconds = None
                    tolerance_seconds = None
                    if input_duration_seconds > 0:
                        (
                            mismatch,
                            difference_seconds,
                            tolerance_seconds,
                        ) = self.duration_mismatch(
                            input_duration_seconds,
                            duration_seconds,
                        )
                    if mismatch:
                        diagnosis = {
                            "code": "fallback_duration_mismatch",
                            "likely_cause": (
                                "Резервное кодирование завершилось, но длительность "
                                "MP3 заметно отличается от временной шкалы исходника."
                            ),
                            "codex_action": (
                                "Не публиковать укороченный MP3; проверить фильтр "
                                "синхронизации и временные метки исходного аудио."
                            ),
                            "user_action": "Сохранить исходник и прислать свежие логи.",
                            "input": self.path_facts(file_path),
                            "output": self.path_facts(out_path),
                        }
                        self.mark_problem_unresolved(
                            fallback_event_id,
                            fallback_mode,
                            file=file_path,
                            output=out_path,
                            diagnosis=diagnosis,
                            expected_duration_seconds=input_duration_seconds,
                            actual_duration_seconds=duration_seconds,
                            difference_seconds=difference_seconds,
                            tolerance_seconds=tolerance_seconds,
                        )
                        self.write_problem(
                            "media_file_skipped",
                            "Резервный MP3 не прошёл проверку длительности; файл исключён из склейки.",
                            severity="warning",
                            parent_event_id=fallback_event_id,
                            file=file_path,
                            output=out_path,
                            diagnosis=diagnosis,
                            expected_duration_seconds=input_duration_seconds,
                            actual_duration_seconds=duration_seconds,
                            difference_seconds=difference_seconds,
                            tolerance_seconds=tolerance_seconds,
                        )
                        try:
                            os.remove(out_path)
                        except OSError:
                            pass
                        return {
                            "success": False,
                            "skipped": True,
                            "skip_code": "fallback_duration_mismatch",
                            "index": index,
                            "file": file_path,
                            "name": base_name,
                            "reason": diagnosis["likely_cause"],
                        }

                    fallback_recovery_details["duration_validation"] = {
                        "status": (
                            "validated"
                            if input_duration_seconds > 0
                            else "input_duration_unknown"
                        ),
                        "expected_duration_seconds": input_duration_seconds,
                        "actual_duration_seconds": duration_seconds,
                        "difference_seconds": difference_seconds,
                        "tolerance_seconds": tolerance_seconds,
                    }
                if not fallback_event_id:
                    input_info = self.get_audio_info(file_path)
                    expected = float(input_info.get("duration_seconds", 0) or 0)
                    if (input_info.get("duration_source") != "format"
                            and expected > 0
                            and self.duration_mismatch(expected, duration_seconds)[0]):
                        self.write_problem(
                            "media_file_skipped",
                            "MP3 не прошёл проверку длительности исходного аудио; файл исключён из склейки.",
                            severity="warning",
                            file=file_path,
                            output=out_path,
                            expected_duration_seconds=expected,
                            actual_duration_seconds=duration_seconds,
                        )
                        return {
                            "success": False, "skipped": True,
                            "skip_code": "output_duration_mismatch",
                            "index": index, "file": file_path, "name": base_name,
                            "reason": "Длительность MP3 отличается от исходного аудио",
                        }
                if self.cancel_requested:
                    return {"success": False, "cancelled": True, "index": index, "file": file_path}
                # Both directories belong to the same course filesystem. A failed
                # replace leaves the previous result intact, including on Windows.
                os.replace(out_path, final_separate)
                if fallback_event_id:
                    fallback_recovery_details["output"] = final_separate
                    self.mark_problem_recovered(
                        fallback_event_id, fallback_mode, **fallback_recovery_details,
                    )
                return {
                    "success": True,
                    "index": index,
                    "input_file": file_path,
                    "path": final_separate,
                    "name": base_name,
                    "duration_seconds": duration_seconds,
                    "input_size_bytes": os.path.getsize(file_path) if os.path.isfile(file_path) else None,
                    "output_size_bytes": os.path.getsize(final_separate),
                    "elapsed_seconds": getattr(result, "elapsed_seconds", None),
                    "process_log_file": getattr(result, "process_log_file", ""),
                    "fallback_mode": fallback_mode,
                    "audio_profile": {
                        "sample_rate_hz": audio_info.get("sample_rate_hz"),
                        "channels": audio_info.get("channels"),
                        "channel_layout": audio_info.get("channel_layout"),
                        "codec_name": audio_info.get("codec_name"),
                        "bit_rate": audio_info.get("bit_rate"),
                    },
                }
            except Exception as e:
                diagnosis = {
                    "code": "move_output_failed",
                    "likely_cause": "Не удалось заменить или переместить итоговый отдельный MP3.",
                    "codex_action": "Проверить длину пути, права и блокировку существующего MP3.",
                    "user_action": "Закрыть проигрыватели, использующие файл, и повторить папку.",
                    "input": self.path_facts(file_path),
                    "output": self.path_facts(final_separate),
                }
                if fallback_event_id:
                    self.mark_problem_unresolved(
                        fallback_event_id,
                        fallback_mode,
                        file=file_path,
                        output=final_separate,
                        diagnosis=diagnosis,
                        exception=f"{type(e).__name__}: {e}",
                    )
                self.write_problem(
                    "media_file_skipped",
                    "Видео сконвертировано, но отдельный MP3 не удалось сохранить; файл пропущен.",
                    severity="warning",
                    parent_event_id=fallback_event_id,
                    file=file_path,
                    temp_output=out_path,
                    final_output=final_separate,
                    diagnosis=diagnosis,
                    codex={
                        "likely_cause": diagnosis["likely_cause"],
                        "codex_action": diagnosis["codex_action"],
                        "user_action": diagnosis["user_action"],
                        "impact": "Только этот файл не вошёл в итог; обработка остальных продолжается.",
                    },
                    exception=f"{type(e).__name__}: {e}",
                    traceback=traceback.format_exc(),
                )
                return {
                    "success": False,
                    "skipped": True,
                    "skip_code": "move_output_failed",
                    "index": index,
                    "file": file_path,
                    "name": base_name,
                    "reason": str(e),
                }

        # CODEX-PHASE A5: terminal invalid/missing output handling.
        if fallback_event_id:
            self.mark_problem_unresolved(
                fallback_event_id,
                fallback_mode,
                file=file_path,
                output=out_path,
                reason="fallback_output_missing_or_too_small",
            )
        self.write_problem(
            "media_file_skipped",
            "FFmpeg завершился без ошибки, но MP3 не создан или слишком маленький; файл пропущен.",
            severity="warning",
            parent_event_id=fallback_event_id,
            file=file_path,
            output=out_path,
            returncode=result.returncode,
            elapsed_seconds=getattr(result, "elapsed_seconds", None),
            process_log_file=getattr(result, "process_log_file", ""),
            command=self.command_to_text(cmd),
            command_argv=cmd,
            diagnostic_excerpt=result.stderr,
            codex={
                "impact": "Только этот файл не вошёл в итог; остальные продолжают обрабатываться.",
                "likely_cause": "FFmpeg не записал полезные аудиоданные, несмотря на нулевой код возврата.",
                "codex_action": "Проверить размер результата, карту потоков и окончание вывода FFmpeg.",
            },
        )
        return {
            "success": False,
            "skipped": True,
            "skip_code": "output_missing_or_too_small",
            "index": index,
            "file": file_path,
            "name": base_name,
            "reason": "output_missing_or_too_small",
        }
