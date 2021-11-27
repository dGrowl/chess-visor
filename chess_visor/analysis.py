from dataclasses import dataclass
from os.path import isfile
from queue import SimpleQueue, Empty

from PySide6.QtCore import (
    QObject, QReadLocker, QReadWriteLock,
    QThread, QWriteLocker, Signal, Slot
)
import chess
import chess.engine

def game_is_rotated(fen_on_screen, game_board_fen):
    return fen_on_screen != game_board_fen

def convert_square_to_coords(square):
    file_from = chess.square_file(square)
    rank_from = 7 - chess.square_rank(square)
    return file_from, rank_from

def combine_labels(labels):
	return '/'.join(labels)

def transform_move(move, is_game_rotated):
    square_from = move.from_square
    square_to = move.to_square
    label = move.uci()[2:]
    if is_game_rotated:
        square_from = 63 - square_from
        square_to = 63 - square_to
    return ((square_from, square_to), label)

@dataclass
class AnalysisJob:
    batch_id: int
    game: chess.Board
    is_game_rotated: bool
    move: tuple[tuple, str] = None

class EngineThread(QThread):
    new_move = Signal(AnalysisJob)

    AnalysisTimeLimit = chess.engine.Limit(time=0.5)

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
            analysis = self.engine.analysis(game, EngineThread.AnalysisTimeLimit)
            analysis_result = analysis.wait()
            move = analysis_result.move
            if move is not None:
                job.move = transform_move(move, job.is_game_rotated)
                self.new_move.emit(job)
        self.engine.quit()

class Analyzer(QObject):
    updated_moveset = Signal(list)

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

    @Slot(AnalysisJob)
    def job_completed(self, job):
        if job.batch_id != self.move_batch_id:
            return
        self.n_completed_jobs += 1
        squares, label = job.move
        if seen_move_labels := self.best_moves.get(squares):
            if label not in seen_move_labels:
                seen_move_labels.append(label)
        else:
            self.best_moves[squares] = [label]
        if self.n_completed_jobs == self.n_jobs:
            moves = []
            for squares, labels in self.best_moves.items():
                square_from, square_to = squares
                file_from, rank_from = convert_square_to_coords(square_from)
                file_to, rank_to = convert_square_to_coords(square_to)
                moves.append((
                    file_from, rank_from,
                    file_to, rank_to,
                    combine_labels(labels)
                ))
            self.updated_moveset.emit(moves)

    @Slot(list, str)
    def get_best_moves(self, possible_games, fen_on_screen):
        self.n_jobs = len(possible_games)
        if self.n_jobs == 0:
            return
        batch_id = self.get_batch_id()
        self.n_completed_jobs = 0
        self.best_moves = dict()
        for game in possible_games:
            job = AnalysisJob(
                batch_id,
                game,
                game_is_rotated(fen_on_screen, game.board_fen())
            )
            self.analysis_queue.put(job)
