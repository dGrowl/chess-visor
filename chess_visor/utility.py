from mss import mss
from PySide6.QtGui import QGuiApplication, QImage, QPixmap
import keyboard
import numpy as np

def array_to_pixmap(array):
    height, width, n_channels = array.shape
    image = QImage(
        array.data,
        width,
        height,
        n_channels * width,
        QImage.Format_RGB888
    )
    pixmap = QPixmap(image)
    return pixmap

def shuffle_deterministic(array_like, seed):
    rng = np.random.default_rng(seed=seed)
    rng.shuffle(array_like)

def increment_key(d, k):
    if k not in d:
        d[k] = 1
    else:
        d[k] += 1

def is_even(x):
    return (x % 2) == 0

def is_valid_hotkey(hotkey):
    try:
        keyboard.parse_hotkey(hotkey)
    except ValueError:
        return False
    return True

def shift_to_front(array, i):
    if i != 0:
        item = array[i]
        array[1:i + 1] = array[0:i]
        array[0] = item

def sort_on_column(array, j, reverse=False):
    return sorted(array, key=lambda entry: entry[j], reverse=reverse)

class Screenshotter:
    def __init__(self):
        self.capture_tool = mss()
        self.screen_regions = dict()
        for screen in QGuiApplication.screens():
            screen_rect = screen.geometry()
            screen_pixel_ratio = screen.devicePixelRatio()
            screen_geometry = {
                "left": screen_rect.left(),
                "top": screen_rect.top(),
                "width": int(screen_rect.width() * screen_pixel_ratio),
                "height": int(screen_rect.height() * screen_pixel_ratio)
            }
            self.screen_regions[screen.name()] = screen_geometry

    def shot(self, screen_name):
        screen_region = self.screen_regions[screen_name]
        screen_dimensions = (
            screen_region["height"],
            screen_region["width"],
            3
        )
        screenshot = self.capture_tool.grab(screen_region).rgb
        screenshot = np.frombuffer(screenshot, dtype=np.uint8)
        screenshot = screenshot.reshape(screen_dimensions)
        return screenshot
