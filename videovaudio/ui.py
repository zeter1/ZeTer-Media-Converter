"""Tkinter interface construction and UI-thread helper methods.

CODEX OWNER: edit this module when the requested change belongs to this responsibility.
Behavior was extracted from the original monolithic Videovaudio.py without intentional logic changes.
"""

import tkinter as tk
from tkinter import ttk
from datetime import datetime
from .notifications import CompletionNotification


class UIMixin:
    def show_completion_notification(self, files):
        """Показать постоянное уведомление; вызывается из UI-потока."""
        if not hasattr(self, 'completion_notification'):
            self.completion_notification = CompletionNotification(self.root)
        self.completion_notification.show(files)

    def create_interface(self):
        main = ttk.Frame(self.root, padding="15 15 15 10")
        main.pack(fill="both", expand=True)
        ttk.Label(
            main,
            text=self.APP_NAME,
            font=("Segoe UI", 18, "bold"),
        ).pack(pady=(0, 10))

        self.mode_notebook = ttk.Notebook(main)
        self.mode_notebook.pack(fill="both", expand=True, pady=(0, 8))

        audio_tab = ttk.Frame(self.mode_notebook, padding=10)
        video_tab = ttk.Frame(self.mode_notebook, padding=10)
        self.mode_notebook.add(audio_tab, text="Все видео в аудио по 10 часов и аудио для каждого видео.")
        self.mode_notebook.add(
            video_tab,
            text="Объединение всех видео по 10 часов",
        )

        self.queue_control_buttons = []

        # Старая очередь конвертации видео в MP3.
        queue_frame = ttk.LabelFrame(
            audio_tab,
            text="Очередь папок для конвертации в аудио",
        )
        queue_frame.pack(fill="both", expand=True, pady=(0, 8))
        queue_buttons = ttk.Frame(queue_frame)
        queue_buttons.pack(fill="x", padx=5, pady=5)

        self.btn_add_folder = ttk.Button(queue_buttons, text="➕ Добавить папку", command=self.add_folder_to_queue)
        self.btn_add_folder.pack(side="left", padx=5)
        self.queue_control_buttons.append(self.btn_add_folder)

        self.btn_add_multiple = ttk.Button(queue_buttons, text="📂 Выбрать несколько", command=self.add_multiple_folders)
        self.btn_add_multiple.pack(side="left", padx=5)
        self.queue_control_buttons.append(self.btn_add_multiple)

        self.btn_remove_queue = ttk.Button(queue_buttons, text="🗑️ Удалить", command=self.remove_selected_from_queue)
        self.btn_remove_queue.pack(side="left", padx=5)
        self.queue_control_buttons.append(self.btn_remove_queue)

        self.btn_remove_duplicates = ttk.Button(queue_buttons, text="🧹 Очистить дубликаты", command=self.remove_duplicates)
        self.btn_remove_duplicates.pack(side="left", padx=5)
        self.queue_control_buttons.append(self.btn_remove_duplicates)

        self.btn_clear_queue = ttk.Button(queue_buttons, text="🗑️ Очистить всё", command=self.clear_queue)
        self.btn_clear_queue.pack(side="left", padx=5)
        self.queue_control_buttons.append(self.btn_clear_queue)
        
        # Список папок в очереди
        list_frame = ttk.Frame(queue_frame)
        list_frame.pack(fill="both", expand=True, padx=5, pady=5)
        
        scrollbar = ttk.Scrollbar(list_frame)
        scrollbar.pack(side="right", fill="y")
        
        self.queue_listbox = tk.Listbox(list_frame, yscrollcommand=scrollbar.set, height=8, font=("Segoe UI", 10))
        self.queue_listbox.pack(side="left", fill="both", expand=True)
        scrollbar.config(command=self.queue_listbox.yview)
        
        # Информация об очереди
        self.queue_info = ttk.Label(queue_frame, text="Очередь пуста (0 папок)", foreground="gray", font=("Segoe UI", 10))
        self.queue_info.pack(pady=5)

        info_frame = ttk.LabelFrame(audio_tab, text="ℹ️ Информация")
        info_frame.pack(fill="x", pady=(0, 8))
        info_text = (
            "MP3 сохраняются рядом с исходной папкой: отдельно для каждого "
            "видео и общими частями до 10 часов"
        )
        info_label = ttk.Label(info_frame, text=info_text, foreground="blue", font=("Segoe UI", 9))
        info_label.pack(padx=10, pady=8)

        audio_buttons = ttk.Frame(audio_tab)
        audio_buttons.pack(pady=(0, 4))
        self.btn_start = ttk.Button(
            audio_buttons,
            text="🚀 Запустить конвертацию в аудио",
            command=self.start,
        )
        self.btn_start.pack(side="left", padx=8)

        # Независимая очередь объединения исходных видео.
        video_queue_frame = ttk.LabelFrame(
            video_tab,
            text="Очередь папок с видео-курсами",
        )
        video_queue_frame.pack(fill="both", expand=True, pady=(0, 8))
        video_queue_buttons = ttk.Frame(video_queue_frame)
        video_queue_buttons.pack(fill="x", padx=5, pady=5)

        video_button_specs = (
            ("➕ Добавить папку", self.add_video_folder_to_queue),
            ("📂 Выбрать несколько", self.add_multiple_video_folders),
            ("🗑️ Удалить", self.remove_selected_from_video_queue),
            ("🧹 Очистить дубликаты", self.remove_video_duplicates),
            ("🗑️ Очистить всё", self.clear_video_queue),
        )
        for text, command in video_button_specs:
            button = ttk.Button(
                video_queue_buttons,
                text=text,
                command=command,
            )
            button.pack(side="left", padx=5)
            self.queue_control_buttons.append(button)

        video_list_frame = ttk.Frame(video_queue_frame)
        video_list_frame.pack(fill="both", expand=True, padx=5, pady=5)
        video_scrollbar = ttk.Scrollbar(video_list_frame)
        video_scrollbar.pack(side="right", fill="y")
        self.video_queue_listbox = tk.Listbox(
            video_list_frame,
            yscrollcommand=video_scrollbar.set,
            height=8,
            font=("Segoe UI", 10),
        )
        self.video_queue_listbox.pack(side="left", fill="both", expand=True)
        video_scrollbar.config(command=self.video_queue_listbox.yview)
        self.video_queue_info = ttk.Label(
            video_queue_frame,
            text="Очередь пуста (0 папок)",
            foreground="gray",
            font=("Segoe UI", 10),
        )
        self.video_queue_info.pack(pady=5)

        video_settings_frame = ttk.LabelFrame(
            video_tab,
            text="⚙️ Настройки готового видео",
        )
        video_settings_frame.pack(fill="x", pady=(0, 8))
        self.video_resolution_var = tk.StringVar(
            value=self.DEFAULT_VIDEO_RESOLUTION
        )
        self.video_bitrate_var = tk.StringVar(
            value=self.DEFAULT_VIDEO_BITRATE
        )
        self.video_audio_bitrate_var = tk.StringVar(
            value=self.DEFAULT_VIDEO_AUDIO_BITRATE
        )
        self.video_setting_widgets = []

        setting_specs = (
            (
                "Разрешение:",
                self.video_resolution_var,
                tuple(self.VIDEO_RESOLUTIONS),
                10,
            ),
            (
                "Битрейт видео:",
                self.video_bitrate_var,
                self.VIDEO_BITRATE_CHOICES,
                11,
            ),
            (
                "Битрейт аудио:",
                self.video_audio_bitrate_var,
                self.VIDEO_AUDIO_BITRATE_CHOICES,
                11,
            ),
        )
        for label_text, variable, values, width in setting_specs:
            setting = ttk.Frame(video_settings_frame)
            setting.pack(side="left", padx=12, pady=8)
            ttk.Label(setting, text=label_text).pack(side="left", padx=(0, 5))
            selector = ttk.Combobox(
                setting,
                textvariable=variable,
                values=values,
                width=width,
                state="readonly",
            )
            selector.pack(side="left")
            self.video_setting_widgets.append(selector)

        ttk.Label(
            video_settings_frame,
            text="Рекомендуется: 720p, 2500k видео, 160k аудио",
            foreground="gray",
            font=("Segoe UI", 9),
        ).pack(side="left", padx=12, pady=8)

        video_info_frame = ttk.LabelFrame(video_tab, text="ℹ️ Как работает")
        video_info_frame.pack(fill="x", pady=(0, 8))
        ttk.Label(
            video_info_frame,
            text=(
                "Видео идут в естественном порядке 1, 2, 10. Программа "
                "создаёт MP4-части длительностью не более 10 часов и "
                "сохраняет их внутри выбранной папки курса. Выбранные "
                "разрешение и битрейты применяются с перекодированием."
            ),
            foreground="blue",
            font=("Segoe UI", 9),
            wraplength=930,
            justify="left",
        ).pack(padx=10, pady=8, anchor="w")

        video_buttons = ttk.Frame(video_tab)
        video_buttons.pack(pady=(0, 4))
        self.btn_video_start = ttk.Button(
            video_buttons,
            text="🎬 Объединить видео по 10 часов",
            command=self.start_video_merge,
        )
        self.btn_video_start.pack(side="left", padx=8)

        # Текущая обрабатываемая папка
        self.current_folder_label = ttk.Label(main, text="Текущая папка: нет", foreground="blue", font=("Segoe UI", 10, "bold"))
        self.current_folder_label.pack(pady=(5, 8))

        # Лог операций
        logf = ttk.LabelFrame(main, text="Лог операций")
        logf.pack(fill="both", expand=True, pady=(0, 10))
        
        log_container = ttk.Frame(logf)
        log_container.pack(fill="both", expand=True, padx=5, pady=5)
        
        self.log = tk.Text(log_container, height=8, font=("Consolas", 9))
        sb = ttk.Scrollbar(log_container, command=self.log.yview)
        self.log.configure(yscrollcommand=sb.set)
        self.log.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")

        # Общая отмена для обоих режимов.
        btns = ttk.Frame(main)
        btns.pack(pady=(6, 2))
        self.btn_cancel = ttk.Button(btns, text="⏹️ Отмена", command=self.request_cancel, state="disabled")
        self.btn_cancel.pack(side="left", padx=8)

        # Прогресс-бар
        self.prog = ttk.Progressbar(main, maximum=100)
        self.prog.pack(fill="x", pady=10, padx=20)
        self.prog_label = tk.Label(main, text="0%", font=("Segoe UI", 11, "bold"), bg="#f0f0f0", relief="solid", width=6)
        self.prog_label.place(in_=self.prog, relx=0.5, rely=0.5, anchor="center")

        # Статус
        self.status = tk.StringVar(value="Готов к работе")
        ttk.Label(main, textvariable=self.status, relief="sunken", anchor="w", padding=8).pack(fill="x")

    def ui_after(self, callback):
        """Безопасно планирует действие в Tkinter, даже если окно уже закрывается."""
        try:
            if hasattr(self, "root") and self.root:
                self.root.after(0, callback)
        except Exception as e:
            try:
                logger = getattr(self, "logger", None)
                if logger:
                    logger.warning("UI_AFTER_FAILED %s: %s", type(e).__name__, e)
            except Exception:
                pass

    def log_message(self, msg, level="info", persist=True):
        """Пишет сообщение в окно; повторяющиеся успехи можно не сохранять в файл."""
        t = datetime.now().strftime("%H:%M:%S")

        if persist:
            try:
                logger = getattr(self, "logger", None)
                if logger:
                    log_func = getattr(logger, level, logger.info)
                    log_func(str(msg))
            except Exception:
                pass

        if hasattr(self, "log"):
            self.ui_after(lambda: self.log.insert("end", f"[{t}] {msg}\n") or self.log.see("end"))

    def set_status(self, msg):
        self.ui_after(lambda: self.status.set(msg))

    def update_progress(self, val, text):
        self.ui_after(lambda: (self.prog.config(value=val), self.prog_label.config(text=text)))
