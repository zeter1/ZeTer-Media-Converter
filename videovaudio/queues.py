"""Audio/video folder queues, validation and queue widgets state.

CODEX OWNER: edit this module when the requested change belongs to this responsibility.
Behavior was extracted from the original monolithic Videovaudio.py without intentional logic changes.
"""

import os
import tkinter as tk
from tkinter import filedialog, messagebox
from .dialogs import MultipleSelectionDialog


class QueueMixin:
    def guard_queue_edit(self):
        """Запрещает менять очередь во время фоновой обработки."""
        if self.is_running:
            messagebox.showwarning(
                "Обработка идёт",
                "Во время обработки очередь менять нельзя.",
            )
            return False
        return True

    def set_queue_controls_state(self, state):
        """Включить/выключить кнопки изменения очереди."""
        for button in getattr(self, "queue_control_buttons", []):
            button.config(state=state)

    def set_video_settings_state(self, enabled):
        """Блокирует настройки на время любой фоновой обработки."""
        state = "readonly" if enabled else "disabled"
        for widget in getattr(self, "video_setting_widgets", []):
            widget.config(state=state)

    def capture_video_settings(self):
        """Проверяет и фиксирует настройки до запуска рабочего потока."""
        resolution = self.video_resolution_var.get()
        video_bitrate = self.video_bitrate_var.get()
        audio_bitrate = self.video_audio_bitrate_var.get()
        if resolution not in self.VIDEO_RESOLUTIONS:
            raise ValueError(f"Неизвестное разрешение: {resolution}")
        if video_bitrate not in self.VIDEO_BITRATE_CHOICES:
            raise ValueError(f"Неизвестный битрейт видео: {video_bitrate}")
        if audio_bitrate not in self.VIDEO_AUDIO_BITRATE_CHOICES:
            raise ValueError(f"Неизвестный битрейт аудио: {audio_bitrate}")
        return {
            "resolution": resolution,
            "video_bitrate": video_bitrate,
            "audio_bitrate": audio_bitrate,
            "force_encode": True,
        }

    def get_folder_queue(self, queue_kind="audio"):
        """Возвращает независимую очередь выбранного режима."""
        if queue_kind == "video":
            return self.video_folder_queue
        return self.folder_queue

    def get_queue_widgets(self, queue_kind="audio"):
        """Возвращает список и информационную строку нужной вкладки."""
        if queue_kind == "video":
            return self.video_queue_listbox, self.video_queue_info
        return self.queue_listbox, self.queue_info

    def _add_folder_to_queue(self, queue_kind="audio"):
        if not self.guard_queue_edit():
            return

        title = (
            "Выберите папку курса с видео"
            if queue_kind == "video"
            else "Выберите папку с видео для добавления в очередь"
        )
        folder = filedialog.askdirectory(title=title)
        if folder:
            folder = self.normalize_folder_path(folder)

        target_queue = self.get_folder_queue(queue_kind)
        existing = {
            self.normalize_folder_key(item)
            for item in target_queue
        }
        if folder and self.normalize_folder_key(folder) in existing:
            messagebox.showinfo("Информация", "Эта папка уже есть в очереди!")
            return
        if not folder:
            return

        scan_result = self.scan_media_files(folder, report_problems=False)
        if scan_result["errors"]:
            messagebox.showerror(
                "Ошибка чтения",
                "Папка не добавлена: не удалось полностью прочитать её содержимое.",
            )
            return
        if not scan_result["files"]:
            messagebox.showinfo(
                "Нет видео",
                "Папка не добавлена: в ней нет поддерживаемых видеофайлов.",
            )
            self.log_message(
                f"ℹ️ Не добавлена папка без поддерживаемых видео: {folder}"
            )
            return

        target_queue.append(folder)
        self.update_queue_display(queue_kind)
        self.log_message(f"➕ Добавлена папка: {os.path.basename(folder)}")

    def add_folder_to_queue(self):
        """Добавить одну папку в очередь"""
        self._add_folder_to_queue("audio")

    def add_video_folder_to_queue(self):
        """Добавить папку курса в очередь объединения видео."""
        self._add_folder_to_queue("video")

    def add_multiple_folders(self):
        """Добавить несколько папок через кастомное окно выбора"""
        if not self.guard_queue_edit():
            return

        MultipleSelectionDialog(self.root, self, "audio")

    def add_multiple_video_folders(self):
        """Добавить несколько курсов в очередь объединения видео."""
        if not self.guard_queue_edit():
            return
        MultipleSelectionDialog(self.root, self, "video")

    def _remove_selected_from_queue(self, queue_kind="audio"):
        if not self.guard_queue_edit():
            return

        target_queue = self.get_folder_queue(queue_kind)
        listbox, _ = self.get_queue_widgets(queue_kind)
        selected_indices = listbox.curselection()
        if not selected_indices:
            messagebox.showinfo("Информация", "Выберите папки для удаления")
            return

        for index in reversed(selected_indices):
            folder = target_queue.pop(index)
            self.log_message(
                f"🗑️ Удалена из очереди: {os.path.basename(folder)}"
            )
        self.update_queue_display(queue_kind)

    def remove_selected_from_queue(self):
        """Удалить выбранные папки из очереди"""
        self._remove_selected_from_queue("audio")

    def remove_selected_from_video_queue(self):
        """Удалить выбранные курсы из видео-очереди."""
        self._remove_selected_from_queue("video")

    def _clear_queue(self, queue_kind="audio"):
        if not self.guard_queue_edit():
            return

        target_queue = self.get_folder_queue(queue_kind)
        if not target_queue:
            return

        if messagebox.askyesno(
            "Подтверждение",
            f"Удалить все {len(target_queue)} папок из очереди?",
        ):
            target_queue.clear()
            self.update_queue_display(queue_kind)
            self.log_message("🗑️ Очередь полностью очищена")

    def clear_queue(self):
        """Очистить всю очередь"""
        self._clear_queue("audio")

    def clear_video_queue(self):
        """Очистить очередь объединения видео."""
        self._clear_queue("video")

    def _remove_duplicates(self, queue_kind="audio"):
        if not self.guard_queue_edit():
            return

        target_queue = self.get_folder_queue(queue_kind)
        if not target_queue:
            messagebox.showinfo("Информация", "Очередь пуста!")
            return

        original_count = len(target_queue)
        seen = set()
        cleaned_queue = []
        duplicates = 0
        missing = 0
        for folder in target_queue:
            if not os.path.isdir(folder):
                missing += 1
                continue
            key = self.normalize_folder_key(folder)
            if key in seen:
                duplicates += 1
                continue
            seen.add(key)
            cleaned_queue.append(folder)

        removed = original_count - len(cleaned_queue)
        if removed == 0:
            messagebox.showinfo(
                "Информация",
                "Дубликаты и несуществующие папки не найдены!",
            )
            return

        target_queue[:] = cleaned_queue
        self.update_queue_display(queue_kind)
        msg = f"Очищено записей: {removed}\n"
        if duplicates > 0:
            msg += f"• Дубликаты: {duplicates}\n"
        if missing > 0:
            msg += f"• Несуществующие папки: {missing}"
        self.log_message(
            f"🧹 Очищено: {duplicates} дубликатов, "
            f"{missing} несуществующих папок"
        )
        messagebox.showinfo("Очистка завершена", msg)

    def remove_duplicates(self):
        """Удалить дубликаты и несуществующие папки из очереди"""
        self._remove_duplicates("audio")

    def remove_video_duplicates(self):
        """Очистить видео-очередь от дубликатов и пропавших папок."""
        self._remove_duplicates("video")

    def update_queue_display(self, queue_kind="audio"):
        """Обновить отображение очереди"""
        target_queue = self.get_folder_queue(queue_kind)
        listbox, info_label = self.get_queue_widgets(queue_kind)
        listbox.delete(0, tk.END)

        folder_counts = []
        for folder in target_queue:
            folder_counts.append((folder, len(self.get_files(folder))))

        for i, (folder, file_count) in enumerate(folder_counts, 1):
            display_text = f"{i}. {os.path.basename(folder)} ({file_count} файлов)"
            listbox.insert(tk.END, display_text)
        
        # Обновить информацию
        total_files = sum(file_count for _, file_count in folder_counts)
        if target_queue:
            info_label.config(
                text=f"В очереди: {len(target_queue)} папок, всего {total_files} файлов",
                foreground="green"
            )
        else:
            info_label.config(
                text="Очередь пуста (0 папок)",
                foreground="gray",
            )
