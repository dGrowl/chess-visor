from dataclasses import dataclass
from itertools import combinations
from os.path import isfile
from queue import SimpleQueue, Empty

from PySide6.QtCore import (
    QObject, QReadLocker, QReadWriteLock,
    QThread, QWriteLocker, Signal, Slot
)
import chess
import chess.engine

@dataclass(eq=True, frozen=True)
class BasicMove:
    from_square: int
    to_square: int
    to_label: str

def moves_have_same_coords(move_a, move_b):
    return (
        move_a.from_square == move_b.from_square and
        move_a.to_square   == move_b.to_square
    )

def game_is_rotated(fen_on_screen, game_board_fen):
    return fen_on_screen != game_board_fen

class AnalysisJob:
    def __init__(self, batch_id, fen_on_screen, game):
        self.batch_id = batch_id
        self.fen_on_screen = fen_on_screen
        self.game = game
        self.move = None

class EngineThread(QThread):
    new_move = Signal(AnalysisJob)

    def __init__(self, analysis_queue, engine_path):
        super().__init__()
        self.analysis_queue = analysis_queue
        self.engine = chess.engine.SimpleEngine.popen_uci(engine_path)
        self.is_alive = True
        self.lock = QReadWriteLock()

    def get_alive(self):
        with QReadLocker(self.lock):
            return self.is_alive

    def set_alive(self, should_be_alive):
        with QWriteLocker(self.lock):
            self.is_alive = should_be_alive

    def run(self):
        while self.get_alive():
            job = None
            try:
                job = self.analysis_queue.get(timeout=2)
            except Empty:
                continue
            game = job.game
            analysis = self.engine.analysis(game, chess.engine.Limit(time=0.5))
            analysis_result = analysis.wait()
            move = analysis_result.move
            if move is not None:
                from_square = move.from_square
                to_square = move.to_square
                dest_tile = move.uci()[2:]
                if game_is_rotated(job.fen_on_screen, game.board_fen()):
                    from_square = 63 - from_square
                    to_square = 63 - to_square
                job.move = BasicMove(from_square, to_square, dest_tile)
                self.new_move.emit(job)
        self.engine.quit()

class Analyzer(QObject):
    updated_moveset = Signal(set)

    def __init__(self, settings):
        super().__init__()
        self.analysis_queue = SimpleQueue()
        self.best_moves = None
        self.engine_path = settings.engine_path
        self.engine_process_count = settings.engine_process_count
        self.is_alive = False
        self.move_batch_id = 0
        self.n_jobs = 0
        self.workers = []

    def start(self):
        if not isfile(self.engine_path):
            return
        if len(self.workers) != 0:
            self.stop()
            self.wait()
        for _ in range(self.engine_process_count):
            worker = EngineThread(self.analysis_queue, self.engine_path)
            worker.new_move.connect(self.job_completed)
            worker.start()
            self.workers.append(worker)

    def stop(self):
        for worker in self.workers:
            worker.set_alive(False)

    def wait(self):
        for worker in self.workers:
            worker.wait()
        self.workers.clear()

    @Slot(str, int)
    def update_settings(self, engine_path, engine_process_count):
        settings_changed = False
        if self.engine_path != engine_path:
            self.engine_path = engine_path
            settings_changed = True
        if self.engine_process_count != engine_process_count:
            self.engine_process_count = engine_process_count
            settings_changed = True
        if settings_changed:
            self.stop()
            self.wait()
            self.start()

    def get_batch_id(self):
        self.move_batch_id += 1
        if self.move_batch_id >= 65536:
            self.move_batch_id = 0
        return self.move_batch_id

    @Slot(BasicMove)
    def job_completed(self, job):
        if job.batch_id != self.move_batch_id:
            return
        self.best_moves.append(job.move)
        if len(self.best_moves) == self.n_jobs:
            unique_moves = set(self.best_moves)
            moves_same_coords = set()
            for move_a, move_b in combinations(unique_moves, 2):
                if moves_have_same_coords(move_a, move_b):
                    merged_move = BasicMove(
                        move_a.from_square,
                        move_b.to_square,
                        f"{move_a.to_label}/{move_b.to_label}"
                    )
                    unique_moves.add(merged_move)
                    moves_same_coords.add(move_a)
                    moves_same_coords.add(move_b)
            self.updated_moveset.emit(unique_moves - moves_same_coords)

    @Slot(list, str)
    def get_best_moves(self, possible_games, fen_on_screen):
        self.n_jobs = len(possible_games)
        if self.n_jobs == 0:
            return
        batch_id = self.get_batch_id()
        self.best_moves = []
        for game in possible_games:
            job = AnalysisJob(batch_id, fen_on_screen, game)
            self.analysis_queue.put(job)
