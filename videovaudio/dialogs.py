"""Custom Tkinter dialogs.

CODEX OWNER: multi-folder selection dialog only.
"""

import os
import tkinter as tk
from tkinter import ttk, filedialog, messagebox


class MultipleSelectionDialog:
    """Диалог для множественного выбора папок"""
    def __init__(self, parent, converter, queue_kind="audio"):
        self.converter = converter
        self.queue_kind = queue_kind
        self.selected_folders = []
        
        self.dialog = tk.Toplevel(parent)
        self.dialog.title("Выбор нескольких папок")
        self.dialog.geometry("800x600")
        self.dialog.transient(parent)
        self.dialog.grab_set()
        
        # Основной фрейм
        main_frame = ttk.Frame(self.dialog, padding="10")
        main_frame.pack(fill="both", expand=True)
        
        # Заголовок
        ttk.Label(main_frame, text="Выберите папки для добавления в очередь", 
                 font=("Segoe UI", 12, "bold")).pack(pady=(0, 10))
        
        # Фрейм с деревом и скроллбаром
        tree_frame = ttk.Frame(main_frame)
        tree_frame.pack(fill="both", expand=True)
        
        # Скроллбары
        vsb = ttk.Scrollbar(tree_frame, orient="vertical")
        hsb = ttk.Scrollbar(tree_frame, orient="horizontal")
        
        # Дерево папок
        self.tree = ttk.Treeview(tree_frame, selectmode="extended",
                                yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        vsb.config(command=self.tree.yview)
        hsb.config(command=self.tree.xview)
        
        # Размещение
        self.tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")
        
        tree_frame.columnconfigure(0, weight=1)
        tree_frame.rowconfigure(0, weight=1)
        
        # Настройка колонок
        self.tree["columns"] = ("files",)
        self.tree.column("#0", width=600, minwidth=200)
        self.tree.column("files", width=50, minwidth=30)
        self.tree.heading("#0", text="Путь к папке")
        self.tree.heading("files", text="")
        
        # Кнопки выбора базовой папки
        nav_frame = ttk.Frame(main_frame)
        nav_frame.pack(fill="x", pady=10)
        
        self.current_path = tk.StringVar()
        ttk.Label(nav_frame, text="Текущая папка:").pack(side="left", padx=5)
        ttk.Entry(nav_frame, textvariable=self.current_path, state="readonly").pack(side="left", fill="x", expand=True, padx=5)
        ttk.Button(nav_frame, text="Обзор...", command=self.browse_folder).pack(side="left", padx=5)
        
        # Информация о выборе
        self.selection_info = tk.StringVar(value="Выбрано: 0 папок")
        ttk.Label(main_frame, textvariable=self.selection_info, 
                 font=("Segoe UI", 10)).pack(pady=5)
        
        # Кнопки действий
        btn_frame = ttk.Frame(main_frame)
        btn_frame.pack(pady=10)
        
        ttk.Button(btn_frame, text="✓ Добавить выбранные", 
                  command=self.add_selected, width=20).pack(side="left", padx=5)
        ttk.Button(btn_frame, text="Выбрать все", 
                  command=self.select_all, width=15).pack(side="left", padx=5)
        ttk.Button(btn_frame, text="Снять выбор", 
                  command=self.deselect_all, width=15).pack(side="left", padx=5)
        ttk.Button(btn_frame, text="Отмена", 
                  command=self.dialog.destroy, width=15).pack(side="left", padx=5)
        
        # Привязка событий
        self.tree.bind("<<TreeviewSelect>>", self.on_selection_changed)
        
        # Загрузка домашней папки по умолчанию
        home_dir = os.path.expanduser("~")
        self.load_folders(home_dir)
        
    def browse_folder(self):
        """Выбор базовой папки для просмотра"""
        folder = filedialog.askdirectory(title="Выберите папку для просмотра")
        if folder:
            self.load_folders(folder)
    
    def load_folders(self, root_path):
        """Загрузка папок из выбранного пути"""
        self.tree.delete(*self.tree.get_children())
        self.current_path.set(root_path)
        
        try:
            # Получаем список всех папок
            items = []
            for item in os.listdir(root_path):
                item_path = os.path.join(root_path, item)
                if os.path.isdir(item_path):
                    items.append((item, item_path, "?"))
            
            # Сортируем по имени
            items.sort(key=lambda x: x[0].lower())
            
            # Добавляем в дерево
            for name, path, count in items:
                self.tree.insert("", "end", text=path, values=(count,), tags=(path,))
                
        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось загрузить папки: {e}")
    
    def on_selection_changed(self, event):
        """Обновление информации о выборе"""
        selected = self.tree.selection()
        self.selection_info.set(f"Выбрано: {len(selected)} папок")
    
    def select_all(self):
        """Выбрать все папки"""
        items = self.tree.get_children()
        self.tree.selection_set(items)
    
    def deselect_all(self):
        """Снять выбор со всех папок"""
        self.tree.selection_remove(self.tree.selection())
    
    def add_selected(self):
        """Добавить выбранные папки в очередь"""
        if self.converter.is_running:
            messagebox.showwarning("Конвертация идёт", "Во время конвертации очередь менять нельзя.")
            return

        selected_items = self.tree.selection()
        
        if not selected_items:
            messagebox.showinfo("Информация", "Выберите хотя бы одну папку!")
            return
        
        added_count = 0
        duplicate_count = 0
        empty_count = 0
        unreadable_count = 0
        target_queue = self.converter.get_folder_queue(self.queue_kind)
        existing = {
            self.converter.normalize_folder_key(path)
            for path in target_queue
        }
        
        for item in selected_items:
            folder_path = self.converter.normalize_folder_path(
                self.tree.item(item)["text"]
            )
            folder_key = self.converter.normalize_folder_key(folder_path)
            if folder_key in existing:
                duplicate_count += 1
                continue

            scan_result = self.converter.scan_media_files(
                folder_path,
                report_problems=False,
            )
            if scan_result["errors"]:
                unreadable_count += 1
                self.converter.log_message(
                    f"⚠️ Не добавлена недоступная папка: {folder_path}",
                    level="warning",
                )
                continue
            if not scan_result["files"]:
                empty_count += 1
                self.converter.log_message(
                    f"ℹ️ Не добавлена папка без поддерживаемых видео: {folder_path}"
                )
                continue

            target_queue.append(folder_path)
            existing.add(folder_key)
            self.converter.log_message(
                f"➕ Добавлена: {os.path.basename(folder_path)}"
            )
            added_count += 1
        
        if added_count > 0:
            self.converter.update_queue_display(self.queue_kind)
            msg = f"Добавлено {added_count} папок в очередь!"
            if duplicate_count:
                msg += f"\nУже были в очереди: {duplicate_count}"
            if empty_count:
                msg += f"\nБез поддерживаемых видео: {empty_count}"
            if unreadable_count:
                msg += f"\nНедоступны для чтения: {unreadable_count}"
            messagebox.showinfo("Успех", msg)
        else:
            details = []
            if duplicate_count:
                details.append(f"уже в очереди: {duplicate_count}")
            if empty_count:
                details.append(f"без поддерживаемых видео: {empty_count}")
            if unreadable_count:
                details.append(f"недоступны для чтения: {unreadable_count}")
            suffix = f"\n\n{'; '.join(details)}" if details else ""
            messagebox.showinfo(
                "Информация",
                f"Ни одна папка не добавлена.{suffix}",
            )
        
        self.dialog.destroy()
