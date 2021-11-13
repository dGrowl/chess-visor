from time import time

from PySide6.QtCore import (
    QReadLocker, QReadWriteLock, QRect,
    QThread, QWriteLocker, Signal
)
from PySide6.QtGui import QGuiApplication
from skimage import img_as_float
from skimage.color import rgb2gray
from skimage.exposure import rescale_intensity
from skimage.filters import sobel
from skimage.transform import probabilistic_hough_line
import numpy as np

from .utility import Screenshotter, shift_to_front
from .tile_classification import TileClassifier, extract_tiles_from_screenshot

def squared_distance(point_a, point_b):
    return (point_b[0] - point_a[0])**2 + (point_b[1] - point_a[1])**2

def contrast_transform(screen, dark_range, light_range):
    screen_t = np.array(screen)
    screen_t = rgb2gray(screen_t)
    screen_t = img_as_float(screen_t)
    screen_dark = rescale_intensity(screen_t, in_range=dark_range)
    screen_light = rescale_intensity(screen_t, in_range=light_range)
    screen_t = screen_dark - screen_light
    screen_t = sobel(screen_t)
    screen_t /= max(screen_t.max(), 1e-15)
    screen_t = np.where(screen_t > .1, 1., 0.)
    return screen_t

def find_lines(image):
    return probabilistic_hough_line(
        image,
        threshold=500,
        line_gap=8,
        line_length=375,
        theta=np.array([0., 0.])
    )

def lines_are_similar(line_a, line_b):
    distance = squared_distance(line_a[0], line_b[0])
    if distance > 36:
        return False
    distance = squared_distance(line_a[1], line_b[1])
    if distance > 36:
        return False
    return True

def find_match(line_a, match_group):
    for line_b in match_group:
        if lines_are_similar(line_a, line_b):
            return True
    return False

def average_lines(lines):
    if len(lines) == 1:
        return np.array(lines)
    lines_array = np.array(lines)
    return lines_array.sum(axis=0) / lines_array.shape[0]

def merge_similar_lines(lines):
    groups_of_similar_lines = []
    for line_a in lines:
        for match_group in groups_of_similar_lines:
            if find_match(line_a, match_group):
                match_group.append(line_a)
                break
        else:
            groups_of_similar_lines.append([line_a])

    averaged_lines = np.zeros((len(groups_of_similar_lines), 2, 2))
    for i, matched_lines in enumerate(groups_of_similar_lines):
        averaged_lines[i] = average_lines(matched_lines)
    averaged_lines = averaged_lines[averaged_lines[:,0,0].argsort()]
    return averaged_lines.tolist()

def find_target_line(target_line, sorted_lines):
    for line in reversed(sorted_lines):
        if lines_are_similar(line, target_line):
            return line
        if line[0][0] < target_line[0][0]:
            break
    return None

def find_square(vertical_lines):
    merged_lines = merge_similar_lines(vertical_lines)
    for left_line in merged_lines:
        y_gap = abs(left_line[0][1] - left_line[1][1])
        projected_right_line = [
            [left_line[0][0] + y_gap, left_line[0][1]],
            [left_line[1][0] + y_gap, left_line[1][1]],
        ]
        if actual_right_line := find_target_line(projected_right_line, merged_lines):
            return QRect(
                round(left_line[0][0]),
                round(left_line[1][1]),
                round(actual_right_line[0][0] - left_line[0][0]),
                round(actual_right_line[0][1] - left_line[1][1])
            )
    return None

def square_is_valid(square):
    return square is not None and square.height() >= 256

class BoardDetector:
    def __init__(self):
        self.bound_space = np.mgrid[.1:1:.2, .1:1:.2].T.reshape(25, 2)
        rng = np.random.default_rng(seed=7)
        rng.shuffle(self.bound_space)
        self.prior_confidence_fail = False

        self.set_default_bounds()

    def set_default_bounds(self):
        self.bound_index = 0
        self.dark_bound, self.light_bound = self.bound_space[0]
        self.optimal_bound_index = 0
        self.optimal_n_lines = np.inf

    def reset_search(self):
        if self.bound_index == len(self.bound_space):
            if self.optimal_n_lines != np.inf:
                self.bound_space = shift_to_front(self.bound_space, self.optimal_bound_index)
            self.set_default_bounds()
            self.prior_confidence_fail = False
        else:
            self.optimal_n_lines = np.inf

    def set_confidence(self, is_confident):
        if is_confident:
            self.prior_confidence_fail = False
        else:
            if self.prior_confidence_fail:
                self.reset_search()
            else:
                self.prior_confidence_fail = True

    def search_bounds(self, screenshot):
        if self.bound_index < len(self.bound_space):
            dark_bound, light_bound = self.bound_space[self.bound_index]
            screenshot_t = contrast_transform(
                screenshot,
                (dark_bound, 1),
                (0, light_bound)
            )
            vertical_lines = find_lines(screenshot_t)
            n_lines = len(vertical_lines)
            if n_lines < 128:
                square = find_square(vertical_lines)
                if square_is_valid(square) and n_lines < self.optimal_n_lines:
                    self.optimal_bound_index = self.bound_index
                    self.optimal_n_lines = n_lines
                    self.dark_bound = dark_bound
                    self.light_bound = light_bound
            self.bound_index += 1

    def detect(self, screenshot):
        screenshot_t = contrast_transform(
            screenshot,
            (self.dark_bound, 1),
            (0, self.light_bound)
        )
        vertical_lines = find_lines(screenshot_t)
        n_lines = len(vertical_lines)
        square = find_square(vertical_lines)
        self.search_bounds(screenshot)
        if square_is_valid(square):
            if n_lines < self.optimal_n_lines:
                self.optimal_n_lines = n_lines
        else:
            square = None
        return square

class Observer(QThread):
    updated_board_rect = Signal(QRect)
    updated_tile_labels = Signal(np.ndarray)

    ObservationInterval = 500

    def __init__(self, settings, overlay):
        super().__init__()

        self.access_lock = QReadWriteLock()
        self.active_screen_name = None
        self.auto_board_detect = settings.auto_board_detect
        self.board_detector = BoardDetector()
        self.board_rect_auto = QRect()
        self.board_rect_manual = settings.board_rect_manual
        self.board_rect_modified = True
        self.found_chessboard = False
        self.is_active = True
        self.is_alive = True
        self.latest_tile_labels = None
        self.overlay = overlay
        self.screenshotter = Screenshotter()
        self.start_time = 0
        self.tile_classifier = TileClassifier()

        self.set_active_screen(settings.active_screen_name)

    def check_board_rect_modified(self):
        if self.board_rect_modified:
            self.updated_board_rect.emit(self.get_board_rect())
            self.board_rect_modified = False

    def set_active_screen(self, screen_name):
        for screen in QGuiApplication.screens():
            if screen.name() == screen_name:
                self.active_screen_name = screen.name()
                break
        else:
            screen_names = [screen.name() for screen in QGuiApplication.screens()]
            error_message = (
                f"Could not find a screen named '{screen_name}'\n"
                f"  Available screens: {screen_names}"
            )
            raise RuntimeError(error_message)

    def get_alive(self):
        with QReadLocker(self.access_lock):
            return self.is_alive

    def set_alive(self, should_be_alive):
        with QWriteLocker(self.access_lock):
            self.is_alive = should_be_alive

    def get_active(self):
        with QReadLocker(self.access_lock):
            return self.is_active

    def set_active(self, should_be_active):
        with QWriteLocker(self.access_lock):
            self.is_active = should_be_active

    def get_auto_board_detect(self):
        with QReadLocker(self.access_lock):
            return self.auto_board_detect

    def set_auto_board_detect(self, should_auto_detect):
        with QWriteLocker(self.access_lock):
            self.auto_board_detect = should_auto_detect

    def get_board_rect_auto(self):
        with QReadLocker(self.access_lock):
            return self.board_rect_auto

    def set_board_rect_auto(self, board_rect):
        with QWriteLocker(self.access_lock):
            if self.board_rect_auto != board_rect:
                self.board_rect_modified = True
                self.board_rect_auto = board_rect

    def get_board_rect_manual(self):
        with QReadLocker(self.access_lock):
            return self.board_rect_manual

    def set_board_rect_manual(self, board_rect):
        with QWriteLocker(self.access_lock):
            if self.board_rect_manual != board_rect:
                self.board_rect_modified = True
                self.board_rect_manual = board_rect

    def detect_board(self, screenshot):
        if self.get_auto_board_detect():
            board_rect = self.board_detector.detect(screenshot)
            if board_rect is None:
                self.found_chessboard = False
            return board_rect
        return self.board_rect_manual

    def get_board_rect(self):
        if self.get_auto_board_detect():
            return self.get_board_rect_auto()
        return self.get_board_rect_manual()

    def delay(self):
        observation_duration = (time() - self.start_time) * 1000
        remaining_time = Observer.ObservationInterval - observation_duration
        if remaining_time > 0:
            QThread.msleep(remaining_time)
        self.start_time = time()

    def run(self):
        while self.get_alive():
            self.delay()
            if not self.get_active():
                continue
            screenshot = self.screenshotter.shot(self.active_screen_name)
            board_rect = self.detect_board(screenshot)
            if self.get_auto_board_detect():
                self.set_board_rect_auto(board_rect)
            self.check_board_rect_modified()
            if board_rect is None:
                self.overlay.set_hidden(True)
                self.board_detector.set_confidence(False)
                continue
            tiles = extract_tiles_from_screenshot(screenshot, board_rect)
            tile_labels = self.tile_classifier.predict(tiles)
            self.found_chessboard = tile_labels is not None
            if not self.found_chessboard:
                self.overlay.set_hidden(True)
                self.board_detector.set_confidence(False)
                continue
            self.overlay.set_hidden(False)
            self.board_detector.set_confidence(True)
            if np.array_equal(self.latest_tile_labels, tile_labels):
                continue
            self.updated_tile_labels.emit(tile_labels)
            self.latest_tile_labels = tile_labels

    def stop(self):
        self.set_active(False)
        self.set_alive(False)
