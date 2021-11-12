from itertools import product

from PySide6.QtCore import QObject, Signal, Slot
import chess
import numpy as np

STARTING_POSITION = np.array([
    ['r', 'n', 'b', 'q', 'k', 'b', 'n', 'r'],
    ['p', 'p', 'p', 'p', 'p', 'p', 'p', 'p'],
    [' ', ' ', ' ', ' ', ' ', ' ', ' ', ' '],
    [' ', ' ', ' ', ' ', ' ', ' ', ' ', ' '],
    [' ', ' ', ' ', ' ', ' ', ' ', ' ', ' '],
    [' ', ' ', ' ', ' ', ' ', ' ', ' ', ' '],
    ['P', 'P', 'P', 'P', 'P', 'P', 'P', 'P'],
    ['R', 'N', 'B', 'Q', 'K', 'B', 'N', 'R']
])

def flip_position(position):
    return np.rot90(position, k=2)

def is_starting_position(position, is_flipped=False):
    if is_flipped:
        position = flip_position(position)
    return np.array_equal(position, STARTING_POSITION)

def position_to_board_fen(position):
    fen = ""
    empty_count = 0
    for rank in range(position.shape[0]):
        for tile in position[rank]:
            if tile == ' ':
                empty_count += 1
            else:
                if empty_count != 0:
                    fen += str(empty_count)
                    empty_count = 0
                fen += tile
        if empty_count != 0:
            fen += str(empty_count)
            empty_count = 0
        if rank < 7:
            fen += '/'
    return fen

def transform_castling(castling):
    castling = ''.join(castling)
    if len(castling) == 0:
        castling = '-'
    return castling

def is_white_piece(piece):
    return piece.isupper()

def is_empty_tile(tile):
    return tile == ' '

class GameState(QObject):
    updated_possible_games = Signal(list, str)

    def __init__(self):
        super().__init__()

        self.best_moves = set()
        self.position = None

        self.reset_assumptions()

    @Slot()
    def reset_assumptions(self):
        self.active_color = ['w', 'b']
        self.en_passant = ['-']
        self.i_halfmoves = ['0']
        self.i_fullmoves = ['1']
        self.white_king_castle = ['', 'K']
        self.white_queen_castle = ['', 'Q']
        self.black_king_castle = ['', 'k']
        self.black_queen_castle = ['', 'q']
        self.could_be_flipped = True
        self.could_be_unflipped = True
        self.last_move = None
        self.vacated_coords = None

    def make_starting_assumptions(self, is_flipped=False):
        self.active_color = ['w']
        self.en_passant = ['-']
        self.i_halfmoves = ['0']
        self.i_fullmoves = ['1']
        self.white_king_castle = ['K']
        self.white_queen_castle = ['Q']
        self.black_king_castle = ['k']
        self.black_queen_castle = ['q']
        self.could_be_flipped = is_flipped
        self.could_be_unflipped = not is_flipped
        self.last_move = None
        self.vacated_coords = None

    def assume_flipped(self, believe_flipped):
        if believe_flipped:
            if not self.could_be_flipped:
                self.reset_assumptions()
            else:
                self.could_be_unflipped = False
                self.could_be_flipped = True
        else:
            if not self.could_be_flipped:
                self.reset_assumptions()
            else:
                self.could_be_unflipped = True
                self.could_be_flipped = False

    def build_possible_games(self):
        if self.position is None:
            return []
        base_fen = [position_to_board_fen(self.position)]
        possible_castling = product(
            self.white_king_castle,
            self.white_queen_castle,
            self.black_king_castle,
            self.black_queen_castle
        )
        possible_castling = map(
            transform_castling,
            possible_castling
        )
        possible_fens = product(
            base_fen,
            self.active_color,
            possible_castling,
            self.en_passant,
            self.i_halfmoves,
            self.i_fullmoves
        )
        possible_fens = list(map(
            lambda f: ' '.join(f),
            possible_fens
        ))
        possible_games = []
        for fen in possible_fens:
            board = None
            try:
                board = chess.Board(fen)
            except:
                continue
            if self.could_be_unflipped:
                if board.is_valid():
                    possible_games.append(board)
            if self.could_be_flipped:
                board_flipped = board.transform(chess.flip_horizontal)
                board_flipped.apply_transform(chess.flip_vertical)
                if board_flipped.is_valid():
                    possible_games.append(board_flipped)
        return possible_games

    def get_board_fen(self):
        return position_to_board_fen(self.position)

    def check_castling(self):
        if len(self.white_king_castle) > 1 or len(self.white_queen_castle) > 1:
            white_king_moved = True
            white_rook_kingside_moved = True
            white_rook_queenside_moved = True
            if self.could_be_unflipped:
                white_king_moved &= (self.position[7, 4] != 'K')
                white_rook_kingside_moved &= (self.position[7, 7] != 'R')
                white_rook_queenside_moved &= (self.position[7, 0] != 'R')
            if self.could_be_flipped:
                white_king_moved &= (self.position[0, 3] != 'K')
                white_rook_kingside_moved &= (self.position[0, 0] != 'R')
                white_rook_queenside_moved &= (self.position[0, 7] != 'R')
            if white_king_moved:
                self.white_king_castle = ['']
                self.white_queen_castle = ['']
            elif white_rook_kingside_moved:
                self.white_king_castle = ['']
            elif white_rook_queenside_moved:
                self.white_queen_castle = ['']
        if len(self.black_king_castle) > 1 or len(self.black_queen_castle) > 1:
            black_king_moved = True
            black_rook_kingside_moved = True
            black_rook_queenside_moved = True
            if self.could_be_unflipped:
                black_king_moved &= (self.position[0, 4] != 'k')
                black_rook_kingside_moved &= (self.position[0, 7] != 'r')
                black_rook_queenside_moved &= (self.position[0, 0] != 'r')
            if self.could_be_flipped:
                black_king_moved &= (self.position[7, 3] != 'k')
                black_rook_kingside_moved &= (self.position[7, 0] != 'r')
                black_rook_queenside_moved &= (self.position[7, 7] != 'r')
            if black_king_moved:
                self.black_king_castle = ['']
                self.black_queen_castle = ['']
            elif black_rook_kingside_moved:
                self.black_king_castle = ['']
            elif black_rook_queenside_moved:
                self.black_queen_castle = ['']

    def check_en_passant(self):
        possible_ep_captures = ['-']
        if self.last_move is not None:
            moved_piece = self.position[self.last_move]
            i, j = self.last_move
            if moved_piece == 'p':
                if self.could_be_unflipped and i == 3:
                    file = chess.FILE_NAMES[j]
                    possible_ep_captures.append(f"{file}6")
                if self.could_be_flipped and i == 4:
                    file = chess.FILE_NAMES[7 - j]
                    possible_ep_captures.append(f"{file}6")
            elif moved_piece == 'P':
                if self.could_be_unflipped and i == 4:
                    file = chess.FILE_NAMES[j]
                    possible_ep_captures.append(f"{file}3")
                if self.could_be_flipped and i == 3:
                    file = chess.FILE_NAMES[7 - j]
                    possible_ep_captures.append(f"{file}3")
        else:
            for j in range(7):
                advancer = self.position[3, j]
                if advancer == 'p' and self.could_be_unflipped:
                    file = chess.FILE_NAMES[j]
                    possible_ep_captures.append(f"{file}6")
                if advancer == 'P' and self.could_be_flipped:
                    file = chess.FILE_NAMES[7 - j]
                    possible_ep_captures.append(f"{file}3")
                advancer = self.position[4, j]
                if advancer == 'P' and self.could_be_unflipped:
                    file = chess.FILE_NAMES[j]
                    possible_ep_captures.append(f"{file}3")
                if advancer == 'p' and self.could_be_flipped:
                    file = chess.FILE_NAMES[7 - j]
                    possible_ep_captures.append(f"{file}6")
        self.en_passant = possible_ep_captures

    def check_continuation(self, position):
        if self.position is None:
            return False
        change_mask = (position != self.position)
        change_indices = np.argwhere(change_mask)
        n_changes = change_indices.shape[0]
        if n_changes > 2:
            self.vacated_coords = None
            return False
        if n_changes == 1:
            updated_coords = tuple(change_indices[0])
            updated_piece = position[updated_coords]
            self.last_move = updated_coords
            if is_empty_tile(updated_piece):
                self.vacated_coords = updated_coords
                old_piece = self.position[updated_coords]
                self.active_color = ['b'] if is_white_piece(old_piece) else ['w']
            else:
                self.active_color = ['b'] if is_white_piece(updated_piece) else ['w']
                if self.vacated_coords is not None:
                    if updated_piece == 'p':
                        if updated_coords[0] > self.vacated_coords[0]:
                            self.assume_flipped(False)
                        else:
                            self.assume_flipped(True)
                    elif updated_piece == 'P':
                        if updated_coords[0] > self.vacated_coords[0]:
                            self.assume_flipped(True)
                        else:
                            self.assume_flipped(False)
                    self.vacated_coords = None
            return True
        self.vacated_coords = None
        new_tiles = position[change_mask]
        if new_tiles[0] == ' ':
            moved_from_coords = tuple(change_indices[0])
            moved_piece = self.position[moved_from_coords]
            if new_tiles[1] == moved_piece:
                self.last_move = tuple(change_indices[1])
                self.active_color = ['b'] if is_white_piece(moved_piece) else ['w']
                if moved_piece == 'p':
                    if self.last_move[0] > moved_from_coords[0]:
                        self.assume_flipped(False)
                    else:
                        self.assume_flipped(True)
                elif moved_piece == 'P':
                    if self.last_move[0] > moved_from_coords[0]:
                        self.assume_flipped(True)
                    else:
                        self.assume_flipped(False)
                return True
        elif new_tiles[1] == ' ':
            moved_from_coords = tuple(change_indices[1])
            moved_piece = self.position[moved_from_coords]
            if new_tiles[0] == moved_piece:
                self.last_move = tuple(change_indices[0])
                self.active_color = ['b'] if is_white_piece(moved_piece) else ['w']
                if moved_piece == 'p':
                    if self.last_move[0] > moved_from_coords[0]:
                        self.assume_flipped(False)
                    else:
                        self.assume_flipped(True)
                elif moved_piece == 'P':
                    if self.last_move[0] > moved_from_coords[0]:
                        self.assume_flipped(True)
                    else:
                        self.assume_flipped(False)
                return True
        return False

    def is_position_different(self, position):
        return not np.array_equal(self.position, position)

    @Slot(np.ndarray)
    def set_position(self, position):
        if not self.is_position_different(position):
            return
        if is_starting_position(position):
            self.make_starting_assumptions()
        elif is_starting_position(flip_position(position)):
            self.make_starting_assumptions(True)
        elif not self.check_continuation(position):
            self.reset_assumptions()
        self.position = position
        self.update_possible_games()

    def update_possible_games(self):
        self.check_castling()
        self.check_en_passant()
        possible_games = self.build_possible_games()
        self.updated_possible_games.emit(possible_games, self.get_board_fen())
