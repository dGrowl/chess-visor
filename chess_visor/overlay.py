from dataclasses import dataclass

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
from .game_state import is_white_piece

@dataclass
class OverlayMove:
    x_from: int
    y_from: int
    x_to: int
    y_to: int
    color: bool
    to_label: str

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
        self.tile_labels = None
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

    def clear(self):
        self.scene.clear()

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
    def set_tile_labels(self, tile_labels):
        if not np.array_equal(tile_labels, self.tile_labels):
            self.tile_labels = tile_labels
            self.latest_moves = None
            self.clear()

    def add_move(self, move):
        self.add_line(move)
        self.add_label(move)

    def add_source_circle(self, coords, color):
        circle = self.scene.addEllipse(
            coords[0] - 5 + self.screen_rect.x(),
            coords[1] - 5 + self.screen_rect.y(),
            10, 10,
            Overlay.GrayPenThin
        )
        circle.setZValue(0)
        if color == chess.WHITE:
            circle.setBrush(Overlay.WhiteBrush)
        else:
            circle.setBrush(Overlay.BlackBrush)

    def add_line(self, move):
        line = QLineF(
            move.x_from + self.screen_rect.x(),
            move.y_from + self.screen_rect.y(),
            move.x_to + self.screen_rect.x(),
            move.y_to + self.screen_rect.y()
        )
        line_bg_graphic = self.scene.addLine(line, pen=Overlay.GrayPenThick)
        line_bg_graphic.setZValue(-2)
        line_fg_graphic = self.scene.addLine(line)
        line_fg_graphic.setZValue(-1)
        if move.color == chess.WHITE:
            line_fg_graphic.setPen(Overlay.WhitePen)
        else:
            line_fg_graphic.setPen(Overlay.BlackPen)

    def add_label(self, move):
        label = self.scene.addSimpleText(move.to_label, font=self.label_font)
        label_rect = label.boundingRect()
        label_offset_x = label_rect.width() / 2
        label_offset_y = label_rect.height() / 2
        label_x = move.x_to - label_offset_x + self.screen_rect.x()
        label_y = move.y_to - label_offset_y + self.screen_rect.y()
        label_w = label_rect.width() + 6
        label_h = label_rect.height() + 2
        label.setZValue(2)
        label.setPos(label_x, label_y)

        rect = QRectF(
            move.x_to - label_w / 2 + self.screen_rect.x(),
            move.y_to - label_h / 2 + self.screen_rect.y(),
            label_w, label_h
        )
        rect_graphic = self.scene.addRect(rect)
        rect_graphic.setPen(Overlay.GrayPenThin)
        rect_graphic.setZValue(1)

        if move.color == chess.WHITE:
            label.setBrush(Overlay.BlackBrush)
            rect_graphic.setBrush(Overlay.WhiteBrush)
        else:
            label.setBrush(Overlay.WhiteBrush)
            rect_graphic.setBrush(Overlay.BlackBrush)

    @Slot(set)
    def set_moves(self, moves):
        self.latest_moves = moves
        self.map_moves_to_board()

    def map_moves_to_board(self):
        if self.board_rect is None or self.latest_moves is None:
            return
        mapped_moves = []
        x_board = self.board_rect.left()
        y_board = self.board_rect.top()
        tile_w = self.board_rect.width() / 8
        tile_h = self.board_rect.height() / 8
        half_tile_w = tile_w / 2
        half_tile_h = tile_h / 2
        for move in self.latest_moves:
            file_from = chess.square_file(move.from_square)
            rank_from = 7 - chess.square_rank(move.from_square)
            file_to = chess.square_file(move.to_square)
            rank_to = 7 - chess.square_rank(move.to_square)
            x_from = x_board + file_from * tile_w + half_tile_w
            y_from = y_board + rank_from * tile_h + half_tile_h
            x_to = x_board + file_to * tile_w + half_tile_w
            y_to = y_board + rank_to * tile_h + half_tile_h
            if self.coordinate_modifier != 1:
                x_from *= self.coordinate_modifier
                y_from *= self.coordinate_modifier
                x_to *= self.coordinate_modifier
                y_to *= self.coordinate_modifier
            piece = self.tile_labels[rank_from, file_from]
            color = chess.WHITE if is_white_piece(piece) else chess.BLACK
            mapped_moves.append(OverlayMove(x_from, y_from, x_to, y_to, color, move.to_label))
        self.add_moves(mapped_moves)

    def add_moves(self, moves):
        self.clear()
        overlaps = dict()
        source_squares = set()
        angle_indices = dict()
        for move in moves:
            from_coords = (move.x_from, move.y_from)
            to_coords = (move.x_to, move.y_to)

            increment_key(overlaps, to_coords)
            source_squares.add(from_coords)
            self.add_source_circle(from_coords, move.color)

        for move in moves:
            to_coords = (move.x_to, move.y_to)

            n_to_overlaps = overlaps.get(to_coords, 0)
            if to_coords in source_squares:
                n_to_overlaps += 1

            if n_to_overlaps > 1:
                angles = np.linspace(
                    0,
                    2 * np.pi,
                    num=n_to_overlaps,
                    endpoint=False
                )
                if to_coords not in angle_indices:
                    angle_indices[to_coords] = 0
                i = angle_indices[to_coords]
                angle_indices[to_coords] += 1
                to_coords = (
                    to_coords[0] + 20 * np.cos(angles[i]),
                    to_coords[1] + 20 * np.sin(angles[i])
                )
            shifted_move = OverlayMove(
                move.x_from,
                move.y_from,
                to_coords[0],
                to_coords[1],
                move.color,
                move.to_label
            )
            self.add_move(shifted_move)
