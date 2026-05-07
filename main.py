import multiprocessing
from app_logging import configure_logging

if __name__ == '__main__':
    multiprocessing.freeze_support()
    configure_logging()
    import tkinter as tk
    from ui import MainUI
    root = tk.Tk()
    app = MainUI(root)
    root.mainloop()
