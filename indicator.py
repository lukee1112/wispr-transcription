#!/usr/bin/env python3
"""Recording indicator overlay - runs as a subprocess."""
import signal
import sys

_should_quit = False


def _handle_signal(*_):
    global _should_quit
    _should_quit = True


signal.signal(signal.SIGTERM, _handle_signal)
signal.signal(signal.SIGINT, _handle_signal)

try:
    import tkinter as tk
except ImportError:
    # If tkinter isn't available, just sit quietly until terminated
    signal.pause()
    sys.exit(0)


_REC_COLOR = "#dc2626"


def main():
    root = tk.Tk()
    root.title("")
    root.overrideredirect(True)
    root.attributes("-topmost", True)

    try:
        root.attributes("-alpha", 0.9)
    except tk.TclError:
        pass

    root.configure(bg=_REC_COLOR)

    frame = tk.Frame(root, bg=_REC_COLOR, padx=12, pady=6)
    frame.pack()

    tk.Label(
        frame,
        text="\u25cf REC",
        fg="white",
        bg=_REC_COLOR,
        font=("Ubuntu", 11, "bold"),
    ).pack()

    # Position top-right corner
    root.update_idletasks()
    screen_w = root.winfo_screenwidth()
    w = root.winfo_width()
    root.geometry(f"+{screen_w - w - 20}+20")

    def check_quit():
        if _should_quit:
            try:
                root.quit()
                root.destroy()
            except Exception:
                pass
            sys.exit(0)
        root.after(100, check_quit)

    root.after(100, check_quit)
    root.mainloop()


if __name__ == "__main__":
    main()
