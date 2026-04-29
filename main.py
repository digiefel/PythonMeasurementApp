import multiprocessing

if __name__ == '__main__':
    multiprocessing.freeze_support()
    import tkinter as tk
    from ui import MainUI
    root = tk.Tk()
    app = MainUI(root)
    root.mainloop()
