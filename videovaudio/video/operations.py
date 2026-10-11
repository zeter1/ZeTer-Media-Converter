"""Reusable video normalize/concat/split/group/publish operations.

CODEX ROUTE: open this file only when the task matches this responsibility.
Methods are moved whole from the previous owner module; behavior is intentionally unchanged.
"""

import os
import traceback
import subprocess
import time
from collections import Counter
import shutil


class VideoOperationsMixin:
    def concat_video_files_copy(self, files, output, temp_dir, operation):
        """Быстро склеивает уже совместимые MP4 без потери качества."""
        manifest = os.path.join(
            temp_dir,
            f"{self.safe_log_fragment(operation, fallback='concat')}.txt",
        )
        with open(manifest, "w", encoding="utf-8") as target:
            for file_path in files:
                target.write(
                    f"file '{self.escape_concat_path(file_path)}'\n"
                )
        cmd = [
            *self.ffmpeg_base_command(),
            "-nostdin", "-y",
            "-fflags", "+genpts",
            "-f", "concat", "-safe", "0", "-i", manifest,
            "-map", "0:v:0", "-map", "0:a:0?",
            "-c", "copy",
            "-avoid_negative_ts", "make_zero",
            "-movflags", "+faststart",
            output,
        ]
        c_flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        result = self.run_process(
            cmd,
            c_flags=c_flags,
            operation=operation,
            file_path=files[0] if files else None,
            report_process_failure=False,
        )
        return result, cmd, manifest

    def normalize_video_file(self, item, output, target, operation):
        """Нормализует один ролик и проверяет, что его содержимое не потеряно."""
        cmd = self.build_video_normalize_command(
            item["file"],
            output,
            item["info"],
            target,
        )
        c_flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        result = self.run_process(
            cmd,
            c_flags=c_flags,
            operation=operation,
            file_path=item["file"],
            report_process_failure=False,
        )
        if result.returncode == -999 or self.cancel_requested:
            return None
        validation = self.validate_merged_video(
            output,
            item["duration_seconds"],
            target=target,
        )
        if result.returncode != 0 or not validation["ok"]:
            self.write_problem(
                "video_normalization_failed",
                "Не удалось привести видео к единому формату H.264/AAC.",
                file=item["file"],
                output=output,
                returncode=result.returncode,
                command_argv=cmd,
                process_log_file=getattr(result, "process_log_file", ""),
                diagnostic_excerpt=result.stderr,
                validation=validation,
            )
            return None
        return {
            "file": output,
            "duration_seconds": validation["actual_duration_seconds"],
            "info": validation["info"],
        }

    def create_video_group_output(
        self,
        items,
        output,
        group_temp_dir,
        target,
        group_number,
    ):
        """Создаёт одну часть: copy при совместимости, иначе нормализация."""
        expected_duration = sum(
            float(item.get("duration_seconds") or 0)
            for item in items
        )
        max_duration = self.SPLIT_HOURS * 3600
        copy_retry_event_id = None

        if (
            not target.get("force_encode", True)
            and self.video_group_can_copy(items)
        ):
            self.log_message(
                f"   ⚡ Часть {group_number}: быстрая склейка без перекодирования"
            )
            result, cmd, _ = self.concat_video_files_copy(
                [item["file"] for item in items],
                output,
                group_temp_dir,
                f"video_concat_copy_{group_number}",
            )
            validation = self.validate_merged_video(
                output,
                expected_duration,
                max_duration,
            )
            if result.returncode == 0 and validation["ok"]:
                return {
                    "file": output,
                    "mode": "copy",
                    "input_count": len(items),
                    "expected_duration_seconds": expected_duration,
                    "validation": validation,
                }
            if result.returncode == -999 or self.cancel_requested:
                return None
            copy_retry_event_id = self.write_problem(
                "video_concat_copy_failed_retry_normalize",
                "Быстрая склейка видео не прошла проверку; выполняется надёжное перекодирование.",
                severity="warning",
                output=output,
                returncode=result.returncode,
                command_argv=cmd,
                process_log_file=getattr(result, "process_log_file", ""),
                diagnostic_excerpt=result.stderr,
                validation=validation,
            )
            try:
                if os.path.isfile(output):
                    os.remove(output)
            except OSError:
                pass

        self.log_message(
            f"   🎞️ Часть {group_number}: приведение файлов к единому H.264/AAC"
        )
        normalized_dir = os.path.join(group_temp_dir, "normalized")
        os.makedirs(normalized_dir, exist_ok=True)
        normalized = []
        for index, item in enumerate(items, 1):
            if self.cancel_requested:
                return None
            normalized_path = os.path.join(
                normalized_dir,
                f"normalized_{index:04d}.mp4",
            )
            normalized_item = self.normalize_video_file(
                item,
                normalized_path,
                target,
                f"video_normalize_{group_number}_{index}",
            )
            if not normalized_item:
                if copy_retry_event_id:
                    self.mark_problem_unresolved(
                        copy_retry_event_id,
                        "normalize_video_group",
                        output=output,
                    )
                return None
            normalized.append(normalized_item)

        result, cmd, _ = self.concat_video_files_copy(
            [item["file"] for item in normalized],
            output,
            group_temp_dir,
            f"video_concat_normalized_{group_number}",
        )
        validation = self.validate_merged_video(
            output,
            expected_duration,
            max_duration,
            target=target,
        )
        if result.returncode != 0 or not validation["ok"]:
            self.write_problem(
                "video_concat_normalized_failed",
                "Не удалось создать проверенную видео-часть после нормализации.",
                output=output,
                returncode=result.returncode,
                command_argv=cmd,
                process_log_file=getattr(result, "process_log_file", ""),
                diagnostic_excerpt=result.stderr,
                validation=validation,
                parent_event_id=copy_retry_event_id,
            )
            if copy_retry_event_id:
                self.mark_problem_unresolved(
                    copy_retry_event_id,
                    "concat_normalized_video_group",
                    output=output,
                )
            return None
        if copy_retry_event_id:
            self.mark_problem_recovered(
                copy_retry_event_id,
                "normalize_and_concat_video_group",
                output=output,
                validation=validation,
            )
        return {
            "file": output,
            "mode": "normalized",
            "input_count": len(items),
            "expected_duration_seconds": expected_duration,
            "validation": validation,
        }

    def split_long_video_to_outputs(
        self,
        item,
        group_temp_dir,
        target,
        group_number,
    ):
        """Перекодирует одиночное видео длиннее лимита сразу в части ≤10 часов."""
        max_duration = self.SPLIT_HOURS * 3600
        margin = min(2.0, max_duration * 0.02)
        segment_seconds = max(1.0, max_duration - margin)
        output_pattern = os.path.join(
            group_temp_dir,
            f"long_{group_number}_%03d.mp4",
        )
        cmd = self.build_video_normalize_command(
            item["file"],
            output_pattern,
            item["info"],
            target,
            segment_seconds=segment_seconds,
        )
        c_flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        result = self.run_process(
            cmd,
            c_flags=c_flags,
            operation=f"video_split_long_{group_number}",
            file_path=item["file"],
            report_process_failure=False,
        )
        if result.returncode == -999 or self.cancel_requested:
            return None
        prefix = f"long_{group_number}_"
        outputs = sorted(
            [
                os.path.join(group_temp_dir, name)
                for name in os.listdir(group_temp_dir)
                if name.startswith(prefix)
                and name.lower().endswith(".mp4")
            ],
            key=self.natural_sort_key,
        )
        validations = []
        for output in outputs:
            info = self.get_video_info(output)
            validation = self.validate_merged_video(
                output,
                info.get("duration_seconds") or 0,
                max_duration,
                target=target,
            )
            validations.append(validation)
        actual_total = sum(
            validation["actual_duration_seconds"]
            for validation in validations
        )
        mismatch, difference, tolerance = self.duration_mismatch(
            item["duration_seconds"],
            actual_total,
        )
        valid = (
            result.returncode == 0
            and outputs
            and all(validation["ok"] for validation in validations)
            and not mismatch
        )
        if not valid:
            self.write_problem(
                "video_long_split_failed",
                "Не удалось безопасно разбить длинное исходное видео на части до 10 часов.",
                file=item["file"],
                returncode=result.returncode,
                command_argv=cmd,
                process_log_file=getattr(result, "process_log_file", ""),
                diagnostic_excerpt=result.stderr,
                output_count=len(outputs),
                expected_duration_seconds=item["duration_seconds"],
                actual_duration_seconds=actual_total,
                difference_seconds=difference,
                tolerance_seconds=tolerance,
                validations=validations,
            )
            return None
        return [
            {
                "file": output,
                "mode": "normalized_long_split",
                "input_count": 1,
                "expected_duration_seconds": validation["actual_duration_seconds"],
                "validation": validation,
            }
            for output, validation in zip(outputs, validations)
        ]

    def build_video_groups(self, items):
        """Укладывает целые уроки в части до 10 часов без разреза между кадрами."""
        max_duration = self.SPLIT_HOURS * 3600
        groups = []
        current = []
        current_duration = 0.0
        for item in items:
            duration = float(item.get("duration_seconds") or 0)
            if duration > max_duration:
                if current:
                    groups.append({"kind": "concat", "items": current})
                    current = []
                    current_duration = 0.0
                groups.append({"kind": "long", "items": [item]})
                continue
            if current and current_duration + duration > max_duration:
                groups.append({"kind": "concat", "items": current})
                current = []
                current_duration = 0.0
            current.append(item)
            current_duration += duration
        if current:
            groups.append({"kind": "concat", "items": current})
        return groups

    def publish_video_outputs(self, staged_outputs, output_dir, staging_dir):
        """Публикует только проверенный полный набор с rollback старых частей."""
        os.makedirs(output_dir, exist_ok=True)
        backup_dir = os.path.join(staging_dir, "previous_outputs")
        os.makedirs(backup_dir, exist_ok=True)
        old_outputs = [
            os.path.join(output_dir, name)
            for name in os.listdir(output_dir)
            if self.VIDEO_OUTPUT_PATTERN.match(name)
            and os.path.isfile(os.path.join(output_dir, name))
        ]
        backed_up = []
        published = []
        try:
            for old_output in old_outputs:
                backup_path = os.path.join(
                    backup_dir,
                    os.path.basename(old_output),
                )
                self.atomic_replace_with_retry(old_output, backup_path)
                backed_up.append((backup_path, old_output))

            final_paths = []
            for index, staged in enumerate(staged_outputs, 1):
                final_path = os.path.join(
                    output_dir,
                    f"Часть {index:03d}.mp4",
                )
                self.atomic_replace_with_retry(staged["file"], final_path)
                published.append((final_path, staged["file"]))
                final_paths.append(final_path)
            shutil.rmtree(backup_dir)
            return final_paths
        except Exception:
            for final_path, staged_path in reversed(published):
                try:
                    if os.path.exists(final_path):
                        rollback_path = os.path.join(
                            staging_dir,
                            f"rollback_{os.path.basename(staged_path)}",
                        )
                        self.atomic_replace_with_retry(final_path, rollback_path)
                except OSError:
                    pass
            for backup_path, old_output in reversed(backed_up):
                try:
                    if os.path.exists(backup_path):
                        self.atomic_replace_with_retry(backup_path, old_output)
                except OSError:
                    pass
            raise
