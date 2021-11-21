from time import time

from PySide6.QtCore import (
    QReadLocker, QReadWriteLock, QRect,
    QThread, QWriteLocker, Signal
)
from PySide6.QtGui import QGuiApplication
from skimage import img_as_float
from skimage.exposure import rescale_intensity
from skimage.filters import sobel
from skimage.transform import probabilistic_hough_line
import numpy as np

from .utility import Screenshotter, shift_to_front, shuffle_deterministic
from .tile_classification import TileClassifier

def squared_distance(point_a, point_b):
    return (point_b[0] - point_a[0])**2 + (point_b[1] - point_a[1])**2

def contrast_transform(screenshot, contrast_range):
    screenshot_t = img_as_float(screenshot)
    screenshot_t = rescale_intensity(screenshot_t, in_range=contrast_range)
    screenshot_t = sobel(screenshot_t)
    screenshot_t /= max(screenshot_t.max(), 1e-15)
    screenshot_t = np.where(screenshot_t > .1, 1., 0.)
    return screenshot_t

def find_lines(image):
    return probabilistic_hough_line(
        image,
        threshold=500,
        line_gap=8,
        line_length=375,
        theta=np.zeros(1)
    )

def lines_are_similar(line_a, line_b, threshold=36):
    distance = squared_distance(line_a[0], line_b[0])
    if distance > threshold:
        return False
    distance = squared_distance(line_a[1], line_b[1])
    if distance > threshold:
        return False
    return True

def find_matching_line(line_a, match_group, threshold=36):
    for line_b in match_group:
        if lines_are_similar(line_a, line_b, threshold):
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
            if find_matching_line(line_a, match_group):
                match_group.append(line_a)
                break
        else:
            groups_of_similar_lines.append([line_a])

    averaged_lines = np.zeros((len(groups_of_similar_lines), 2, 2))
    for i, matched_lines in enumerate(groups_of_similar_lines):
        averaged_lines[i] = average_lines(matched_lines)
    averaged_lines = averaged_lines[averaged_lines[:, 0, 0].argsort()]
    return averaged_lines.tolist()

def find_target_line(target_line, sorted_lines):
    for line in reversed(sorted_lines):
        if lines_are_similar(line, target_line):
            return line
        if line[0][0] < target_line[0][0]:
            break
    return None

def crop_image_near_line(image, line):
    left = max(0, line[0][0] - 4)
    right = min(image.shape[1], line[0][0] + 5)
    top = max(0, line[1][1] - 4)
    bottom = min(image.shape[0], line[0][1] + 5)
    line[0][0] -= left
    line[1][0] -= left
    line[0][1] -= top
    line[1][1] -= top
    return image[top:bottom, left:right]

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
        self.board_rect = None
        self.prior_confidence_fail = False

        self.init_possible_ranges()
        self.set_default_bounds()

    def init_possible_ranges(self):
        self.possible_ranges = []
        upper_bounds = np.array([.2, .3, .5, .6, .9, 1.])
        for upper_bound in upper_bounds:
            lower_bounds = np.linspace(
                max(0, upper_bound - .3),
                upper_bound,
                4,
                endpoint=False
            )
            for lower_bound in lower_bounds:
                self.possible_ranges.append((lower_bound, upper_bound))
        shuffle_deterministic(self.possible_ranges)

    def set_default_bounds(self):
        self.range_index = 0
        self.contrast_range = self.possible_ranges[0]
        self.optimal_range_index = 0
        self.optimal_n_lines = np.inf

    def get_board(self, screenshot):
        if not self.validate(screenshot):
            self.board_rect = None
            self.detect(screenshot)
        return self.board_rect

    def reset_range_search(self):
        if self.range_index == len(self.possible_ranges):
            if self.optimal_n_lines != np.inf:
                shift_to_front(self.possible_ranges, self.optimal_range_index)
            self.set_default_bounds()
            self.prior_confidence_fail = False
        else:
            self.optimal_n_lines = np.inf

    def set_confidence(self, is_confident):
        if is_confident:
            self.prior_confidence_fail = False
        else:
            if self.prior_confidence_fail:
                self.board_rect = None
                self.reset_range_search()
            else:
                self.prior_confidence_fail = True

    def search_ranges(self, screenshot):
        if self.range_index < len(self.possible_ranges):
            contrast_range = self.possible_ranges[self.range_index]
            screenshot_t = contrast_transform(screenshot, contrast_range)
            vertical_lines = find_lines(screenshot_t)
            n_lines = len(vertical_lines)
            if n_lines < 128:
                square = find_square(vertical_lines)
                if square_is_valid(square) and n_lines < self.optimal_n_lines:
                    self.optimal_range_index = self.range_index
                    self.optimal_n_lines = n_lines
                    self.contrast_range = contrast_range
            self.range_index += 1

    def validate(self, screenshot):
        if self.board_rect is None:
            return False

        left_line = [
            [self.board_rect.left(), self.board_rect.bottom()],
            [self.board_rect.left(), self.board_rect.top()]
        ]
        left_line_region = crop_image_near_line(screenshot, left_line)
        left_line_region = contrast_transform(left_line_region, self.contrast_range)
        screenshot_lines = find_lines(left_line_region)
        if not find_matching_line(left_line, screenshot_lines, 4):
            return False

        right_line = [
            [self.board_rect.right(), self.board_rect.bottom()],
            [self.board_rect.right(), self.board_rect.top()]
        ]
        right_line_region = crop_image_near_line(screenshot, right_line)
        right_line_region = contrast_transform(right_line_region, self.contrast_range)
        screenshot_lines = find_lines(right_line_region)
        return find_matching_line(right_line, screenshot_lines, 4)

    def detect(self, screenshot):
        screenshot_t = contrast_transform(screenshot, self.contrast_range)
        vertical_lines = find_lines(screenshot_t)
        n_lines = len(vertical_lines)
        square = find_square(vertical_lines)
        self.search_ranges(screenshot)
        if square_is_valid(square):
            if n_lines < self.optimal_n_lines:
                self.optimal_n_lines = n_lines
        else:
            square = None
        self.board_rect = square

class Observer(QThread):
    updated_board_rect = Signal(QRect)
    updated_tile_labels = Signal(np.ndarray)

    ObservationInterval = 500

    def __init__(self, settings, overlay):
        super().__init__()

        self.active_screen_name = None
        self.auto_board_detect = settings.auto_board_detect
        self.board_detector = BoardDetector()
        self.board_rect_auto = QRect()
        self.board_rect_manual = settings.board_rect_manual
        self.board_rect_modified = True
        self.is_active = True
        self.is_alive = True
        self.latest_tile_labels = None
        self.lock = QReadWriteLock()
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
        with QReadLocker(self.lock):
            return self.is_alive

    def set_alive(self, should_be_alive):
        with QWriteLocker(self.lock):
            self.is_alive = should_be_alive

    def get_active(self):
        with QReadLocker(self.lock):
            return self.is_active

    def set_active(self, should_be_active):
        with QWriteLocker(self.lock):
            self.is_active = should_be_active

    def get_auto_board_detect(self):
        with QReadLocker(self.lock):
            return self.auto_board_detect

    def set_auto_board_detect(self, should_auto_detect):
        with QWriteLocker(self.lock):
            self.board_rect_modified = True
            self.auto_board_detect = should_auto_detect

    def get_board_rect_auto(self):
        with QReadLocker(self.lock):
            return self.board_rect_auto

    def set_board_rect_auto(self, board_rect):
        with QWriteLocker(self.lock):
            if self.board_rect_auto != board_rect:
                self.board_rect_modified = True
                self.board_rect_auto = board_rect

    def get_board_rect_manual(self):
        with QReadLocker(self.lock):
            return self.board_rect_manual

    def set_board_rect_manual(self, board_rect):
        with QWriteLocker(self.lock):
            if self.board_rect_manual != board_rect:
                self.board_rect_modified = True
                self.board_rect_manual = board_rect

    def detect_board(self, screenshot):
        if self.get_auto_board_detect():
            board_rect = self.board_detector.get_board(screenshot)
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

    def set_observation_success(self, was_successful):
        self.overlay.set_hidden(not was_successful)
        self.board_detector.set_confidence(was_successful)

    def tile_labels_are_different(self, tile_labels):
        return not np.array_equal(self.latest_tile_labels, tile_labels)

    def run(self):
        while self.get_alive():
            self.delay()
            if not self.get_active():
                continue
            screenshot = self.screenshotter.take_gray(self.active_screen_name)
            board_rect = self.detect_board(screenshot)
            if self.get_auto_board_detect():
                self.set_board_rect_auto(board_rect)
            self.check_board_rect_modified()
            if board_rect is None:
                self.set_observation_success(False)
                continue
            tile_labels = self.tile_classifier.predict(screenshot, board_rect)
            if tile_labels is None:
                self.set_observation_success(False)
                continue
            self.set_observation_success(True)
            if self.tile_labels_are_different(tile_labels):
                self.updated_tile_labels.emit(tile_labels)
                self.latest_tile_labels = tile_labels

    def stop(self):
        self.set_active(False)
        self.set_alive(False)
