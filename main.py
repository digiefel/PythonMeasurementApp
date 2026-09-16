import multiprocessing
from app_logging import configure_logging


def main():
    multiprocessing.freeze_support()
    configure_logging()
    from window_layout import enable_dpi_awareness
    enable_dpi_awareness()
    import tkinter as tk
    from ui import MainUI
    root = tk.Tk()
    app = MainUI(root)
    root.mainloop()


if __name__ == '__main__':
    main()
