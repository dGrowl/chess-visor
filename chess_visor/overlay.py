from PySide6.QtCore import QLineF, QRect, QRectF, Qt, Slot
from PySide6.QtGui import (
    QBrush, QColor, QFont, QFontDatabase,
    QGuiApplication, QPainter, QPen
)
from PySide6.QtWidgets import (
    QGraphicsScene, QGraphicsView, QMainWindow
)
import chess
import numpy as np

from .utility import increment_key

class Overlay(QMainWindow):
    Black = QColor(48, 48, 48)
    Gray = QColor(128, 128, 128)
    White = QColor(255, 255, 255)
    BlackBrush = QBrush(Black)
    BlackPen = QPen(Black, 3)
    GrayPenThick = QPen(Gray, 4)
    GrayPenThin = QPen(Gray, 1)
    WhiteBrush = QBrush(White)
    WhitePen = QPen(White, 3)

    def __init__(self, settings):
        QMainWindow.__init__(self)

        self.board_rect = settings.board_rect_manual
        self.is_active = True
        self.latest_moves = None
        self.scene = None
        self.set_active_screen(settings.active_screen_name)

        self.init_window()
        self.init_fonts()
        self.init_scene()

    def init_window(self):
        self.setWindowFlags(
            Qt.WindowTransparentForInput |
            Qt.WindowStaysOnTopHint |
            Qt.FramelessWindowHint |
            Qt.X11BypassWindowManagerHint |
            Qt.ToolTip |
            Qt.NoDropShadowWindowHint
        )
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WA_QuitOnClose)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAutoFillBackground(True)

    def init_fonts(self):
        font_id = QFontDatabase.addApplicationFont("fonts/selawik-semibold.ttf")
        font_families = QFontDatabase.applicationFontFamilies(font_id)
        self.label_font = QFont(font_families, 11)

    def init_scene(self):
        self.scene = QGraphicsScene(self)
        self.scene.setSceneRect(self.screen_rect)

        self.view = QGraphicsView(self.scene)
        self.view.setAttribute(Qt.WA_DeleteOnClose)
        self.view.setRenderHints(
            QPainter.Antialiasing |
            QPainter.TextAntialiasing |
            QPainter.SmoothPixmapTransform
        )
        self.view.setEnabled(False)
        self.view.setDragMode(QGraphicsView.NoDrag)
        self.view.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.view.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setCentralWidget(self.view)

    def set_hidden(self, should_be_hidden):
        if self.is_active:
            if should_be_hidden:
                self.setWindowOpacity(0)
            else:
                self.setWindowOpacity(1)

    def set_active(self, should_be_active):
        self.is_active = should_be_active
        self.set_hidden(not should_be_active)
        if should_be_active:
            self.setWindowOpacity(1)
        else:
            self.setWindowOpacity(0)

    @Slot(str)
    def set_active_screen(self, screen_name):
        active_screen = QGuiApplication.primaryScreen()
        for screen in QGuiApplication.screens():
            if screen.name() == screen_name:
                active_screen = screen
                break
        self.screen_rect = active_screen.availableGeometry()
        self.coordinate_modifier = 1 / active_screen.devicePixelRatio()
        self.setGeometry(self.screen_rect)
        if self.scene is not None:
            self.scene.setSceneRect(self.screen_rect)
        self.map_moves_to_board()

    @Slot(QRect)
    def set_board_rect(self, board_rect):
        self.board_rect = board_rect
        self.map_moves_to_board()

    @Slot(np.ndarray)
    def clear(self, _=None):
        self.scene.clear()

    def add_move(self, x_from, y_from, x_to, y_to, label, color):
        self.add_line(x_from, y_from, x_to, y_to, color)
        self.add_label(x_to, y_to, label, color)

    def add_source_circle(self, x, y, color):
        circle = self.scene.addEllipse(
            x - 5, y - 5,
            10, 10,
            Overlay.GrayPenThin
        )
        circle.setZValue(0)
        if color == chess.WHITE:
            circle.setBrush(Overlay.WhiteBrush)
        else:
            circle.setBrush(Overlay.BlackBrush)

    def add_line(self, x_from, y_from, x_to, y_to, color):
        line = QLineF(x_from, y_from, x_to, y_to)
        line_bg_graphic = self.scene.addLine(line, pen=Overlay.GrayPenThick)
        line_bg_graphic.setZValue(-2)
        line_fg_graphic = self.scene.addLine(line)
        line_fg_graphic.setZValue(-1)
        if color == chess.WHITE:
            line_fg_graphic.setPen(Overlay.WhitePen)
        else:
            line_fg_graphic.setPen(Overlay.BlackPen)

    def add_label(self, x_to, y_to, label, color):
        label_graphic = self.scene.addSimpleText(label, font=self.label_font)
        label_rect = label_graphic.boundingRect()
        label_offset_x = label_rect.width() / 2
        label_offset_y = label_rect.height() / 2
        label_x = x_to - label_offset_x
        label_y = y_to - label_offset_y
        label_w = label_rect.width() + 6
        label_h = label_rect.height() + 2
        label_graphic.setZValue(2)
        label_graphic.setPos(label_x, label_y)

        rect = QRectF(
            x_to - label_w / 2,
            y_to - label_h / 2,
            label_w, label_h
        )
        rect_graphic = self.scene.addRect(rect)
        rect_graphic.setPen(Overlay.GrayPenThin)
        rect_graphic.setZValue(1)

        if color == chess.WHITE:
            label_graphic.setBrush(Overlay.BlackBrush)
            rect_graphic.setBrush(Overlay.WhiteBrush)
        else:
            label_graphic.setBrush(Overlay.WhiteBrush)
            rect_graphic.setBrush(Overlay.BlackBrush)

    @Slot(list)
    def set_moves(self, moves):
        self.latest_moves = moves
        self.map_moves_to_board()

    def map_moves_to_board(self):
        if self.board_rect is None or self.latest_moves is None:
            return
        mapped_moves = []
        x_board = self.screen_rect.x() + self.board_rect.x()
        y_board = self.screen_rect.y() + self.board_rect.y()
        tile_w = self.board_rect.width() / 8
        tile_h = self.board_rect.height() / 8
        half_tile_w = tile_w / 2
        half_tile_h = tile_h / 2
        for move in self.latest_moves:
            x_from = x_board + move.j_from * tile_w + half_tile_w
            y_from = y_board + move.i_from * tile_h + half_tile_h
            x_to = x_board + move.j_to * tile_w + half_tile_w
            y_to = y_board + move.i_to * tile_h + half_tile_h
            if self.coordinate_modifier != 1:
                x_from *= self.coordinate_modifier
                y_from *= self.coordinate_modifier
                x_to *= self.coordinate_modifier
                y_to *= self.coordinate_modifier
            mapped_moves.append((
                x_from,
                y_from,
                x_to,
                y_to,
                move.label,
                move.color
            ))
        self.add_moves(mapped_moves)

    def add_moves(self, moves):
        self.clear()
        overlaps = dict()
        from_squares = set()
        angle_indices = dict()
        for x_from, y_from, x_to, y_to, _, color in moves:
            xy_from = (x_from, y_from)
            xy_to = (x_to, y_to)

            increment_key(overlaps, xy_to)
            if xy_from not in from_squares:
                from_squares.add(xy_from)
                self.add_source_circle(x_from, y_from, color)

        for x_from, y_from, x_to, y_to, label, color in moves:
            xy_to = (x_to, y_to)

            n_to_overlaps = overlaps.get(xy_to, 0)
            if xy_to in from_squares:
                n_to_overlaps += 1

            if n_to_overlaps > 1:
                angles = np.linspace(
                    -np.pi / 8, -2 * np.pi,
                    num=n_to_overlaps,
                    endpoint=False
                )
                i = angle_indices.setdefault(xy_to, 0)
                angle_indices[xy_to] += 1
                x_to += 27 * np.cos(angles[i])
                y_to += 27 * np.sin(angles[i])
            self.add_move(x_from, y_from, x_to, y_to, label, color)
