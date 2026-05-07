import multiprocessing
from app_logging import configure_logging


def main():
    multiprocessing.freeze_support()
    configure_logging()
    import tkinter as tk
    from ui import MainUI
    root = tk.Tk()
    app = MainUI(root)
    root.mainloop()


if __name__ == '__main__':
    main()
