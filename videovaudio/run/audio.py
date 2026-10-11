"""Audio queue run orchestration and start action.

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


class AudioRunMixin:
    def process_queue(self):
        """Обработка всей очереди папок по снимку очереди на момент старта."""
        if not self.folder_queue:
            self.ui_after(lambda: messagebox.showinfo("Информация", "Очередь пуста!"))
            return

        queue_snapshot = list(self.folder_queue)
        total_folders = len(queue_snapshot)
        terminal_status = "running"
        start_time = time.time()
        started_at = datetime.now().isoformat()
        folder_results = []
        terminal_notices = []

        try:
            self.current_run_id = (
                f"run-{datetime.now().strftime('%Y%m%d-%H%M%S')}-"
                f"{uuid.uuid4().hex[:8]}"
            )
            self.begin_run_diagnostics()
            self.log_message(
                f"🧠 Файл проблем для Codex: {self.problem_log_file}"
            )
            with self.state_lock:
                self.active_state = {}
            initial_resources = self.reset_run_resource_metrics()
            self.start_heartbeat()
            self.update_active_state(
                "queue_start",
                status="running",
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
                "queue_total_at_start": total_folders,
            })
            self.log_message(f"\n🎯 НАЧАЛО ОБРАБОТКИ ОЧЕРЕДИ: {total_folders} папок")
            self.log_message(f"💾 Результаты сохраняются в папки с исходными файлами")
            self.log_message(f"🧾 Подробные логи: {self.log_dir}\n")

            for index, folder_path in enumerate(queue_snapshot, 1):
                if self.cancel_requested:
                    self.log_message("\n⚠️ Обработка очереди отменена пользователем", level="warning")
                    break

                result = self.process_single_folder(folder_path, index, total_folders)
                folder_results.append(result)

                if result.get("status") == "cancelled" or self.cancel_requested:
                    self.cancel_requested = True
                    self.log_message("\n⚠️ Обработка очереди отменена пользователем", level="warning")
                    break

            elapsed_time = time.time() - start_time
            hours, remainder = divmod(int(elapsed_time), 3600)
            minutes, seconds = divmod(remainder, 60)

            success_results = [
                result
                for result in folder_results
                if result.get("outcome") == "success"
            ]
            skipped_folder_results = [
                result
                for result in folder_results
                if result.get("outcome") == "skipped"
            ]
            failed_results = [
                result
                for result in folder_results
                if result.get("outcome") == "failed"
            ]
            cancelled = self.cancel_requested or any(
                result.get("outcome") == "cancelled"
                for result in folder_results
            )
            skipped_media_count = sum(int(r.get("skipped_files", 0) or 0) for r in folder_results)
            skipped_no_audio_count = sum(
                int(r.get("skipped_no_audio_files", 0) or 0)
                for r in folder_results
            )
            skipped_problem_count = sum(
                int(r.get("skipped_problem_files", 0) or 0)
                for r in folder_results
            )
            if cancelled:
                run_status = "cancelled"
            elif failed_results:
                run_status = "completed_with_errors"
            elif skipped_media_count or skipped_folder_results:
                run_status = "completed_with_skips"
            else:
                run_status = "completed"

            run_summary = {
                "status": run_status,
                "started_at": started_at,
                "finished_at": self.now_iso(),
                "elapsed_seconds": elapsed_time,
                "cancelled": cancelled,
                "queue_total_at_start": total_folders,
                "processed_count": len(folder_results),
                "success_count": len(success_results),
                "skipped_folder_count": len(skipped_folder_results),
                "failed_count": len(failed_results),
                "skipped_media_count": skipped_media_count,
                "skipped_no_audio_count": skipped_no_audio_count,
                "skipped_problem_count": skipped_problem_count,
                "log_file": self.log_file,
                "problem_log_file": self.problem_log_file,
                "summary_log_file": self.summary_log_file,
                "process_output_dir": self.process_output_dir,
                "folders": folder_results,
            }
            run_summary["resource_metrics"] = (
                self.run_resource_metrics_summary()
            )
            self.last_run_summary = run_summary
            self.save_run_summary(run_summary)
            terminal_status = run_status

            self.log_message(f"\n{'='*60}")
            if cancelled:
                self.log_message("⚠️ ОБРАБОТКА ОТМЕНЕНА ПОЛЬЗОВАТЕЛЕМ", level="warning")
            elif failed_results:
                self.log_message("❌ ОЧЕРЕДЬ ЗАВЕРШЕНА С ОШИБКАМИ", level="error")
            else:
                self.log_message("🎉 ВСЯ ОЧЕРЕДЬ ОБРАБОТАНА УСПЕШНО!")
            self.log_message(f"⏱️  Общее время работы: {hours:02d}:{minutes:02d}:{seconds:02d}")
            self.log_message(f"✅ Успешно папок: {len(success_results)}")
            self.log_message(
                f"ℹ️ Папок без поддерживаемых видео пропущено: "
                f"{len(skipped_folder_results)}"
            )
            self.log_message(
                f"ℹ️ Видео без звука пропущено: {skipped_no_audio_count}"
            )
            self.log_message(
                (
                    f"⚠️ Других проблемных видео пропущено: {skipped_problem_count}"
                    if skipped_problem_count
                    else "ℹ️ Других проблемных видео пропущено: 0"
                ),
                level="warning" if skipped_problem_count else "info",
            )
            self.log_message(
                (
                    f"❌ Папок с ошибками: {len(failed_results)}"
                    if failed_results
                    else "✅ Папок с ошибками: 0"
                ),
                level="error" if failed_results else "info",
            )
            self.log_message(f"🧾 Лог проблем: {self.problem_log_file}")
            self.log_message(f"{'='*60}\n")

            if not cancelled and not failed_results:
                self.folder_queue.clear()
                self.log_message(
                    "🧹 Очередь очищена: папки обработаны или корректно пропущены"
                )
                self.ui_after(self.update_queue_display)
            elif not cancelled:
                completed_folder_keys = {
                    self.normalize_folder_key(result.get("folder"))
                    for result in [
                        *success_results,
                        *skipped_folder_results,
                    ]
                    if result.get("folder")
                }
                if completed_folder_keys:
                    self.folder_queue = [
                        folder
                        for folder in self.folder_queue
                        if self.normalize_folder_key(folder)
                        not in completed_folder_keys
                    ]
                    self.ui_after(self.update_queue_display)
                    self.log_message(
                        "🧹 Из очереди удалены обработанные и корректно "
                        "пропущенные папки. Оставлены только реальные ошибки."
                    )
                terminal_notices.append(lambda: messagebox.showwarning(
                    "Завершено с ошибками", 
                    f"Успешно папок: {len(success_results)}\n"
                    f"Корректно пропущено папок: {len(skipped_folder_results)}\n"
                    f"С ошибками: {len(failed_results)}\n\n"
                    f"Проблемные папки оставлены в очереди.\n\n"
                    f"Подробные логи:\n{self.log_dir}"
                ))
            else:
                self.log_message("ℹ️ Очередь не очищена, потому что обработка была отменена")
                terminal_notices.append(lambda: messagebox.showwarning(
                    "Отменено", 
                    f"Обработка остановлена.\n\n"
                    f"Очередь не очищена.\n\n"
                    f"Подробные логи:\n{self.log_dir}"
                ))

        except Exception as e:
            msg = f"Критическая ошибка обработки очереди: {type(e).__name__}: {e}"
            terminal_status = "crashed"
            self.last_run_summary = {
                "status": "crashed",
                "started_at": started_at,
                "finished_at": self.now_iso(),
                "elapsed_seconds": time.time() - start_time,
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
                "skipped_media_count": sum(
                    int(result.get("skipped_files", 0) or 0)
                    for result in folder_results
                ),
                "skipped_no_audio_count": sum(
                    int(
                        result.get("skipped_no_audio_files", 0)
                        or 0
                    )
                    for result in folder_results
                ),
                "skipped_problem_count": sum(
                    int(
                        result.get("skipped_problem_files", 0)
                        or 0
                    )
                    for result in folder_results
                ),
                "error": msg,
                "problem_event_ids": [],
                "log_file": self.log_file,
                "problem_log_file": self.problem_log_file,
                "summary_log_file": self.summary_log_file,
                "process_output_dir": self.process_output_dir,
                "folders": folder_results,
            }
            # Publish the failure in memory before diagnostic I/O can fail again.
            try:
                self.log_message(f"💥 {msg}", level="error")
                queue_event_id = self.write_problem(
                    "queue_unhandled_exception",
                    msg,
                    severity="critical",
                    exception=f"{type(e).__name__}: {e}",
                    traceback=traceback.format_exc(),
                )
                self.last_run_summary["problem_event_ids"] = [queue_event_id]
                self.last_run_summary["resource_metrics"] = self.run_resource_metrics_summary()
                self.save_run_summary(self.last_run_summary)
            except Exception as error:
                self.logger.warning("QUEUE_FAILURE_REPORT_FAILED %s: %s", type(error).__name__, error)
        finally:
            try:
                try:
                    self.finish_active_run(
                        terminal_status,
                        summary_file=self.summary_log_file,
                        problem_file=self.problem_log_file,
                    )
                except Exception as error:
                    terminal_status = "crashed"
                    self.last_run_summary.update(
                        status="crashed",
                        failed_count=max(1, self.last_run_summary.get("failed_count", 0)),
                        error=f"Завершение диагностики: {type(error).__name__}: {error}",
                    )
                    self.logger.warning("ACTIVE_RUN_FINALIZE_FAILED %s: %s", type(error).__name__, error)
                try:
                    self.update_current_session(
                        getattr(self, "last_run_summary", {}) or {"status": terminal_status}
                    )
                except Exception as error:
                    terminal_status = "crashed"
                    self.last_run_summary.update(
                        status="crashed",
                        failed_count=max(1, self.last_run_summary.get("failed_count", 0)),
                        error=f"Завершение сессии: {type(error).__name__}: {error}",
                    )
                    self.logger.warning("CURRENT_SESSION_FINALIZE_FAILED %s: %s", type(error).__name__, error)
                if terminal_status != "crashed":
                    for notice in terminal_notices:
                        self.ui_after(notice)
            finally:
                self.ui_after(self.done)

    def start(self):
        if not self.folder_queue:
            messagebox.showwarning("Внимание", "Добавьте папки в очередь!")
            return

        missing_tools = [tool for tool in ("ffmpeg", "ffprobe") if not which(tool)]
        if missing_tools:
            msg = "Невозможно запустить: не найдены зависимости " + ", ".join(missing_tools)
            self.log_message(f"❌ {msg}", level="error")
            self.write_problem(
                "start_blocked_missing_dependency",
                msg,
                missing_tools=missing_tools,
                PATH=os.environ.get("PATH", ""),
            )
            messagebox.showwarning("Ошибка зависимости", msg)
            return

        if self.is_running:
            return

        self.is_running = True
        self.active_job_kind = "audio"
        self.cancel_requested = False
        self.last_run_summary = {}
        self.btn_start.config(state="disabled")
        self.btn_video_start.config(state="disabled")
        self.btn_cancel.config(state="normal")
        self.set_queue_controls_state("disabled")
        self.set_video_settings_state(False)
        self.prog.config(value=0)
        self.log.delete(1.0, "end")
        self.set_status("🚀 Запуск обработки очереди...")
        self.log_message(f"🧾 Файл обычного лога: {self.log_file}")
        self.log_message(
            f"📂 Вывод FFmpeg сохраняется только при ошибках и процессах дольше 15 минут: "
            f"{self.process_output_dir}"
        )

        threading.Thread(target=self.process_queue, daemon=True).start()
