"""Subprocess lifecycle, cancellation, timeout and process log retention.

CODEX OWNER: edit this module when the requested change belongs to this responsibility.
Behavior was extracted from the original monolithic Videovaudio.py without intentional logic changes.
"""

import os
import traceback
import threading
import subprocess
import time
from datetime import datetime


class ProcessRunnerMixin:
    def compact_process_log(self, file_path):
        """Ограничивает сохранённый ошибочный вывод процесса без потери начала и хвоста."""
        try:
            if not file_path or not os.path.isfile(file_path):
                return
            size = os.path.getsize(file_path)
            if size <= self.MAX_PROCESS_LOG_BYTES:
                return

            head_size = min(12 * 1024, self.MAX_PROCESS_LOG_BYTES // 4)
            tail_size = self.MAX_PROCESS_LOG_BYTES - head_size
            with open(file_path, "rb") as source:
                head = source.read(head_size)
                source.seek(-tail_size, os.SEEK_END)
                tail = source.read(tail_size)

            marker = (
                f"\n\n... [середина лога удалена; исходный размер {size} байт] ...\n\n"
            ).encode("utf-8")
            temp_path = file_path + ".tmp"
            with open(temp_path, "wb") as target:
                target.write(head)
                target.write(marker)
                target.write(tail)
                target.flush()
                os.fsync(target.fileno())
            os.replace(temp_path, file_path)
        except Exception as e:
            try:
                self.logger.warning("Не удалось ограничить размер process-log: %s: %s", type(e).__name__, e)
            except Exception:
                pass

    def remove_success_process_log(self, file_path):
        """Успешный служебный вывод не хранится: полезные метрики уже есть в итоговом JSON."""
        try:
            if file_path and os.path.isfile(file_path):
                os.remove(file_path)
                return ""
        except Exception as e:
            try:
                self.logger.warning("Не удалось удалить успешный process-log: %s: %s", type(e).__name__, e)
            except Exception:
                pass
        return file_path

    def make_process_log_path(self, operation, file_path=None):
        """Создаёт отдельный файл под полный вывод конкретного процесса."""
        with self.process_lock:
            self.process_log_counter = getattr(self, "process_log_counter", 0) + 1
            number = self.process_log_counter

        base = os.path.basename(file_path) if file_path else ""
        name = self.safe_log_fragment(f"{operation}_{base}", fallback=operation or "process")
        return os.path.join(self.process_output_dir, f"{number:05d}_{name}.log")

    def completed_process(self, cmd, returncode, stdout, stderr, elapsed, process_log_file):
        """CompletedProcess с метаданными, нужными для диагностики Codex."""
        completed = subprocess.CompletedProcess(cmd, returncode, stdout, stderr)
        completed.elapsed_seconds = elapsed
        completed.process_log_file = process_log_file
        return completed

    def terminate_process(self, proc):
        """Мгновенно останавливает ffmpeg/ffprobe процесс и дочерние процессы."""
        if not proc or proc.poll() is not None:
            return

        try:
            if os.name == "nt":
                flags = subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0
                subprocess.run(
                    ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    creationflags=flags,
                    timeout=10
                )
            else:
                proc.terminate()
                try:
                    proc.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    proc.kill()
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass

    def terminate_active_processes(self):
        """Останавливает все текущие ffmpeg-процессы при нажатии отмены."""
        with self.process_lock:
            processes = list(self.active_processes)

        for proc in processes:
            self.terminate_process(proc)

    def request_cancel(self):
        """Обработчик кнопки отмены."""
        if self.cancel_requested:
            return
        self.cancel_requested = True
        self.log_message("⏹️ Отмена запрошена. Останавливаю текущие процессы ffmpeg...", level="warning")
        self.set_status("⏹️ Отмена: останавливаю ffmpeg...")
        self.terminate_active_processes()

    def run_process(
        self,
        cmd,
        c_flags=0,
        timeout=None,
        operation="",
        file_path=None,
        report_process_failure=True,
    ):
        """Запускает процесс без PIPE-зависаний; хранит полный вывод только при сбое."""
        self.ensure_windows_child_error_mode()
        proc = None
        started = time.time()
        next_fatal_output_check = started + 0.5
        process_log_file = self.make_process_log_path(operation or cmd[0], file_path)

        # CODEX-PHASE P1: finalize process output, retention and slow-process diagnostics.
        def finish(returncode, message=""):
            elapsed = time.time() - started
            try:
                captured_log_bytes = os.path.getsize(process_log_file)
            except OSError:
                captured_log_bytes = 0
            stderr_tail = self.read_text_tail(process_log_file)
            if message:
                stderr_tail = (stderr_tail + "\n" + message).strip()

            slow_process = (
                returncode == 0
                and elapsed > 900
                and not str(operation).startswith("ffprobe")
            )
            retained_log_file = process_log_file
            if returncode != 0 or slow_process:
                self.compact_process_log(process_log_file)
                stderr_tail = self.read_text_tail(process_log_file)
                if message:
                    stderr_tail = (stderr_tail + "\n" + message).strip()
            else:
                retained_log_file = self.remove_success_process_log(process_log_file)

            if slow_process:
                try:
                    retained_log_bytes = (
                        os.path.getsize(retained_log_file)
                        if retained_log_file and os.path.isfile(retained_log_file)
                        else 0
                    )
                except OSError:
                    retained_log_bytes = 0
                self.write_problem(
                    "slow_ffmpeg_process",
                    "FFmpeg-процесс занял больше 15 минут. Это не всегда ошибка, но важно для поиска причин медленной работы.",
                    severity="warning",
                    operation=operation,
                    file=file_path,
                    returncode=returncode,
                    elapsed_seconds=elapsed,
                    command=self.command_to_text(cmd),
                    command_argv=cmd,
                    process_log_file=retained_log_file,
                    captured_log_bytes_before_compaction=captured_log_bytes,
                    retained_log_bytes=retained_log_bytes,
                    output_tail=stderr_tail,
                )

            if (
                report_process_failure
                and returncode != 0
                and returncode not in (-999, -998)
            ):
                try:
                    self.logger.warning(
                        "PROCESS_FAILED operation=%s returncode=%s elapsed=%.2f file=%s details=%s",
                        operation,
                        self.normalize_returncode(returncode),
                        elapsed,
                        file_path,
                        retained_log_file,
                    )
                except Exception:
                    pass

            return self.completed_process(
                cmd,
                returncode,
                "",
                stderr_tail,
                elapsed,
                retained_log_file,
            )

        try:
            final_returncode = None
            final_message = ""
            # CODEX-PHASE P2: launch child process and register live process context.
            with open(process_log_file, "wb") as process_log:
                header = (
                    f"=== PROCESS START ===\n"
                    f"time={datetime.now().isoformat(timespec='seconds')}\n"
                    f"operation={operation}\n"
                    f"file={file_path}\n"
                    f"timeout_seconds={timeout}\n"
                    f"command={self.command_to_text(cmd)}\n\n"
                )
                process_log.write(header.encode("utf-8", errors="replace"))
                process_log.flush()

                proc = subprocess.Popen(
                    cmd,
                    stdin=subprocess.DEVNULL,
                    stdout=process_log,
                    stderr=subprocess.STDOUT,
                    creationflags=c_flags
                )

                with self.process_lock:
                    self.active_processes.add(proc)
                    self.process_contexts[proc.pid] = {
                        "pid": proc.pid,
                        "operation": operation,
                        "file": file_path,
                        "started_at": self.now_iso(),
                        "started_monotonic": time.monotonic(),
                        "process_log_file": process_log_file,
                        "command": self.command_to_text(cmd),
                    }
                self.update_active_state(
                    operation=operation,
                    file=file_path,
                    last_started_process_pid=proc.pid,
                )
                process_log.write(
                    (
                        f"process_pid={proc.pid}\n"
                        f"thread_name={threading.current_thread().name}\n\n"
                    ).encode("utf-8", errors="replace")
                )
                process_log.flush()

                # CODEX-PHASE P3: poll cancel/fatal-output/timeout/process-exit conditions.
                while True:
                    if self.cancel_requested:
                        self.terminate_process(proc)
                        try:
                            proc.wait(timeout=5)
                        except Exception:
                            pass
                        process_log.flush()
                        final_returncode = -999
                        final_message = "Процесс остановлен по отмене пользователя."
                        break

                    if proc.poll() is not None:
                        process_log.flush()
                        final_returncode = proc.returncode
                        break

                    current_time = time.time()
                    if (
                        str(operation).startswith("convert_single_file")
                        and current_time >= next_fatal_output_check
                    ):
                        process_log.flush()
                        output_tail = self.read_text_tail(
                            process_log_file,
                            limit_bytes=4096,
                        )
                        if self.is_libmp3lame_joint_stereo_assertion(
                            output_tail
                        ):
                            self.terminate_process(proc)
                            try:
                                proc.wait(timeout=5)
                            except Exception:
                                pass
                            process_log.flush()
                            final_returncode = proc.returncode
                            if final_returncode in (None, 0):
                                final_returncode = 3
                            final_message = (
                                "Обнаружен фатальный assertion libmp3lame; "
                                "процесс завершён досрочно для безопасного fallback."
                            )
                            break
                        next_fatal_output_check = current_time + 0.5

                    if timeout and (time.time() - started) > timeout:
                        self.terminate_process(proc)
                        try:
                            proc.wait(timeout=5)
                        except Exception:
                            pass
                        process_log.flush()
                        final_returncode = -998
                        final_message = "Процесс остановлен по таймауту."
                        break

                    time.sleep(0.2)

            process_elapsed = time.time() - started
            try:
                captured_output_bytes = os.path.getsize(process_log_file)
            except OSError:
                captured_output_bytes = 0
            with open(process_log_file, "ab") as process_log:
                footer = (
                    f"\n\n=== PROCESS END ===\n"
                    f"time={datetime.now().isoformat(timespec='seconds')}\n"
                    f"returncode={self.normalize_returncode(final_returncode)}\n"
                    f"elapsed_seconds={process_elapsed:.3f}\n"
                    f"captured_output_bytes={captured_output_bytes}\n"
                )
                process_log.write(footer.encode("utf-8", errors="replace"))
                process_log.flush()
                os.fsync(process_log.fileno())

            # CODEX-PHASE P4: persist footer, classify timeout and return CompletedProcess metadata.
            result = finish(final_returncode, final_message)
            if final_returncode == -998:
                self.write_problem(
                    "process_timeout",
                    f"Процесс превысил лимит времени: {operation or cmd[0]}",
                    operation=operation,
                    file=file_path,
                    timeout_seconds=timeout,
                    elapsed_seconds=result.elapsed_seconds,
                    command=self.command_to_text(cmd),
                    command_argv=cmd,
                    process_log_file=result.process_log_file,
                    stderr_tail=result.stderr,
                )
            return result

        except Exception as e:
            stderr = f"{type(e).__name__}: {e}"
            self.write_problem(
                "process_start_error",
                f"Не удалось запустить процесс: {operation or cmd[0]}",
                operation=operation,
                file=file_path,
                command=self.command_to_text(cmd),
                command_argv=cmd,
                process_log_file=process_log_file,
                exception=stderr,
                traceback=traceback.format_exc(),
            )
            return self.completed_process(cmd, -997, "", stderr, time.time() - started, process_log_file)

        finally:
            if proc:
                with self.process_lock:
                    self.active_processes.discard(proc)
                    self.process_contexts.pop(proc.pid, None)
                self.update_active_state(
                    last_finished_operation=operation,
                    last_finished_process_pid=proc.pid,
                )
