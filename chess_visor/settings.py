from platform import system
from os.path import isfile

from PySide6.QtCore import QRect, QSize, Qt, QTimer, Signal, Slot
from PySide6.QtGui import (
    QBrush, QColor, QFont, QGuiApplication, QIcon,
    QPainter, QPen, QPixmap, QTransform
)
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QFileDialog, QGridLayout,
    QGroupBox, QLabel, QLineEdit, QMessageBox,
    QPushButton, QSizePolicy, QSpinBox, QVBoxLayout,
    QWidget
)
import pytomlpp as toml

from .utility import Screenshotter, array_to_pixmap, is_valid_hotkey

def platform_init(id):
    if system() == "Windows":
        from ctypes import WinDLL
        shell32 = WinDLL("shell32")
        shell32.SetCurrentProcessExplicitAppUserModelID(id)

class Settings:
    Default = 1
    File = 2
    Available = 3

    def __init__(self, load_type=None):
        if load_type == Settings.Available:
            self.load_available()
        elif load_type == Settings.File:
            self.load_file()
        elif load_type == Settings.Default:
            self.load_defaults()
        else:
            self.load_empty()

    def load_empty(self):
        self.active_screen_name = None
        self.auto_board_detect = None
        self.board_rect_manual = None
        self.engine_path = None
        self.engine_process_count = None

    def load_available(self):
        try:
            self.load_file()
        except:
            self.load_defaults()
            self.save()

    def load_defaults(self):
        primary_screen = QGuiApplication.primaryScreen()
        screen_size = primary_screen.size()
        rect_size = min(screen_size.width(), screen_size.height()) // 2

        if system() == "Windows":
            self.engine_path = "./engine/stockfish_14_x64.exe"
        elif system() == "Linux":
            self.engine_path = "./engine/stockfish_14_x64"
        else:
            self.engine_path = ""

        if not self.has_valid_engine_path():
            self.engine_path = ""

        self.active_hotkey = "alt+z"
        self.active_screen_name = primary_screen.name()
        self.auto_board_detect = True
        self.board_rect_manual = QRect(0, 0, rect_size, rect_size)
        self.engine_process_count = 8

    def load_file(self):
        settings = toml.load("settings.toml")

        board_settings = settings["Board"]
        system_settings = settings["System"]
        manual_rect = board_settings["ManualRect"]

        self.active_hotkey = system_settings["ActiveHotkey"]
        self.active_screen_name = system_settings["Screen"]
        self.auto_board_detect = board_settings["AutoDetect"]
        self.board_rect_manual = QRect(
            manual_rect["x"],
            manual_rect["y"],
            manual_rect["w"],
            manual_rect["h"]
        )
        self.engine_path = system_settings["EnginePath"]
        self.engine_process_count = system_settings["EngineProcessCount"]

    def save(self):
        settings = dict()

        system_settings = dict()
        system_settings["ActiveHotkey"] = self.active_hotkey
        system_settings["Screen"] = self.active_screen_name
        system_settings["EnginePath"] = self.engine_path
        system_settings["EngineProcessCount"] = self.engine_process_count
        settings["System"] = system_settings

        board_settings = dict()
        board_settings["AutoDetect"] = self.auto_board_detect
        manual_rect = dict()
        manual_rect["x"] = self.board_rect_manual.left()
        manual_rect["y"] = self.board_rect_manual.top()
        manual_rect["w"] = self.board_rect_manual.width()
        manual_rect["h"] = self.board_rect_manual.height()
        board_settings["ManualRect"] = manual_rect
        settings["Board"] = board_settings

        toml.dump(settings, "settings.toml")

    def has_valid_engine_path(self):
        return isfile(self.engine_path)

    def has_valid_active_hotkey(self):
        return is_valid_hotkey(self.active_hotkey)

    def board_is_square(self):
        return self.board_rect_manual.height() == self.board_rect_manual.width()

class SettingsWindow(QWidget):
    updated_active_hotkey = Signal(str)
    updated_active_screen = Signal(str)
    updated_analyzer = Signal(str, int)
    updated_autodetect = Signal(bool)
    updated_manual_rect = Signal(QRect)

    DarkGray = QColor(33, 33, 33)
    FadedBlack = QColor(0, 0, 0, 128)
    LightGray = QColor(222, 222, 222)
    LightGreen = QColor(128, 255, 128)
    Red = QColor(255, 64, 64)
    DarkBrush = QBrush(DarkGray)
    GreenPen = QPen(LightGreen, 2, j=Qt.MiterJoin)
    LightBrush = QBrush(LightGray)
    RedPen = QPen(Red)
    DefaultSize = QSize(256, 256)
    MirrorXY = QTransform.fromScale(-1, -1)
    PreviewFont = QFont("sans-serif", 10, QFont.DemiBold)
    PreviewPadding = 32
    PreviewPaddingx2 = 2 * PreviewPadding
    PreviewWidth = PreviewHeight = 144
    RedrawInterval = 500

    def __init__(self, observer):
        super().__init__()

        self.active_screenshot = None
        self.observer = observer
        self.screenshot_timer = QTimer()
        self.screenshotter = Screenshotter()
        self.settings = Settings(Settings.Available)
        self.unsaved_changes = False

        self.init_window()
        self.init_screen_controls()
        self.init_board_controls()
        self.init_system_controls()
        self.init_save_controls()

        self.start_screen_capture()

    def closeEvent(self, event):
        if self.unsaved_changes:
            unsaved_response = QMessageBox.question(
                self,
                "Warning: Unsaved Changes",
                "You haven't saved the changes you've made. Would you still like to exit?",
                QMessageBox.Cancel | QMessageBox.Discard | QMessageBox.Save,
                defaultButton=QMessageBox.Cancel
            )
            if unsaved_response == QMessageBox.Cancel:
                event.ignore()
            elif unsaved_response == QMessageBox.Discard:
                event.accept()
            elif unsaved_response == QMessageBox.Save:
                self.save_changes()
                event.accept()
        else:
            event.accept()

    def init_window(self):
        self.resize(SettingsWindow.DefaultSize)
        self.setWindowFlags(Qt.MSWindowsFixedSizeDialogHint)
        self.setAttribute(Qt.WA_DeleteOnClose)
        self.setAttribute(Qt.WA_QuitOnClose, False)
        self.central_layout = QGridLayout(self)
        window_name = "ChessVisor: Settings"
        self.setWindowTitle(window_name)
        platform_init(window_name)

    def init_screen_controls(self):
        self.screen_names = []
        screen_img_size = QSize(192, 108)
        screen_group = QGroupBox("Screen", self)
        screen_column = QVBoxLayout(screen_group)
        self.central_layout.addWidget(screen_group, 0, 0)

        self.screen_menu = QComboBox(screen_group)
        self.screen_menu.setIconSize(screen_img_size)
        screen_column.addWidget(self.screen_menu)

        for i, screen in enumerate(QGuiApplication.screens()):
            shot = self.screenshotter.take(screen.name())
            shot = array_to_pixmap(shot)
            screen_icon = QIcon(shot)
            self.screen_menu.addItem(screen_icon, "")
            if screen.name() == self.settings.active_screen_name:
                self.screen_menu.setCurrentIndex(i)
                active_screen_size = screen.size()
                self.active_screen_width = active_screen_size.width()
                self.active_screen_height = active_screen_size.height()
            self.screen_names.append(screen.name())
        self.screen_menu.currentIndexChanged.connect(self.set_active_screen)

    def init_board_controls(self):
        board_group = QGroupBox("Chessboard", self)
        board_column = QVBoxLayout(board_group)
        self.central_layout.addWidget(board_group, 0, 1, 2, 1)

        preview_layout = QGridLayout()
        board_column.addLayout(preview_layout)

        topleft_example = QLabel(board_group)
        botright_example = QLabel(board_group)
        topleft_pixmap, botright_pixmap = self.create_corner_icons()
        topleft_example.setPixmap(topleft_pixmap)
        botright_example.setPixmap(botright_pixmap)

        topleft_label = QLabel("Top-Left Corner", board_group)
        topleft_label.setAlignment(Qt.AlignVCenter)
        topleft_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        preview_layout.addWidget(topleft_example, 0, 0)
        preview_layout.addWidget(topleft_label,   0, 1)

        botright_label = QLabel("Bottom-Right Corner", board_group)
        botright_label.setAlignment(Qt.AlignVCenter)
        botright_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        preview_layout.addWidget(botright_example, 0, 2)
        preview_layout.addWidget(botright_label,   0, 3)

        self.topleft_preview = QLabel(board_group)
        self.botright_preview = QLabel(board_group)
        preview_layout.addWidget(self.topleft_preview,  1, 0, 1, 2)
        preview_layout.addWidget(self.botright_preview, 1, 2, 1, 2)

        shape_grid = QGridLayout()
        board_column.addLayout(shape_grid)

        autodetect_checkbox = QCheckBox("Auto-Detect", board_group)
        autodetect_checkbox.setChecked(self.settings.auto_board_detect)
        autodetect_checkbox.clicked.connect(self.set_board_autodetect)
        shape_grid.addWidget(autodetect_checkbox, 0, 0, 1, 2)

        left_spinbox_label = QLabel("Left:", board_group)
        self.left_spinbox = QSpinBox(board_group)
        self.left_spinbox.setAccelerated(True)
        self.left_spinbox.setMinimum(0)
        self.left_spinbox.setMaximum(self.active_screen_width)
        self.left_spinbox.setValue(self.settings.board_rect_manual.left())
        self.left_spinbox.valueChanged.connect(self.set_board_left)
        shape_grid.addWidget(left_spinbox_label, 1, 0)
        shape_grid.addWidget(self.left_spinbox,  1, 1)

        top_spinbox_label = QLabel("Top:", board_group)
        self.top_spinbox = QSpinBox(board_group)
        self.top_spinbox.setAccelerated(True)
        self.top_spinbox.setMinimum(0)
        self.top_spinbox.setMaximum(self.active_screen_height)
        self.top_spinbox.setValue(self.settings.board_rect_manual.top())
        self.top_spinbox.valueChanged.connect(self.set_board_top)
        shape_grid.addWidget(top_spinbox_label, 2, 0)
        shape_grid.addWidget(self.top_spinbox,  2, 1)

        self.constrain_dims = self.settings.board_is_square()
        self.dim_constraint_checkbox = QCheckBox("Lock Height=Width", board_group)
        self.dim_constraint_checkbox.setChecked(self.constrain_dims)
        self.dim_constraint_checkbox.clicked.connect(self.set_dim_constraints)
        shape_grid.addWidget(self.dim_constraint_checkbox, 0, 2, 1, 2)

        width_spinbox_label = QLabel("Width:", board_group)
        self.width_spinbox = QSpinBox(board_group)
        self.width_spinbox.setAccelerated(True)
        self.width_spinbox.setMinimum(8)
        self.width_spinbox.setMaximum(self.active_screen_width)
        self.width_spinbox.setValue(self.settings.board_rect_manual.width())
        self.width_spinbox.valueChanged.connect(self.set_board_width)
        shape_grid.addWidget(width_spinbox_label, 1, 2)
        shape_grid.addWidget(self.width_spinbox,  1, 3)

        height_spinbox_label = QLabel("Height:", board_group)
        self.height_spinbox = QSpinBox(board_group)
        self.height_spinbox.setAccelerated(True)
        self.height_spinbox.setMinimum(8)
        self.height_spinbox.setMaximum(self.active_screen_height)
        self.height_spinbox.setValue(self.settings.board_rect_manual.height())
        self.height_spinbox.valueChanged.connect(self.set_board_height)
        shape_grid.addWidget(height_spinbox_label, 2, 2)
        shape_grid.addWidget(self.height_spinbox,  2, 3)

        self.set_board_controls_enabled(not self.settings.auto_board_detect)

        self.set_dim_constraints(self.constrain_dims)

    def init_system_controls(self):
        system_group = QGroupBox("System", self)
        system_grid = QGridLayout(system_group)
        self.central_layout.addWidget(system_group, 1, 0)

        self.engine_path_label = QLabel("UCI Engine Path:", system_group)
        system_grid.addWidget(self.engine_path_label, 0, 0)

        browse_button = QPushButton("Browse", system_group)
        browse_button.clicked.connect(self.browse_engine_path)
        system_grid.addWidget(browse_button, 0, 1)

        self.engine_path_field = QLineEdit(self.settings.engine_path, system_group)
        self.engine_path_field.textChanged.connect(self.set_engine_path)
        self.check_engine_path()
        system_grid.addWidget(self.engine_path_field, 1, 0, 1, 2)

        n_engine_processes_label = QLabel("Engine Process Count:", system_group)
        n_engine_processes_spinbox = QSpinBox(system_group)
        n_engine_processes_spinbox.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        n_engine_processes_spinbox.setMinimum(1)
        n_engine_processes_spinbox.setMaximum(32)
        n_engine_processes_spinbox.setValue(self.settings.engine_process_count)
        n_engine_processes_spinbox.valueChanged.connect(self.set_engine_process_count)
        system_grid.addWidget(n_engine_processes_label,   2, 0)
        system_grid.addWidget(n_engine_processes_spinbox, 2, 1)

        self.active_hotkey_label = QLabel("Toggle Active Hotkey:", system_group)
        self.active_hotkey_field = QLineEdit(self.settings.active_hotkey, system_group)
        self.active_hotkey_field.textChanged.connect(self.set_active_hotkey)
        self.check_active_hotkey()
        system_grid.addWidget(self.active_hotkey_label, 3, 0)
        system_grid.addWidget(self.active_hotkey_field, 3, 1)

    def init_save_controls(self):
        save_button = QPushButton("Save", self)
        save_button.clicked.connect(self.save_changes)
        save_button.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.central_layout.addWidget(save_button, 2, 0, 1, 3, Qt.AlignHCenter)

    def bring_to_front(self):
        self.setWindowState(Qt.WindowActive)
        self.show()
        self.activateWindow()
        self.raise_()

    def start_screen_capture(self):
        self.update_screenshots()
        self.screenshot_timer.timeout.connect(self.update_screenshots)
        self.screenshot_timer.start(SettingsWindow.RedrawInterval)

    def create_corner_icons(self):
        topleft_icon = QPixmap(32, 32)
        topleft_icon.fill(Qt.black)
        topleft_rect = QRect(9, 9, 32, 32)
        painter = QPainter(topleft_icon)
        painter.setPen(SettingsWindow.GreenPen)
        painter.drawRect(topleft_rect)
        tile_marks = [10, 22]
        for x, y in zip(tile_marks, tile_marks):
            tile = QRect(x, y, 12, 12)
            if x == y:
                painter.fillRect(tile, SettingsWindow.LightBrush)
            else:
                painter.fillRect(tile, SettingsWindow.DarkBrush)
        painter.end()
        botright_icon = topleft_icon.transformed(SettingsWindow.MirrorXY)
        return topleft_icon, botright_icon

    @Slot(bool)
    def set_dim_constraints(self, should_be_constrained):
        self.dims_constrained = should_be_constrained
        width_constraint = self.active_screen_width - self.settings.board_rect_manual.left()
        height_constraint = self.active_screen_height - self.settings.board_rect_manual.top()
        if should_be_constrained:
            self.height_spinbox.setValue(self.width_spinbox.value())
            self.width_spinbox.valueChanged.connect(self.height_spinbox.setValue)
            self.height_spinbox.valueChanged.connect(self.width_spinbox.setValue)
            if width_constraint > height_constraint:
                width_constraint = height_constraint
            else:
                height_constraint = width_constraint
        else:
            self.width_spinbox.valueChanged.disconnect(self.height_spinbox.setValue)
            self.height_spinbox.valueChanged.disconnect(self.width_spinbox.setValue)
        self.width_spinbox.setMaximum(width_constraint)
        self.height_spinbox.setMaximum(height_constraint)

    def draw_board_preview(self):
        if self.active_screenshot is None:
            return

        padded_width = self.active_screenshot.width() + SettingsWindow.PreviewPaddingx2
        padded_height = self.active_screenshot.height() + SettingsWindow.PreviewPaddingx2
        preview_canvas = QPixmap(padded_width, padded_height)
        preview_canvas.fill(Qt.black)

        board_rect = None
        should_draw_board = True
        if self.settings.auto_board_detect and self.observer is not None:
            board_rect = self.observer.get_board_rect_auto()
        else:
            board_rect = self.settings.board_rect_manual
        if board_rect is None:
            should_draw_board = False
            board_rect = self.active_screenshot.rect()

        adjusted_board_rect = board_rect.translated(
            SettingsWindow.PreviewPadding,
            SettingsWindow.PreviewPadding
        )

        topleft_src_rect = QRect(board_rect)
        topleft_src_rect.setWidth(SettingsWindow.PreviewWidth)
        topleft_src_rect.setHeight(SettingsWindow.PreviewHeight)

        botright_src_rect = QRect(
            adjusted_board_rect.right() - SettingsWindow.PreviewWidth + SettingsWindow.PreviewPadding,
            adjusted_board_rect.bottom() - SettingsWindow.PreviewHeight + SettingsWindow.PreviewPadding,
            SettingsWindow.PreviewWidth,
            SettingsWindow.PreviewHeight
        )

        if topleft_src_rect.right() > padded_width:
            topleft_src_rect.moveLeft(padded_width - topleft_src_rect.width())
        if topleft_src_rect.bottom() > padded_height:
            topleft_src_rect.moveTop(padded_height - topleft_src_rect.height())

        if botright_src_rect.left() < 0:
            botright_src_rect.moveLeft(0)
        if botright_src_rect.top() < 0:
            botright_src_rect.moveTop(0)
        if botright_src_rect.right() > padded_width:
            botright_src_rect.moveLeft(padded_width - botright_src_rect.width())
        if botright_src_rect.bottom() > padded_height:
            botright_src_rect.moveTop(padded_height - botright_src_rect.height())

        painter = QPainter(preview_canvas)
        painter.drawPixmap(
            SettingsWindow.PreviewPadding,
            SettingsWindow.PreviewPadding,
            self.active_screenshot
        )
        if should_draw_board:
            painter.setPen(SettingsWindow.GreenPen)
            painter.drawRect(adjusted_board_rect.adjusted(-1, -1, 1, 1))
        else:
            painter.setPen(SettingsWindow.RedPen)
            painter.setFont(SettingsWindow.PreviewFont)
            painter.fillRect(topleft_src_rect, SettingsWindow.FadedBlack)
            painter.fillRect(botright_src_rect, SettingsWindow.FadedBlack)
            painter.drawText(topleft_src_rect, Qt.AlignCenter, "No Board Detected")
            painter.drawText(botright_src_rect, Qt.AlignCenter, "No Board Detected")
        painter.end()

        topleft_pixmap = preview_canvas.copy(topleft_src_rect)
        botright_pixmap = preview_canvas.copy(botright_src_rect)
        self.topleft_preview.setPixmap(topleft_pixmap)
        self.botright_preview.setPixmap(botright_pixmap)

    def check_engine_path(self):
        if not self.settings.has_valid_engine_path():
            self.engine_path_label.setStyleSheet("color: red;")
            self.engine_path_field.setStyleSheet("color: red;")
        else:
            self.engine_path_label.setStyleSheet("color: initial;")
            self.engine_path_field.setStyleSheet("color: initial;")

    def check_active_hotkey(self):
        if not self.settings.has_valid_active_hotkey():
            self.active_hotkey_label.setStyleSheet("color: red;")
            self.active_hotkey_field.setStyleSheet("color: red;")
        else:
            self.active_hotkey_label.setStyleSheet("color: initial;")
            self.active_hotkey_field.setStyleSheet("color: initial;")

    @Slot()
    def browse_engine_path(self):
        engine_path, _ = QFileDialog.getOpenFileName(self, "Select UCI Engine")
        if len(engine_path) != 0:
            self.engine_path_field.setText(engine_path)
            self.set_engine_path(engine_path)

    def set_all_spinbox_maxima(self):
        self.set_left_spinbox_maximum()
        self.set_top_spinbox_maximum()
        self.set_dimension_spinbox_maxima()

    def set_left_spinbox_maximum(self):
        left_constraint = self.active_screen_width - self.settings.board_rect_manual.width()
        self.left_spinbox.setMaximum(left_constraint)

    def set_top_spinbox_maximum(self):
        top_constraint = self.active_screen_height - self.settings.board_rect_manual.height()
        self.top_spinbox.setMaximum(top_constraint)

    def set_dimension_spinbox_maxima(self):
        width_constraint = self.active_screen_width - self.settings.board_rect_manual.left()
        height_constraint = self.active_screen_height - self.settings.board_rect_manual.top()
        if self.dims_constrained:
            if width_constraint > height_constraint:
                width_constraint = height_constraint
            else:
                height_constraint = width_constraint
        self.width_spinbox.setMaximum(width_constraint)
        self.height_spinbox.setMaximum(height_constraint)

    def set_board_controls_enabled(self, should_enable):
        self.dim_constraint_checkbox.setEnabled(should_enable)
        self.left_spinbox.setEnabled(should_enable)
        self.top_spinbox.setEnabled(should_enable)
        self.width_spinbox.setEnabled(should_enable)
        self.height_spinbox.setEnabled(should_enable)

    @Slot(int)
    def set_board_left(self, x):
        self.unsaved_changes = True
        self.settings.board_rect_manual.moveLeft(x)
        self.updated_manual_rect.emit(self.settings.board_rect_manual)
        self.set_dimension_spinbox_maxima()
        self.draw_board_preview()

    @Slot(int)
    def set_board_top(self, y):
        self.unsaved_changes = True
        self.settings.board_rect_manual.moveTop(y)
        self.updated_manual_rect.emit(self.settings.board_rect_manual)
        self.set_dimension_spinbox_maxima()
        self.draw_board_preview()

    @Slot(int)
    def set_board_width(self, w):
        self.unsaved_changes = True
        self.settings.board_rect_manual.setWidth(w)
        self.updated_manual_rect.emit(self.settings.board_rect_manual)
        self.set_left_spinbox_maximum()
        self.draw_board_preview()

    @Slot(int)
    def set_board_height(self, h):
        self.unsaved_changes = True
        self.settings.board_rect_manual.setHeight(h)
        self.updated_manual_rect.emit(self.settings.board_rect_manual)
        self.set_top_spinbox_maximum()
        self.draw_board_preview()

    @Slot(bool)
    def set_board_autodetect(self, should_autodetect):
        self.unsaved_changes = True
        self.settings.auto_board_detect = should_autodetect
        self.updated_autodetect.emit(should_autodetect)
        self.set_board_controls_enabled(not should_autodetect)
        self.draw_board_preview()

    @Slot(int)
    def set_active_screen(self, selected_screen_index):
        self.unsaved_changes = True
        screen_name = self.screen_names[selected_screen_index]
        if self.settings.active_screen_name != screen_name:
            self.settings.active_screen_name = screen_name
            self.updated_active_screen.emit(screen_name)
            for screen in QGuiApplication.screens():
                if screen.name() == screen_name:
                    active_screen_size = screen.size()
                    self.active_screen_width = active_screen_size.width()
                    self.active_screen_height = active_screen_size.height()
                    self.set_all_spinbox_maxima()
                    break
            self.update_screenshots()
            self.screenshot_timer.start(SettingsWindow.RedrawInterval)

    @Slot(str)
    def set_active_hotkey(self, active_hotkey):
        self.unsaved_changes = True
        self.settings.active_hotkey = active_hotkey
        self.check_active_hotkey()

    @Slot(str)
    def set_engine_path(self, engine_path):
        self.unsaved_changes = True
        self.settings.engine_path = engine_path
        self.check_engine_path()

    @Slot(int)
    def set_engine_process_count(self, n_processes):
        self.unsaved_changes = True
        self.settings.engine_process_count = n_processes

    @Slot()
    def update_screenshots(self):
        screens = QGuiApplication.screens()
        for i, screen in enumerate(screens):
            shot = self.screenshotter.take(screen.name())
            shot = array_to_pixmap(shot)
            self.screen_menu.setItemIcon(i, QIcon(shot))
            if screen.name() == self.settings.active_screen_name:
                self.active_screenshot = shot
        self.draw_board_preview()

    @Slot()
    def save_changes(self):
        self.updated_active_hotkey.emit(self.settings.active_hotkey)
        self.updated_active_screen.emit(self.settings.active_screen_name)
        self.updated_analyzer.emit(
            self.settings.engine_path,
            self.settings.engine_process_count
        )
        self.updated_autodetect.emit(self.settings.auto_board_detect)
        self.updated_manual_rect.emit(self.settings.board_rect_manual)
        self.settings.save()
        self.unsaved_changes = False
