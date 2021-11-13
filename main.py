from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QApplication

from chess_visor.visor import Visor

if __name__ == "__main__":
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling)
    QGuiApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.Round
    )
    qapp = QApplication()
    with open("./style/gui.qss", 'r', encoding="utf-8") as style_file:
        style = style_file.read()
        qapp.setStyleSheet(style)
    visor = Visor()
    visor.start()
    qapp.exec()
