"""Persistent completion window and Windows Explorer navigation (Tk thread only)."""
import ctypes
from ctypes import wintypes
import os
from pathlib import Path
import subprocess
import tkinter as tk
from tkinter import ttk


def reveal_file(filename):
    """Open Explorer with the exact published file selected, without a shell."""
    path = Path(filename).resolve()
    if not path.is_file():
        raise FileNotFoundError(f"Файл больше не существует: {path}")
    explorer = os.path.join(os.environ.get('SystemRoot', r'C:\Windows'), 'explorer.exe')
    subprocess.Popen([explorer, '/select,', str(path)],
                     creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))


def work_area(root):
    """Work area of the app's monitor, excluding Windows taskbars."""
    if os.name == 'nt':
        class MonitorInfo(ctypes.Structure):
            _fields_ = [('cbSize', wintypes.DWORD), ('rcMonitor', wintypes.RECT),
                        ('rcWork', wintypes.RECT), ('dwFlags', wintypes.DWORD)]

        user32 = ctypes.WinDLL('user32', use_last_error=True)
        user32.MonitorFromWindow.argtypes = [wintypes.HWND, wintypes.DWORD]
        user32.MonitorFromWindow.restype = wintypes.HANDLE
        user32.GetMonitorInfoW.argtypes = [wintypes.HANDLE, ctypes.POINTER(MonitorInfo)]
        user32.GetMonitorInfoW.restype = wintypes.BOOL
        monitor = user32.MonitorFromWindow(root.winfo_id(), 2)
        info = MonitorInfo()
        info.cbSize = ctypes.sizeof(info)
        if user32.GetMonitorInfoW(monitor, ctypes.byref(info)):
            rect = info.rcWork
            return rect.left, rect.top, rect.right, rect.bottom
    return 0, 0, root.winfo_screenwidth(), root.winfo_screenheight()


class CompletionNotification:
    """One scrollable window retains all results until its cross is clicked."""
    def __init__(self, root):
        self.root = root
        self.window = None

    def show(self, files):
        if not files:
            return
        left, top, right, bottom = work_area(self.root)
        width = min(460, max(200, right - left - 24))
        if self.window is None:
            self.window = tk.Toplevel(self.root)
            self.window.withdraw()
            # No transient/grab: remain visible while the main window is minimized.
            self.window.overrideredirect(True)
            self.window.attributes('-topmost', True)
            self.window.protocol('WM_DELETE_WINDOW', lambda: None)
            outer = ttk.Frame(self.window, padding=12, relief='solid', borderwidth=1)
            outer.pack(fill='both', expand=True)
            header = ttk.Frame(outer)
            header.pack(fill='x')
            ttk.Label(header, text='✓ Обработка завершена',
                      font=('Segoe UI', 11, 'bold')).pack(side='left')
            ttk.Button(header, text='✕', width=3, command=self.close).pack(side='right')
            ttk.Label(outer, text='Готовые файлы. Уведомление закрывается крестиком.').pack(
                anchor='w', pady=(6, 8))
            body = ttk.Frame(outer)
            body.pack(fill='both', expand=True)
            self.canvas = tk.Canvas(body, highlightthickness=0, height=220)
            scrollbar = ttk.Scrollbar(body, orient='vertical', command=self.canvas.yview)
            scrollbar.pack(side='right', fill='y')
            self.canvas.pack(side='left', fill='both', expand=True)
            self.canvas.configure(yscrollcommand=scrollbar.set)
            self.items = ttk.Frame(self.canvas)
            item_id = self.canvas.create_window(0, 0, window=self.items, anchor='nw')
            self.canvas.bind('<Configure>', lambda event: self.canvas.itemconfigure(
                item_id, width=event.width))
            self.items.bind('<Configure>', lambda event: self.canvas.configure(
                scrollregion=self.canvas.bbox('all')))
            self.error = ttk.Label(outer, foreground='#a62626', wraplength=width - 30)
            self.error.pack(fill='x', pady=(6, 0))

        for filename in reversed(files):
            children = self.items.pack_slaves()
            row = ttk.Frame(self.items, padding=(0, 6))
            row.pack(fill='x', **({'before': children[0]} if children else {}))
            ttk.Label(row, text=Path(filename).name, font=('Segoe UI', 10, 'bold'),
                      wraplength=width - 48).pack(anchor='w')
            ttk.Label(row, text=str(Path(filename).parent),
                      wraplength=width - 48).pack(anchor='w', pady=(2, 4))
            ttk.Button(row, text='Открыть расположение файла',
                       command=lambda path=filename: self.open_file(path)).pack(anchor='w')
            ttk.Separator(row).pack(fill='x', pady=(8, 0))
        height = min(370, max(180, bottom - top - 24))
        x, y = right - width - 12, bottom - height - 12
        # Signed negative coordinates would mean an offset from the right in Tk.
        self.window.geometry(f'{width}x{height}+{x}+{y}')
        self.window.deiconify()
        self.window.lift()
        self.canvas.yview_moveto(0)

    def open_file(self, filename):
        try:
            reveal_file(filename)
        except OSError as error:
            self.error.configure(text=f'Не удалось открыть файл: {error}')
        else:
            self.error.configure(text='')

    def close(self):
        self.window.destroy()
        self.window = None
