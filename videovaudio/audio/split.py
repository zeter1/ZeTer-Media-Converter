"""Split a full MP3 into validated <=10-hour outputs.

CODEX ROUTE: open this file only when the task matches this responsibility.
Methods are moved whole from the previous owner module; behavior is intentionally unchanged.
"""

import os
import traceback
import subprocess
import json
import tempfile
import shutil
import math


class AudioSplitMixin:
    def split_file(
        self,
        src,
        out_dir,
        c_flags,
        folder_index=1,
        total_folders=1,
        known_duration=None,
        output_label=None,
    ):
        """Проверяет полный набор временных частей и затем публикует без перезаписи."""
        stage = None
        published = []
        retain_stage = False
        phase = "splitting"
        self.last_split_validation = {"status": "started", "source": src, "parts": []}
        try:
            stage = tempfile.mkdtemp(prefix=".s", dir=out_dir)
            if not self._split_file_into_stage(
                src, out_dir, c_flags, folder_index, total_folders,
                known_duration, output_label, stage,
            ):
                return False
            if self.cancel_requested:
                self.last_split_validation["status"] = "cancelled"
                return False
            phase = "publishing"
            parts = self.last_split_validation["parts"]
            mapping = [(part["file"], os.path.join(out_dir, os.path.basename(part["file"])))
                       for part in parts]
            if len({os.path.normcase(target) for _, target in mapping}) != len(mapping):
                raise ValueError("Повторяющиеся имена итоговых частей")
            for candidate, target in mapping:
                if not os.path.isfile(candidate) or os.path.lexists(target):
                    raise FileExistsError(f"Нельзя опубликовать часть без перезаписи: {target}")
            self.last_split_validation["status"] = "publishing"
            for candidate, target in mapping:
                # On Windows rename fails if the destination appeared after the
                # preflight. All files are on the output filesystem.
                os.rename(candidate, target)
                published.append((target, candidate))
            for part, (_, target) in zip(parts, mapping):
                part["file"] = target
            self.last_split_validation["status"] = "validated"
            return True
        except Exception as error:
            rollback_errors = []
            for target, candidate in reversed(published):
                try:
                    os.rename(target, candidate)
                except OSError as rollback_error:
                    retain_stage = True
                    rollback_errors.append(f"{target}: {rollback_error}")
            self.last_split_validation["status"] = (
                "failed_publication" if phase == "publishing" else "failed_exception"
            )
            self.write_problem(
                "split_publication_failed" if phase == "publishing" else "split_unhandled_exception",
                "Разбивка не завершена; набор частей не опубликован полностью.",
                source=src, staging_dir=stage,
                exception=f"{type(error).__name__}: {error}",
                rollback_errors=rollback_errors,
            )
            return False
        finally:
            if stage and not retain_stage:
                try:
                    shutil.rmtree(stage)
                except OSError as error:
                    self.write_problem(
                        "split_staging_cleanup_failed",
                        "Не удалось убрать временные части аудио.",
                        severity="warning", staging_dir=stage,
                        exception=f"{type(error).__name__}: {error}",
                    )

    def _split_file_into_stage(
        self, src, out_dir, c_flags, folder_index, total_folders,
        known_duration, output_label, staging_dir,
    ):
        """Точная разбивка ≤10 часов. Возвращает True только если все части созданы."""
        # CODEX-PHASE S1: establish duration contract and target part length.
        total_duration = float(known_duration or 0) or self.get_duration(src)
        self.last_split_validation = {
            "status": "started",
            "source": src,
            "expected_total_duration_seconds": total_duration,
            "max_part_duration_seconds": self.SPLIT_HOURS * 3600,
            "parts": [],
        }
        if not math.isfinite(total_duration) or total_duration <= 0:
            self.log_message("❌ Не удалось определить длительность полного аудио", level="error")
            self.write_problem(
                "split_duration_unknown",
                "Не удалось определить длительность файла для разбивки.",
                file=src,
            )
            self.last_split_validation["status"] = "failed_duration_unknown"
            return False

        max_duration_sec = self.SPLIT_HOURS * 3600
        frame_duration_seconds = (
            self.MP3_FRAME_SAMPLES / self.OUTPUT_SAMPLE_RATE_HZ
        )
        boundary_margin_seconds = (
            frame_duration_seconds * self.SPLIT_BOUNDARY_MARGIN_FRAMES
        )
        target_part_duration_seconds = max(
            1.0,
            max_duration_sec - boundary_margin_seconds,
        )
        expected_parts = int(
            (
                total_duration
                + target_part_duration_seconds
                - 0.001
            )
            // target_part_duration_seconds
        )
        self.last_split_validation.update({
            "target_part_duration_seconds": (
                target_part_duration_seconds
            ),
            "boundary_margin_seconds": boundary_margin_seconds,
            "mp3_frame_duration_seconds": frame_duration_seconds,
            "maximum_allowed_overage_seconds": (
                self.SPLIT_MAX_OVERAGE_SECONDS
            ),
        })
        self.log_message(f"⏱️  Разбивка без повторного перекодирования: {self.format_duration(total_duration)} → ≤{self.SPLIT_HOURS}ч")

        start_time = 0.0
        part_num = 1
        label = output_label or os.path.basename(os.path.dirname(out_dir))
        created_parts = []
        created_part_durations = []
        created_part_modes = []
        created_part_requested_durations = []

        # CODEX-PHASE S2: create each part with copy-first / transcode-fallback logic.
        while start_time < total_duration - 0.001:
            if self.cancel_requested:
                self.last_split_validation["status"] = "cancelled"
                return False

            part_duration = min(
                target_part_duration_seconds,
                total_duration - start_time,
            )
            out_file = self.build_audio_split_output_path(
                out_dir,
                label,
                part_number=part_num,
                expected_parts=expected_parts,
            )
            out_file = os.path.join(staging_dir, os.path.basename(out_file))

            split_mode = "copy"
            part_retry_event_id = None
            cmd = [
                *self.ffmpeg_base_command(),
                "-nostdin",
                "-y",
                "-ss", f"{start_time:.3f}",
                "-i", src,
                "-t", f"{part_duration:.3f}",
                "-c:a", "copy",
                out_file
            ]

            split_result = self.run_process(
                cmd,
                c_flags=c_flags,
                operation=f"split_part_{part_num}",
                file_path=src
            )

            if split_result.returncode == -999 or self.cancel_requested:
                self.last_split_validation["status"] = "cancelled"
                return False

            if split_result.returncode != 0:
                part_retry_event_id = self.write_problem(
                    "ffmpeg_split_copy_failed_retry_transcode",
                    "Быстрая разбивка без перекодирования не сработала. Пробую fallback с перекодированием.",
                    severity="warning",
                    source=src,
                    output=out_file,
                    part_num=part_num,
                    start_time=start_time,
                    part_duration=part_duration,
                    command=self.command_to_text(cmd),
                    command_argv=cmd,
                    returncode=split_result.returncode,
                    elapsed_seconds=getattr(split_result, "elapsed_seconds", None),
                    process_log_file=getattr(split_result, "process_log_file", ""),
                    stderr_tail=self.trim_text(split_result.stderr, 12000),
                )
                try:
                    if os.path.exists(out_file):
                        os.remove(out_file)
                except Exception as e:
                    self.write_problem(
                        "split_partial_output_remove_failed",
                        "Не удалось удалить неполную часть перед fallback-разбивкой.",
                        output=out_file,
                        part_num=part_num,
                        exception=f"{type(e).__name__}: {e}",
                    )

                split_mode = "transcode_fallback"
                cmd = [
                    *self.ffmpeg_base_command(),
                    "-nostdin",
                    "-y",
                    "-ss", f"{start_time:.3f}",
                    "-i", src,
                    "-t", f"{part_duration:.3f}",
                    "-af", f"aresample={self.OUTPUT_SAMPLE_RATE_HZ},asetpts=N/SR/TB",
                    "-ar", str(self.OUTPUT_SAMPLE_RATE_HZ),
                    "-ac", str(self.OUTPUT_CHANNELS),
                    "-c:a", "libmp3lame",
                    "-b:a", self.bitrate,
                    out_file
                ]
                split_result = self.run_process(
                    cmd,
                    c_flags=c_flags,
                    operation=f"split_part_{part_num}_transcode_fallback",
                    file_path=src
                )

                if split_result.returncode == -999 or self.cancel_requested:
                    self.last_split_validation["status"] = "cancelled"
                    return False

            if split_result.returncode != 0:
                if part_retry_event_id:
                    self.mark_problem_unresolved(
                        part_retry_event_id,
                        "split_part_transcode_fallback",
                        source=src,
                        output=out_file,
                        part_num=part_num,
                        returncode=split_result.returncode,
                    )
                self.log_message(f"   ❌ Часть {part_num} не создана: ffmpeg returncode={split_result.returncode}", level="error")
                self.write_problem(
                    "ffmpeg_split_failed",
                    "FFmpeg не смог создать часть аудио.",
                    source=src,
                    output=out_file,
                    split_mode=split_mode,
                    part_num=part_num,
                    start_time=start_time,
                    part_duration=part_duration,
                    command=self.command_to_text(cmd),
                    command_argv=cmd,
                    returncode=split_result.returncode,
                    elapsed_seconds=getattr(split_result, "elapsed_seconds", None),
                    process_log_file=getattr(split_result, "process_log_file", ""),
                    stderr_tail=self.trim_text(split_result.stderr, 12000),
                    stdout_tail=self.trim_text(split_result.stdout, 4000),
                )
                self.last_split_validation["status"] = "failed_ffmpeg"
                return False

            if (
                split_mode == "copy"
                and (
                    not os.path.exists(out_file)
                    or os.path.getsize(out_file) <= 0
                )
            ):
                part_retry_event_id = self.write_problem(
                    "split_copy_output_missing_retry_transcode",
                    "Быстрое разрезание завершилось без полезного MP3. Повторяю часть с точным перекодированием.",
                    severity="warning",
                    source=src,
                    output=out_file,
                    part_num=part_num,
                    start_time=start_time,
                    part_duration=part_duration,
                    exists=os.path.exists(out_file),
                    size=os.path.getsize(out_file) if os.path.exists(out_file) else 0,
                    diagnostic_excerpt=split_result.stderr,
                    command=self.command_to_text(cmd),
                    command_argv=cmd,
                )
                try:
                    if os.path.exists(out_file):
                        os.remove(out_file)
                except Exception as e:
                    self.write_problem(
                        "split_empty_output_remove_failed",
                        "Не удалось удалить пустую часть перед точным повтором.",
                        output=out_file,
                        exception=f"{type(e).__name__}: {e}",
                    )

                split_mode = "transcode_fallback"
                cmd = [
                    *self.ffmpeg_base_command(),
                    "-nostdin",
                    "-y",
                    "-ss", f"{start_time:.3f}",
                    "-i", src,
                    "-t", f"{part_duration:.3f}",
                    "-af", f"aresample={self.OUTPUT_SAMPLE_RATE_HZ},asetpts=N/SR/TB",
                    "-ar", str(self.OUTPUT_SAMPLE_RATE_HZ),
                    "-ac", str(self.OUTPUT_CHANNELS),
                    "-c:a", "libmp3lame",
                    "-b:a", self.bitrate,
                    out_file,
                ]
                split_result = self.run_process(
                    cmd,
                    c_flags=c_flags,
                    operation=f"split_part_{part_num}_empty_fallback",
                    file_path=src,
                )
                if split_result.returncode == -999 or self.cancel_requested:
                    self.last_split_validation["status"] = "cancelled"
                    return False

                if split_result.returncode != 0:
                    self.mark_problem_unresolved(
                        part_retry_event_id,
                        "split_empty_output_transcode_fallback",
                        source=src,
                        output=out_file,
                        part_num=part_num,
                        returncode=split_result.returncode,
                    )
                    self.write_problem(
                        "split_empty_output_fallback_failed",
                        "Точный повтор после пустого copy-результата завершился ошибкой.",
                        source=src,
                        output=out_file,
                        part_num=part_num,
                        returncode=split_result.returncode,
                        command=self.command_to_text(cmd),
                        command_argv=cmd,
                        process_log_file=getattr(split_result, "process_log_file", ""),
                        diagnostic_excerpt=split_result.stderr,
                        parent_event_id=part_retry_event_id,
                    )
                    self.last_split_validation["status"] = "failed_empty_fallback"
                    return False

            if os.path.exists(out_file) and os.path.getsize(out_file) > 0:
                actual_dur = self.get_duration(out_file)
                if actual_dur <= 0:
                    if split_mode == "copy":
                        part_retry_event_id = self.write_problem(
                            "split_copy_duration_invalid_retry_transcode",
                            "Часть создана быстрым copy, но ffprobe не видит длительность. Пробую fallback с перекодированием.",
                            severity="warning",
                            output=out_file,
                            size=os.path.getsize(out_file),
                            command=self.command_to_text(cmd),
                            command_argv=cmd,
                        )
                        try:
                            os.remove(out_file)
                        except Exception:
                            pass

                        split_mode = "transcode_fallback"
                        cmd = [
                            *self.ffmpeg_base_command(),
                            "-nostdin",
                            "-y",
                            "-ss", f"{start_time:.3f}",
                            "-i", src,
                            "-t", f"{part_duration:.3f}",
                            "-af", f"aresample={self.OUTPUT_SAMPLE_RATE_HZ},asetpts=N/SR/TB",
                            "-ar", str(self.OUTPUT_SAMPLE_RATE_HZ),
                            "-ac", str(self.OUTPUT_CHANNELS),
                            "-c:a", "libmp3lame",
                            "-b:a", self.bitrate,
                            out_file
                        ]
                        split_result = self.run_process(
                            cmd,
                            c_flags=c_flags,
                            operation=f"split_part_{part_num}_duration_fallback",
                            file_path=src
                        )
                        if split_result.returncode == -999 or self.cancel_requested:
                            self.last_split_validation["status"] = "cancelled"
                            return False
                        if split_result.returncode != 0:
                            self.mark_problem_unresolved(
                                part_retry_event_id,
                                "split_duration_transcode_fallback",
                                source=src,
                                output=out_file,
                                part_num=part_num,
                                returncode=split_result.returncode,
                            )
                            self.last_split_validation["status"] = "failed_duration_fallback"
                            return False
                        actual_dur = self.get_duration(out_file) if os.path.exists(out_file) and os.path.getsize(out_file) > 0 else 0

                    if actual_dur <= 0:
                        if part_retry_event_id:
                            self.mark_problem_unresolved(
                                part_retry_event_id,
                                "split_duration_transcode_fallback",
                                source=src,
                                output=out_file,
                                part_num=part_num,
                                returncode=split_result.returncode,
                            )
                        self.log_message(f"   ❌ Часть {part_num} создана, но длительность не определяется", level="error")
                        self.write_problem(
                            "split_part_duration_invalid",
                            "Часть создана, но ffprobe не видит длительность.",
                            output=out_file,
                            split_mode=split_mode,
                            size=os.path.getsize(out_file) if os.path.exists(out_file) else 0,
                            parent_event_id=part_retry_event_id,
                        )
                        self.last_split_validation["status"] = "failed_part_duration"
                        return False

                if (
                    split_mode == "copy"
                    and actual_dur
                    > max_duration_sec + self.SPLIT_MAX_OVERAGE_SECONDS
                ):
                    part_retry_event_id = self.write_problem(
                        "split_copy_duration_too_long_retry_transcode",
                        "Быстрая разбивка copy создала часть длиннее лимита. Пробую fallback с перекодированием.",
                        severity="warning",
                        source=src,
                        output=out_file,
                        part_num=part_num,
                        requested_duration_seconds=part_duration,
                        expected_max_seconds=max_duration_sec,
                        actual_duration_seconds=actual_dur,
                        command=self.command_to_text(cmd),
                        command_argv=cmd,
                    )
                    try:
                        os.remove(out_file)
                    except Exception as e:
                        self.write_problem(
                            "split_too_long_output_remove_failed",
                            "Не удалось удалить слишком длинную часть перед fallback-разбивкой.",
                            output=out_file,
                            part_num=part_num,
                            exception=f"{type(e).__name__}: {e}",
                        )

                    split_mode = "transcode_fallback"
                    cmd = [
                        *self.ffmpeg_base_command(),
                        "-nostdin",
                        "-y",
                        "-ss", f"{start_time:.3f}",
                        "-i", src,
                        "-t", f"{part_duration:.3f}",
                        "-af", f"aresample={self.OUTPUT_SAMPLE_RATE_HZ},asetpts=N/SR/TB",
                        "-ar", str(self.OUTPUT_SAMPLE_RATE_HZ),
                        "-ac", str(self.OUTPUT_CHANNELS),
                        "-c:a", "libmp3lame",
                        "-b:a", self.bitrate,
                        out_file
                    ]
                    split_result = self.run_process(
                        cmd,
                        c_flags=c_flags,
                        operation=f"split_part_{part_num}_too_long_fallback",
                        file_path=src
                    )

                    if split_result.returncode == -999 or self.cancel_requested:
                        self.last_split_validation["status"] = "cancelled"
                        return False

                    actual_dur = self.get_duration(out_file) if os.path.exists(out_file) and os.path.getsize(out_file) > 0 else 0
                    if split_result.returncode != 0 or actual_dur <= 0:
                        self.mark_problem_unresolved(
                            part_retry_event_id,
                            "split_too_long_transcode_fallback",
                            source=src,
                            output=out_file,
                            part_num=part_num,
                            returncode=split_result.returncode,
                        )
                        self.write_problem(
                            "split_too_long_fallback_failed",
                            "Fallback-разбивка после слишком длинной copy-части не сработала.",
                            source=src,
                            output=out_file,
                            part_num=part_num,
                            returncode=split_result.returncode,
                            elapsed_seconds=getattr(split_result, "elapsed_seconds", None),
                            process_log_file=getattr(split_result, "process_log_file", ""),
                            stderr_tail=self.trim_text(split_result.stderr, 12000),
                            parent_event_id=part_retry_event_id,
                        )
                        self.last_split_validation["status"] = "failed_too_long_fallback"
                        return False

                if (
                    actual_dur
                    > max_duration_sec + self.SPLIT_MAX_OVERAGE_SECONDS
                ):
                    self.write_problem(
                        "split_part_still_too_long",
                        "После точного повтора часть всё ещё длиннее заданного интервала.",
                        source=src,
                        output=out_file,
                        split_mode=split_mode,
                        part_num=part_num,
                        requested_duration_seconds=part_duration,
                        expected_max_seconds=max_duration_sec,
                        actual_duration_seconds=actual_dur,
                        parent_event_id=part_retry_event_id,
                    )
                    if part_retry_event_id:
                        self.mark_problem_unresolved(
                            part_retry_event_id,
                            "split_part_limit_validation",
                            source=src,
                            output=out_file,
                            part_num=part_num,
                            actual_duration_seconds=actual_dur,
                        )
                    self.last_split_validation["status"] = "failed_part_too_long"
                    return False

                mismatch, difference, tolerance = self.duration_mismatch(part_duration, actual_dur)
                if not math.isfinite(actual_dur) or mismatch:
                    self.last_split_validation["status"] = "failed_part_duration_mismatch"
                    self.write_problem(
                        "split_part_duration_mismatch",
                        "Длительность части отличается от запрошенного участка исходного аудио.",
                        source=src, output=out_file, part_num=part_num,
                        expected_duration_seconds=part_duration,
                        actual_duration_seconds=actual_dur,
                        difference_seconds=difference, tolerance_seconds=tolerance,
                    )
                    if part_retry_event_id:
                        self.mark_problem_unresolved(
                            part_retry_event_id, "split_part_duration_validation",
                            source=src, output=out_file, part_num=part_num,
                        )
                    return False
                created_parts.append(out_file)
                created_part_durations.append(actual_dur)
                created_part_modes.append(split_mode)
                created_part_requested_durations.append(part_duration)
                if part_retry_event_id:
                    self.mark_problem_recovered(
                        part_retry_event_id,
                        "split_part_transcode_fallback",
                        source=src,
                        output=out_file,
                        part_num=part_num,
                        actual_duration_seconds=actual_dur,
                    )
                self.log_message(f"   ✅ Часть {part_num}: {self.format_duration(actual_dur)} ({split_mode})")
            else:
                self.log_message(f"   ❌ Часть {part_num} не создана или слишком маленькая", level="error")
                self.write_problem(
                    "split_part_output_missing",
                    "FFmpeg завершился без ошибки, но часть не создана или слишком маленькая.",
                    source=src,
                    output=out_file,
                    split_mode=split_mode,
                    part_num=part_num,
                    exists=os.path.exists(out_file),
                    size=os.path.getsize(out_file) if os.path.exists(out_file) else 0,
                    command=self.command_to_text(cmd),
                    command_argv=cmd,
                    elapsed_seconds=getattr(split_result, "elapsed_seconds", None),
                    process_log_file=getattr(split_result, "process_log_file", ""),
                    stderr_tail=self.trim_text(split_result.stderr, 12000),
                    stdout_tail=self.trim_text(split_result.stdout, 4000),
                )
                if part_retry_event_id:
                    self.mark_problem_unresolved(
                        part_retry_event_id,
                        "split_part_output_validation",
                        source=src,
                        output=out_file,
                        part_num=part_num,
                    )
                self.last_split_validation["status"] = "failed_output_missing"
                return False

            start_time += part_duration
            part_num += 1

            base_progress = (folder_index - 1) / total_folders * 100 + 35 / total_folders
            split_progress = (start_time / total_duration) * 60 / total_folders
            total_progress = min(99, base_progress + split_progress)
            self.update_progress(total_progress, f"{int(total_progress)}%")

        # CODEX-PHASE S3: verify that at least one part was produced.
        if not created_parts:
            self.write_problem(
                "split_no_parts_created",
                "Разбивка завершилась без созданных частей.",
                source=src,
                expected_parts=expected_parts,
            )
            self.last_split_validation["status"] = "failed_no_parts"
            return False

        # CODEX-PHASE S4: validate total duration across all generated parts.
        parts_total = sum(created_part_durations)
        maximum_part_duration = max(created_part_durations, default=0)
        strict_part_limit_valid = (
            maximum_part_duration
            <= max_duration_sec + self.SPLIT_MAX_OVERAGE_SECONDS
        )
        mismatch, difference, tolerance = self.duration_mismatch(total_duration, parts_total)
        if mismatch:
            parts_manifest = [
                {
                    "part_num": index,
                    "file": path,
                    "duration_seconds": duration,
                    "requested_duration_seconds": requested_duration,
                    "mode": mode,
                }
                for index, (path, duration, mode, requested_duration) in enumerate(
                    zip(
                        created_parts,
                        created_part_durations,
                        created_part_modes,
                        created_part_requested_durations,
                    ),
                    1,
                )
            ]
            self.last_split_validation.update({
                "status": "failed_total_duration_mismatch",
                "expected_part_count": expected_parts,
                "actual_part_count": len(created_parts),
                "actual_total_duration_seconds": parts_total,
                "difference_seconds": difference,
                "tolerance_seconds": tolerance,
                "maximum_part_duration_seconds": maximum_part_duration,
                "strict_part_limit_valid": strict_part_limit_valid,
                "parts": parts_manifest,
            })
            self.write_problem(
                "split_total_duration_mismatch",
                "Суммарная длительность частей заметно отличается от полного аудио.",
                source=src,
                expected_duration_seconds=total_duration,
                actual_parts_duration_seconds=parts_total,
                difference_seconds=difference,
                tolerance_seconds=tolerance,
                parts=parts_manifest,
                codex={
                    "impact": "Набор частей может содержать пропуск или лишний фрагмент.",
                    "likely_cause": "Некорректное позиционирование по временным меткам MP3.",
                    "codex_action": "Не считать папку успешной; сравнить длительности каждой части.",
                },
            )
            return False

        # CODEX-PHASE S5: publish successful split validation summary.
        self.last_split_validation.update({
            "status": "validated",
            "expected_part_count": expected_parts,
            "actual_part_count": len(created_parts),
            "actual_total_duration_seconds": parts_total,
            "difference_seconds": difference,
            "tolerance_seconds": tolerance,
            "maximum_part_duration_seconds": maximum_part_duration,
            "strict_part_limit_valid": strict_part_limit_valid,
            "parts": [
                {
                    "part_num": index,
                    "file": path,
                    "duration_seconds": duration,
                    "requested_duration_seconds": requested_duration,
                    "mode": mode,
                }
                for index, (path, duration, mode, requested_duration) in enumerate(
                    zip(
                        created_parts,
                        created_part_durations,
                        created_part_modes,
                        created_part_requested_durations,
                    ),
                    1,
                )
            ],
        })
        return True
