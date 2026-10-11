"""Video queue run orchestration and start action.

CODEX ROUTE: open this file only when the task matches this responsibility.
Methods are moved whole from the previous owner module; behavior is intentionally unchanged.
"""

import os
import traceback
from tkinter import messagebox
import threading
import time
import uuid
from datetime import datetime
from shutil import which


class VideoRunMixin:
    def process_video_queue(self):
        """Фоновая обработка независимой очереди объединения видео."""
        queue_snapshot = list(self.video_folder_queue)
        total_folders = len(queue_snapshot)
        terminal_status = "running"
        self.current_run_id = (
            f"run-video-{datetime.now().strftime('%Y%m%d-%H%M%S')}-"
            f"{uuid.uuid4().hex[:8]}"
        )
        self.begin_run_diagnostics()
        self.log_message(f"🧠 Файл проблем для Codex: {self.problem_log_file}")
        with self.state_lock:
            self.active_state = {}
        initial_resources = self.reset_run_resource_metrics()
        self.start_heartbeat()
        self.update_active_state(
            "video_queue_start",
            status="running",
            operation="video_merge",
            video_settings=dict(self.active_video_settings),
            queue_total=total_folders,
            queue_snapshot=queue_snapshot[:50],
            folder=None,
            file=None,
            summary_file=self.summary_log_file,
            problem_file=self.problem_log_file,
            report_file=self.report_file,
            conversion_log_file=self.log_file,
            system_resources=initial_resources,
        )
        self.update_current_session({
            "status": "running",
            "operation": "video_merge",
            "video_settings": dict(self.active_video_settings),
            "queue_total_at_start": total_folders,
        })
        self.log_message(
            f"\n🎬 НАЧАЛО ОБЪЕДИНЕНИЯ ВИДЕО: {total_folders} папок"
        )
        started_at = self.now_iso()
        started = time.time()
        folder_results = []
        try:
            for index, folder_path in enumerate(queue_snapshot, 1):
                if self.cancel_requested:
                    break
                result = self.process_video_folder(
                    folder_path,
                    index,
                    total_folders,
                )
                folder_results.append(result)
                if result.get("outcome") == "cancelled":
                    self.cancel_requested = True
                    break

            success_results = [
                result for result in folder_results
                if result.get("outcome") == "success"
            ]
            skipped_results = [
                result for result in folder_results
                if result.get("outcome") == "skipped"
            ]
            failed_results = [
                result for result in folder_results
                if result.get("outcome") == "failed"
            ]
            cancelled = self.cancel_requested or any(
                result.get("outcome") == "cancelled"
                for result in folder_results
            )
            if cancelled:
                run_status = "cancelled"
            elif failed_results:
                run_status = "completed_with_errors"
            elif skipped_results:
                run_status = "completed_with_skips"
            else:
                run_status = "completed"
            elapsed = time.time() - started
            run_summary = {
                "operation": "video_merge",
                "video_settings": dict(self.active_video_settings),
                "status": run_status,
                "started_at": started_at,
                "finished_at": self.now_iso(),
                "elapsed_seconds": elapsed,
                "cancelled": cancelled,
                "queue_total_at_start": total_folders,
                "processed_count": len(folder_results),
                "success_count": len(success_results),
                "skipped_folder_count": len(skipped_results),
                "failed_count": len(failed_results),
                "skipped_media_count": 0,
                "skipped_no_audio_count": 0,
                "skipped_problem_count": 0,
                "log_file": self.log_file,
                "problem_log_file": self.problem_log_file,
                "summary_log_file": self.summary_log_file,
                "process_output_dir": self.process_output_dir,
                "folders": folder_results,
                "resource_metrics": self.run_resource_metrics_summary(),
            }
            self.last_run_summary = run_summary
            self.save_run_summary(run_summary)
            terminal_status = run_status

            hours, remainder = divmod(int(elapsed), 3600)
            minutes, seconds = divmod(remainder, 60)
            self.log_message(f"\n{'=' * 60}")
            self.log_message(
                "🎉 ОБЪЕДИНЕНИЕ ВИДЕО ЗАВЕРШЕНО"
                if not failed_results and not cancelled
                else "⚠️ ОБЪЕДИНЕНИЕ ВИДЕО ЗАВЕРШЕНО НЕ ПОЛНОСТЬЮ",
                level=(
                    "info"
                    if not failed_results and not cancelled
                    else "warning"
                ),
            )
            self.log_message(
                f"✅ Успешно: {len(success_results)} | "
                f"❌ Ошибок: {len(failed_results)} | "
                f"⏱️ {hours:02d}:{minutes:02d}:{seconds:02d}"
            )
            self.log_message(f"{'=' * 60}\n")

            completed_keys = {
                self.normalize_folder_key(result.get("folder"))
                for result in [*success_results, *skipped_results]
                if result.get("folder")
            }
            if not cancelled and completed_keys:
                self.video_folder_queue[:] = [
                    folder
                    for folder in self.video_folder_queue
                    if self.normalize_folder_key(folder) not in completed_keys
                ]
                self.ui_after(lambda: self.update_queue_display("video"))

            if cancelled:
                self.ui_after(lambda: messagebox.showwarning(
                    "Объединение остановлено",
                    "Обработка остановлена. Очередь сохранена, старые готовые части не удалялись.",
                ))
            elif failed_results:
                self.ui_after(lambda: messagebox.showwarning(
                    "Завершено с ошибками",
                    f"Успешно папок: {len(success_results)}\n"
                    f"С ошибками: {len(failed_results)}\n\n"
                    "Проблемные папки оставлены в очереди.\n\n"
                    f"Логи: {self.log_dir}",
                ))
            elif not success_results:
                self.ui_after(lambda: messagebox.showinfo(
                    "Объединение завершено",
                    f"Успешно папок: {len(success_results)}\n"
                    f"Пропущено пустых папок: {len(skipped_results)}\n\n"
                    "Готовые MP4 находятся внутри каждой папки курса в каталоге:\n"
                    f"{self.VIDEO_OUTPUT_FOLDER}",
                ))
        except Exception as error:
            message = (
                "Критическая ошибка видео-очереди: "
                f"{type(error).__name__}: {error}"
            )
            event_id = self.write_problem(
                "video_queue_unhandled_exception",
                message,
                severity="critical",
                exception=f"{type(error).__name__}: {error}",
                traceback=traceback.format_exc(),
            )
            self.last_run_summary = {
                "operation": "video_merge",
                "video_settings": dict(self.active_video_settings),
                "status": "crashed",
                "started_at": started_at,
                "finished_at": self.now_iso(),
                "elapsed_seconds": time.time() - started,
                "cancelled": self.cancel_requested,
                "queue_total_at_start": total_folders,
                "processed_count": len(folder_results),
                "success_count": sum(
                    result.get("outcome") == "success"
                    for result in folder_results
                ),
                "skipped_folder_count": sum(
                    result.get("outcome") == "skipped"
                    for result in folder_results
                ),
                "failed_count": (
                    sum(
                        result.get("outcome") == "failed"
                        for result in folder_results
                    )
                    + 1
                ),
                "skipped_media_count": 0,
                "problem_event_ids": [event_id],
                "folders": folder_results,
            }
            self.save_run_summary(self.last_run_summary)
            terminal_status = "crashed"
            self.log_message(f"💥 {message}", level="error")
        finally:
            self.finish_active_run(
                terminal_status,
                summary_file=self.summary_log_file,
                problem_file=self.problem_log_file,
            )
            try:
                self.update_current_session(self.last_run_summary)
            except Exception as error:
                self.logger.warning(
                    "CURRENT_SESSION_FINALIZE_FAILED %s: %s",
                    type(error).__name__,
                    error,
                )
            self.ui_after(self.done)

    def start_video_merge(self):
        """Запускает независимую очередь объединения видео."""
        if not self.video_folder_queue:
            messagebox.showwarning(
                "Внимание",
                "Добавьте папки с видео-курсами в очередь!",
            )
            return

        missing_tools = [
            tool for tool in ("ffmpeg", "ffprobe")
            if not which(tool)
        ]
        if missing_tools:
            message = (
                "Невозможно запустить: не найдены зависимости "
                + ", ".join(missing_tools)
            )
            self.log_message(f"❌ {message}", level="error")
            self.write_problem(
                "video_merge_start_blocked_missing_dependency",
                message,
                missing_tools=missing_tools,
                PATH=os.environ.get("PATH", ""),
            )
            messagebox.showwarning("Ошибка зависимости", message)
            return
        if self.is_running:
            return

        try:
            self.active_video_settings = self.capture_video_settings()
        except ValueError as error:
            messagebox.showerror("Ошибка настроек", str(error))
            return

        self.is_running = True
        self.active_job_kind = "video"
        self.cancel_requested = False
        self.last_run_summary = {}
        self.btn_start.config(state="disabled")
        self.btn_video_start.config(state="disabled")
        self.btn_cancel.config(state="normal")
        self.set_queue_controls_state("disabled")
        self.set_video_settings_state(False)
        self.prog.config(value=0)
        self.log.delete(1.0, "end")
        self.set_status("🎬 Запуск объединения видео...")
        self.log_message(f"🧾 Файл обычного лога: {self.log_file}")
        self.log_message(
            "🛡️ Старые готовые части сохраняются до полной проверки нового набора"
        )
        self.log_message(
            "⚙️ Настройки: "
            f"{self.active_video_settings['resolution']}, "
            f"видео {self.active_video_settings['video_bitrate']}, "
            f"аудио {self.active_video_settings['audio_bitrate']}"
        )
        threading.Thread(
            target=self.process_video_queue,
            daemon=True,
        ).start()
