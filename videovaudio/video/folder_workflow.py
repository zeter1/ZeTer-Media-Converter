"""End-to-end workflow for one course folder in video-merge mode.

CODEX ROUTE: open this file only when the task matches this responsibility.
Methods are moved whole from the previous owner module; behavior is intentionally unchanged.
"""

import os
import traceback
import subprocess
import time
from collections import Counter
import shutil


class VideoFolderWorkflowMixin:
    def process_video_folder(self, folder_path, folder_index, total_folders):
        """Объединяет один курс в проверенные MP4-части до 10 часов."""
        started = time.perf_counter()
        folder_path = self.normalize_folder_path(folder_path)
        folder_name = os.path.basename(folder_path) or folder_path
        initial_event_ids = set(self.event_records)
        summary = {
            "folder": folder_path,
            "folder_name": folder_name,
            "operation": "video_merge",
            "status": "started",
            "outcome": "failed",
            "success": False,
            "input_files": 0,
            "converted_files": 0,
            "failed_files": 0,
            "skipped_files": 0,
            "skipped_no_audio_files": 0,
            "skipped_problem_files": 0,
            "problem_event_ids": [],
            "stage_metrics": {},
            "error": "",
            "skip_code": "",
            "skip_reason": "",
            "started_at": self.now_iso(),
        }

        def collect_events():
            summary["problem_event_ids"] = [
                event_id
                for event_id in self.event_records
                if event_id not in initial_event_ids
                and self.event_records[event_id].get("run_id")
                == getattr(self, "current_run_id", "")
            ]

        def finish(status, outcome="failed", success=False, error=""):
            summary.update({
                "status": status,
                "outcome": outcome,
                "success": success,
                "error": error,
                "finished_at": self.now_iso(),
            })
            summary["stage_metrics"]["folder_wall_seconds"] = (
                time.perf_counter() - started
            )
            collect_events()
            self.update_active_state(
                "folder_finished",
                folder=folder_path,
                folder_status=status,
            )
            return summary

        self.update_active_state(
            "video_folder_start",
            status="running",
            folder=folder_path,
            folder_index=folder_index,
            folder_total=total_folders,
            file=None,
        )
        self.ui_after(lambda: self.current_folder_label.config(
            text=(
                f"Текущая папка ({folder_index}/{total_folders}): "
                f"{folder_name}"
            )
        ))
        self.log_message(f"\n{'=' * 60}")
        self.log_message(
            f"🎬 ВИДЕО-КУРС {folder_index}/{total_folders}: {folder_name}"
        )
        self.log_message(f"{'=' * 60}")

        if not os.path.isdir(folder_path):
            message = f"Папка не существует или недоступна: {folder_path}"
            event_id = self.write_problem(
                "video_merge_folder_missing",
                message,
                folder=folder_path,
            )
            summary["problem_event_ids"] = [event_id]
            return finish("failed_folder_missing", error=message)

        scan_started = time.perf_counter()
        # CODEX-PHASE V1: scan and validate the course folder.
        scan_result = self.scan_media_files(folder_path, report_problems=True)
        summary["stage_metrics"]["scan_seconds"] = (
            time.perf_counter() - scan_started
        )
        files = scan_result["files"]
        summary["input_files"] = len(files)
        summary["scan"] = {
            "status": scan_result["status"],
            "error_count": len(scan_result["errors"]),
            "errors": scan_result["errors"][:20],
        }
        if scan_result["errors"]:
            message = (
                "Папка прочитана не полностью; объединение остановлено, "
                "чтобы не потерять часть уроков."
            )
            self.log_message(f"❌ {message}", level="error")
            return finish("failed_scan", error=message)
        if not files:
            message = f"В папке '{folder_name}' нет поддерживаемых видеофайлов"
            self.write_problem(
                "folder_skipped_no_media",
                message,
                severity="info",
                resolution_status="expected_skip",
                folder=folder_path,
                skip_code="no_supported_media",
            )
            summary["skip_code"] = "no_supported_media"
            summary["skip_reason"] = message
            self.log_message(f"ℹ️ {message}")
            return finish(
                "skipped_no_files",
                outcome="skipped",
                error="",
            )

        probe_started = time.perf_counter()
        # CODEX-PHASE V2: probe each input and build duration/profile items.
        items = []
        for index, file_path in enumerate(files, 1):
            if self.cancel_requested:
                return finish(
                    "cancelled",
                    outcome="cancelled",
                    error="Остановлено пользователем",
                )
            self.set_status(
                f"🔎 Проверка видео {index}/{len(files)} "
                f"(папка {folder_index}/{total_folders})..."
            )
            info = self.get_video_info(file_path)
            duration = float(info.get("duration_seconds") or 0)
            if not info.get("has_video") or duration <= 0:
                self.write_problem(
                    "video_merge_input_invalid",
                    "Исходное видео не удалось проверить; курс не объединён, чтобы не пропустить урок.",
                    file=file_path,
                    video_info=info,
                )
                summary["failed_files"] += 1
                message = (
                    f"Не удалось проверить видео: {os.path.basename(file_path)}"
                )
                self.log_message(f"❌ {message}", level="error")
                return finish("failed_input_validation", error=message)
            items.append({
                "index": index,
                "file": file_path,
                "duration_seconds": duration,
                "info": info,
            })
        summary["stage_metrics"]["probe_seconds"] = (
            time.perf_counter() - probe_started
        )
        summary["total_input_duration_seconds"] = sum(
            item["duration_seconds"] for item in items
        )
        # CODEX-PHASE V3: choose target profile and pack videos into <=10-hour groups.
        target = self.choose_video_target_profile(items)
        summary["target_profile"] = target
        groups = self.build_video_groups(items)
        summary["planned_groups"] = [
            {
                "kind": group["kind"],
                "input_count": len(group["items"]),
                "duration_seconds": sum(
                    item["duration_seconds"] for item in group["items"]
                ),
            }
            for group in groups
        ]

        temp_root = os.path.join(folder_path, self.VIDEO_TEMP_FOLDER)
        run_token = self.safe_log_fragment(
            getattr(self, "current_run_id", "run"),
            fallback="run",
            limit=80,
        )
        staging_dir = os.path.join(
            temp_root,
            f"{run_token}_{folder_index:03d}",
        )
        output_dir = os.path.join(folder_path, self.VIDEO_OUTPUT_FOLDER)
        staged_outputs = []
        try:
            os.makedirs(staging_dir, exist_ok=False)
            self.log_message(
                f"📚 Найдено видео: {len(items)}, "
                f"общая длительность: "
                f"{self.format_duration(summary['total_input_duration_seconds'])}"
            )
            self.log_message(
                f"📦 Планируется групп: {len(groups)}; "
                f"лимит каждой готовой части — {self.SPLIT_HOURS:g} ч"
            )
            merge_started = time.perf_counter()
            # CODEX-PHASE V4: build and validate each staged output group.
            for group_index, group in enumerate(groups, 1):
                if self.cancel_requested:
                    return finish(
                        "cancelled",
                        outcome="cancelled",
                        error="Остановлено пользователем",
                    )
                group_dir = os.path.join(
                    staging_dir,
                    f"group_{group_index:04d}",
                )
                os.makedirs(group_dir, exist_ok=True)
                self.update_active_state(
                    "video_merge_group",
                    folder=folder_path,
                    group_index=group_index,
                    group_total=len(groups),
                )
                self.set_status(
                    f"🎬 Объединение части {group_index}/{len(groups)} "
                    f"(папка {folder_index}/{total_folders})..."
                )
                if group["kind"] == "long":
                    result_parts = self.split_long_video_to_outputs(
                        group["items"][0],
                        group_dir,
                        target,
                        group_index,
                    )
                    if not result_parts:
                        if self.cancel_requested:
                            return finish(
                                "cancelled",
                                outcome="cancelled",
                                error="Остановлено пользователем",
                            )
                        return finish(
                            "failed_long_video_split",
                            error="Не удалось разбить видео длиннее 10 часов",
                        )
                    staged_outputs.extend(result_parts)
                else:
                    staged_path = os.path.join(
                        group_dir,
                        f"staged_{group_index:04d}.mp4",
                    )
                    group_result = self.create_video_group_output(
                        group["items"],
                        staged_path,
                        group_dir,
                        target,
                        group_index,
                    )
                    if not group_result:
                        if self.cancel_requested:
                            return finish(
                                "cancelled",
                                outcome="cancelled",
                                error="Остановлено пользователем",
                            )
                        return finish(
                            "failed_video_concat",
                            error=f"Не удалось создать часть {group_index}",
                        )
                    staged_outputs.append(group_result)
                progress = (
                    (folder_index - 1) / total_folders * 100
                    + (group_index / len(groups)) * 90 / total_folders
                )
                self.update_progress(min(99, progress), f"{int(progress)}%")
            summary["stage_metrics"]["merge_seconds"] = (
                time.perf_counter() - merge_started
            )

            publish_started = time.perf_counter()
            try:
                # CODEX-PHASE V5: atomically publish the complete validated output set.
                final_paths = self.publish_video_outputs(
                    staged_outputs,
                    output_dir,
                    staging_dir,
                )
            except Exception as error:
                self.write_problem(
                    "video_output_publish_failed",
                    "Не удалось заменить старый набор видео новым; выполнена попытка восстановления старых частей.",
                    folder=folder_path,
                    output_dir=output_dir,
                    exception=f"{type(error).__name__}: {error}",
                    traceback=traceback.format_exc(),
                )
                return finish(
                    "failed_publish",
                    error=f"Не удалось сохранить готовые части: {error}",
                )
            summary["stage_metrics"]["publish_seconds"] = (
                time.perf_counter() - publish_started
            )
            summary["converted_files"] = len(files)
            summary["output_dir"] = output_dir
            summary["output_files"] = [
                {
                    "file": final_path,
                    "mode": staged["mode"],
                    "input_count": staged["input_count"],
                    "duration_seconds": staged["validation"][
                        "actual_duration_seconds"
                    ],
                    "validation": staged["validation"],
                }
                for final_path, staged in zip(final_paths, staged_outputs)
            ]
            self.log_message(
                f"✅ Курс объединён: создано частей {len(final_paths)}"
            )
            self.log_message(f"📁 Результат: {output_dir}")
            return finish("success", outcome="success", success=True)
        except Exception as error:
            message = (
                "Непредвиденная ошибка объединения видео: "
                f"{type(error).__name__}: {error}"
            )
            self.write_problem(
                "video_folder_unhandled_exception",
                message,
                folder=folder_path,
                exception=f"{type(error).__name__}: {error}",
                traceback=traceback.format_exc(),
            )
            self.log_message(f"❌ {message}", level="error")
            return finish("failed_unhandled_exception", error=message)
        # CODEX-PHASE V6: cleanup staging directory and finalize folder state.
        finally:
            if os.path.isdir(staging_dir):
                try:
                    shutil.rmtree(staging_dir)
                except OSError as error:
                    self.write_problem(
                        "video_temp_cleanup_failed",
                        "Не удалось удалить временные файлы объединения видео.",
                        severity="warning",
                        folder=staging_dir,
                        exception=f"{type(error).__name__}: {error}",
                    )
            try:
                if os.path.isdir(temp_root) and not os.listdir(temp_root):
                    os.rmdir(temp_root)
            except OSError:
                pass
