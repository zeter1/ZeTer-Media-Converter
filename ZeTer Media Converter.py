"""Thin launcher for the modular ZeTer Media Converter application.

Business logic lives in the ``videovaudio`` package.
"""

import tkinter as tk

from videovaudio import VideoToAudioConverter


def main():
    root = tk.Tk()
    try:
        from ctypes import windll
        windll.shcore.SetProcessDpiAwareness(1)
    except:
        pass
    VideoToAudioConverter(root)
    root.mainloop()


if __name__ == "__main__":
    main()
