"""Renders `MainWindow` off-screen-ish, grabs a screenshot, saves it next to
this file, then closes. Used only to visualize POC layouts without needing a
human to click around.
"""
import os

from PIL import ImageGrab

from main_window_poc import MainWindow

OUT_PATH = os.path.join(os.path.dirname(__file__), "main_window_poc.png")


def _capture(win: MainWindow):
    win.update_idletasks()
    x = win.winfo_rootx()
    y = win.winfo_rooty()
    w = win.winfo_width()
    h = win.winfo_height()
    # include the title bar / window chrome
    fx, fy = win.winfo_x(), win.winfo_y()
    img = ImageGrab.grab(bbox=(fx, fy, fx + w, fy + (y - fy) + h))
    img.save(OUT_PATH)
    print(f"saved {OUT_PATH}")
    win.destroy()


if __name__ == "__main__":
    win = MainWindow()
    win.geometry("1080x680+100+100")
    win.after(700, lambda: _capture(win))
    win.mainloop()
