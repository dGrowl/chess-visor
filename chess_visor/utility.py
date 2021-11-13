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

def increment_key(d, k):
    if k not in d:
        d[k] = 1
    else:
        d[k] += 1

def sort_on_column(array, j, reverse=False):
    return sorted(array, key=lambda entry: entry[j], reverse=reverse)

def shift_to_front(array, i):
    if i != 0:
        i_t = (i + 1) % len(array)
        array_t = np.roll(array, 1, axis=0)
        array_t[[i_t, 0]] = array_t[[0, i_t]]
        return array_t
    return array

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
