from PySide6.QtCore import QCoreApplication, QRect, QObject, Qt, Signal, Slot
from PySide6.QtWidgets import QMenu, QSystemTrayIcon
from PySide6.QtGui import QBrush, QColor, QGradient, QIcon, QPainter, QPixmap
import keyboard

from .analysis import Analyzer
from .game_state import GameState
from .observation import Observer
from .overlay import Overlay
from .settings import Settings, SettingsWindow
from .utility import is_valid_hotkey

def draw_icon_background(pixmap, brush):
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setPen(Qt.transparent)
    painter.setBrush(brush)
    icon_offset = 2
    painter.drawRoundedRect(
        icon_offset, icon_offset,
        128 - icon_offset, 128 - icon_offset,
        16, 16
    )
    painter.end()

def draw_icon_chessboard(pixmap):
    board_offset = 16
    board_size = pixmap.width() - board_offset * 2
    square_size = round(board_size / 3)
    black = QColor(52, 52, 52)
    white = QColor(216, 216, 216)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setPen(white)
    painter.setBrush(QBrush(QGradient.RiskyConcrete))
    board_rect = QRect(
        board_offset, board_offset,
        board_size, board_size
    )
    painter.drawRoundedRect(board_rect, 12, 12)
    top_center_square = QRect(
        board_offset + square_size, board_offset,
        square_size, square_size
    )
    center_left_square = top_center_square.translated(-square_size, square_size)
    center_right_square = top_center_square.translated(square_size, square_size)
    bottom_center_square = top_center_square.translated(0, 2 * square_size)
    painter.setPen(black)
    painter.fillRect(top_center_square, QGradient.ViciousStance)
    painter.fillRect(center_left_square, QGradient.ViciousStance)
    painter.fillRect(center_right_square, QGradient.ViciousStance)
    painter.fillRect(bottom_center_square, QGradient.ViciousStance)
    painter.end()

def generate_icon(size, background_brush):
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.transparent)
    draw_icon_background(pixmap, background_brush)
    draw_icon_chessboard(pixmap)
    return QIcon(pixmap)

def generate_icons():
    active_brush = QBrush(QGradient.OrangeJuice)
    inactive_brush = QBrush(QGradient.MountainRock)
    active_icon = generate_icon(128, active_brush)
    inactive_icon = generate_icon(128, inactive_brush)
    return active_icon, inactive_icon

class Visor(QObject):
    toggle_active = Signal(bool)

    def __init__(self):
        super().__init__()

        self.is_active = True
        self.toggle_active.connect(self.set_active)

        settings = Settings(Settings.Available)

        self.init_icon()
        self.init_overlay(settings)
        self.init_analyzer(settings)
        self.init_game_state()
        self.init_observer(settings)
        self.init_settings_window(settings)

    def init_icon(self):
        if QSystemTrayIcon.isSystemTrayAvailable():
            self.tray_icon = QSystemTrayIcon(self)
            menu = QMenu()

            self.active_action = menu.addAction("Active")
            self.active_action.setCheckable(True)
            self.active_action.setChecked(True)
            self.active_action.triggered.connect(self.set_active)

            menu.addSeparator()

            settings_window_action = menu.addAction("Settings")
            settings_window_action.triggered.connect(self.show_settings_window)

            reset_assumptions_action = menu.addAction("Reset Assumptions")
            reset_assumptions_action.triggered.connect(self.reset_assumptions)

            exit_action = menu.addAction("Exit")
            exit_action.triggered.connect(self.finish)

            self.active_icon, self.inactive_icon = generate_icons()
            self.tray_icon.setContextMenu(menu)
            self.tray_icon.activated.connect(self.icon_activated)
            self.tray_icon.setIcon(self.active_icon)

    def init_overlay(self, settings):
        self.overlay = Overlay(settings)

    def init_analyzer(self, settings):
        self.analyzer = Analyzer(settings)
        self.analyzer.updated_moves.connect(self.overlay.set_moves)

    def init_game_state(self):
        self.game_state = GameState()
        self.game_state.updated_possible_games.connect(self.analyzer.get_best_moves)

    def init_observer(self, settings):
        self.set_active_hotkey(settings.active_hotkey)
        self.observer = Observer(settings, self.overlay)
        self.observer.updated_tile_labels.connect(self.game_state.set_position)
        self.observer.updated_tile_labels.connect(self.overlay.clear)
        self.observer.updated_board_rect.connect(self.overlay.set_board_rect)

    def init_settings_window(self, settings):
        self.settings_window = None
        if not settings.has_valid_engine_path():
            self.show_settings_window()

    @Slot(QSystemTrayIcon.ActivationReason)
    def icon_activated(self, activation):
        if activation == QSystemTrayIcon.Trigger:
            self.set_active(not self.observer.get_active())

    @Slot()
    def show_settings_window(self):
        if self.settings_window is None:
            self.settings_window = SettingsWindow(self.observer)
            if self.observer.get_active():
                self.settings_window.setWindowIcon(self.active_icon)
            else:
                self.settings_window.setWindowIcon(self.inactive_icon)
            self.settings_window.updated_active_hotkey.connect(self.set_active_hotkey)
            self.settings_window.updated_active_screen.connect(self.overlay.set_active_screen)
            self.settings_window.updated_active_screen.connect(self.set_active_screen)
            self.settings_window.updated_analyzer.connect(self.analyzer.update_settings)
            self.settings_window.updated_autodetect.connect(self.set_auto_board_detect)
            self.settings_window.updated_manual_rect.connect(self.set_board_rect_manual)
            self.settings_window.destroyed.connect(self.close_settings_window)
        self.settings_window.bring_to_front()

    @Slot()
    def close_settings_window(self):
        self.settings_window = None

    @Slot(bool)
    def set_active(self, should_be_active):
        self.is_active = should_be_active
        self.active_action.setChecked(should_be_active)
        self.observer.set_active(should_be_active)
        self.overlay.set_active(should_be_active)
        if should_be_active:
            self.tray_icon.setIcon(self.active_icon)
            if self.settings_window is not None:
                self.settings_window.setWindowIcon(self.active_icon)
        else:
            self.tray_icon.setIcon(self.inactive_icon)
            if self.settings_window is not None:
                self.settings_window.setWindowIcon(self.inactive_icon)

    @Slot(str)
    def set_active_hotkey(self, hotkey):
        if is_valid_hotkey(hotkey):
            keyboard.unhook_all()
            keyboard.add_hotkey(
                hotkey,
                lambda: self.toggle_active.emit(not self.is_active)
            )

    @Slot(bool)
    def set_auto_board_detect(self, should_auto_detect):
        self.observer.set_auto_board_detect(should_auto_detect)

    @Slot(str)
    def set_active_screen(self, screen_name):
        self.observer.set_active_screen(screen_name)

    @Slot(QRect)
    def set_board_rect_manual(self, board_rect):
        self.observer.set_board_rect_manual(board_rect)

    @Slot()
    def reset_assumptions(self):
        self.game_state.reset_assumptions()
        self.game_state.update_possible_games()

    def start(self):
        self.analyzer.start()
        self.observer.start()
        self.tray_icon.show()
        self.overlay.show()

    @Slot()
    def finish(self):
        self.overlay.hide()
        self.tray_icon.hide()
        self.observer.stop()
        self.analyzer.stop()
        if self.settings_window is not None:
            self.settings_window.close()
        self.observer.wait()
        self.analyzer.wait()
        QCoreApplication.quit()
