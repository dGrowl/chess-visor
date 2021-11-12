from PySide6.QtWidgets import QApplication

from chess_visor.visor import Visor

if __name__ == "__main__":
    qapp = QApplication()
    with open("./style/gui.qss", 'r', encoding="utf-8") as style_file:
        style = style_file.read()
        qapp.setStyleSheet(style)
    visor = Visor()
    visor.start()
    qapp.exec()
