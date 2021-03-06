from os import environ
from random import choice, random, randrange, sample
environ["TF_CPP_MIN_LOG_LEVEL"] = '3'

from chess import FILE_NAMES, RANK_NAMES
from PIL import Image, ImageColor, ImageDraw, ImageFont, ImageOps
from skimage.transform import resize
from tensorflow.keras import Sequential
from tensorflow.keras.layers import Conv2D, Dense, Dropout, Flatten, MaxPool2D
from tensorflow.keras.layers.experimental.preprocessing import Normalization
from tensorflow.keras.models import load_model
from tensorflow.keras.regularizers import l2
from tensorflow.keras.utils import to_categorical
from tensorflow.keras.optimizers import Adam
import numpy as np
import pytomlpp as toml
import tensorflow as tf

from .utility import is_even, increment_key

TILE_LABELS = np.array([
    ' ',
    'p', 'n', 'b', 'r', 'q', 'k',
    'P', 'N', 'B', 'R', 'Q', 'K'
])
TILE_PATHS = np.array([
    "",
    "pawn/b", "knight/b", "bishop/b", "rook/b", "queen/b", "king/b",
    "pawn/w", "knight/w", "bishop/w", "rook/w", "queen/w", "king/w"
])
TILE_FONT = ImageFont.truetype("./fonts/selawik-semibold.ttf", 25)
MOVE_FONT = ImageFont.truetype("./fonts/selawik-semibold.ttf", 11)
WHITE = (255, 255, 255)
BLACK = (48, 48, 48)
GRAY = (128, 128, 128)

def make_decision(p):
    assert p >= 0. and p <= 1.
    return random() < p

def generate_background_color():
    should_be_dark = make_decision(0.5)
    h = randrange(0, 360)
    s = randrange(0, 101)
    l = randrange(0, 31) if should_be_dark else randrange(70, 101)
    return ImageColor.getrgb(f"hsl({h},{s}%,{l}%)")

def invert_color(c):
    return (
        255 - c[0],
        255 - c[1],
        255 - c[2]
    )

def is_white_label(label):
    return label > 6

def get_color(label):
    if label == 0:
        return None
    return WHITE if is_white_label(label) else BLACK

def generate_checkerboard(size):
    color_light = generate_background_color()
    color_dark  = invert_color(color_light)
    if sum(color_light) < sum(color_dark):
        color_light, color_dark = color_dark, color_light
    board_image = Image.new("RGBA", (size, size), color=color_dark)
    tile_size = size // 8
    draw = ImageDraw.Draw(board_image)
    for x in range(0, size, size // 4):
        for y in range(0, size, size // 4):
            rectangle = [
                (x, y),
                (x + tile_size - 1, y + tile_size - 1)
            ]
            draw.rectangle(rectangle, fill=color_light)
            rectangle = [
                (x + tile_size, y + tile_size),
                (x + tile_size * 2 - 1, y + tile_size * 2 - 1),
            ]
            draw.rectangle(rectangle, fill=color_light)
    return board_image

def add_text_to_board(board):
    light_color = board.getpixel((0, 0))
    dark_color  = board.getpixel((100, 0))
    draw = ImageDraw.Draw(board)
    corner_offsets = [[37, 34], [-37, 34], [-37, -34], [37, -34]]
    tile_centers = np.mgrid[50:800:100,50:800:100]
    for i in range(8):
        for j in range(8):
            xy = tile_centers[:, i, j]
            text_color = dark_color if is_even(i + j) else light_color
            corners = np.array(sample(corner_offsets, 2))
            should_have_rank_text = make_decision(.125)
            if should_have_rank_text:
                draw.text(
                    xy + corners[0],
                    choice(RANK_NAMES),
                    fill=text_color,
                    font=TILE_FONT,
                    anchor="mm"
                )
            should_have_file_text = make_decision(.125)
            if should_have_file_text:
                draw.text(
                    xy + corners[1],
                    choice(FILE_NAMES),
                    fill=text_color,
                    font=TILE_FONT,
                    anchor="mm"
                )

class ImageCache:
    Data = dict()

    @staticmethod
    def load(path):
        if path in ImageCache.Data:
            return ImageCache.Data[path]
        image = Image.open(path)
        ImageCache.Data[path] = image
        return image

    @staticmethod
    def clear():
        ImageCache.Data.clear()

def load_piece(image_path):
    piece_size = randrange(90, 98)
    piece_offset = (100 - piece_size) // 2
    piece_image = ImageCache.load(image_path)
    piece_image = piece_image.resize(
        (piece_size, piece_size),
        resample=Image.LANCZOS
    )
    should_mirror_piece = make_decision(.25)
    if should_mirror_piece:
        piece_image = ImageOps.mirror(piece_image)
    piece_image_alpha = Image.new("RGBA", (100, 100))
    piece_image_alpha.paste(piece_image, (piece_offset, piece_offset))
    return piece_image_alpha

def add_pieces_to_board(board, allowed_versions):
    labels = np.random.randint(-4, len(TILE_LABELS), size=(8, 8))
    labels[labels < 0] = 0
    versions = np.random.choice(allowed_versions, size=(8, 8))
    for i in range(8):
        y = i * 100 + 3
        for j in range(8):
            label = labels[i, j]
            if label == 0:
                continue
            piece_path = TILE_PATHS[label]
            piece_id = TILE_LABELS[label].lower()
            version = versions[i, j]
            piece_image_path = f"./tile_classifier/training/{piece_path}{piece_id}-{version}.png"
            piece_image = load_piece(piece_image_path)
            x = j * 100
            board.alpha_composite(piece_image, (x, y))
    return labels

def draw_move_line(draw, xy_from, xy_to, color):
    draw.line(
        (xy_from[0], xy_from[1], xy_to[0], xy_to[1]),
        width=4,
        fill=GRAY
    )
    draw.line(
        (xy_from[0], xy_from[1], xy_to[0], xy_to[1]),
        width=3,
        fill=color
    )

def draw_move_circle(draw, xy, color):
    draw.ellipse(
        (xy[0] - 5, xy[1] - 5, xy[0] + 5, xy[1] + 5),
        outline=GRAY,
        fill=color
    )

def generate_move_text():
    should_be_long = make_decision(.2)
    rank = randrange(8)
    file = randrange(8)
    text = f"{FILE_NAMES[file]}{RANK_NAMES[rank]}"
    if should_be_long:
        text += f"/{FILE_NAMES[7 - file]}{RANK_NAMES[7 - rank]}"
    return text

def draw_move_text(draw, xy, text_color, background_color):
    text = generate_move_text()
    font_box = np.array(MOVE_FONT.getbbox(text))
    text_width = (font_box[2] - font_box[0] + 8) / 2
    text_height = (font_box[3] - font_box[1] + 8) / 2
    draw.rectangle(
        (
            xy[0] - text_width,
            xy[1] - text_height,
            xy[0] + text_width,
            xy[1] + text_height
        ),
        outline=GRAY,
        fill=background_color
    )
    draw.text(
        xy, text,
        fill=text_color,
        font=MOVE_FONT,
        anchor="mm"
    )

def resize_board(board):
    new_board_size = randrange(450, 951)
    board_resized = board.resize(
        (new_board_size, new_board_size),
        resample=Image.LANCZOS
    )
    return board_resized

def get_random_indices():
    return randrange(8), randrange(8)

def get_from_indices(tile_labels):
    i_from, j_from = get_random_indices()
    while tile_labels[i_from, j_from] == 0:
        i_from, j_from = get_random_indices()

def get_to_indices(tile_labels, color):
    i_to, j_to = get_random_indices()
    while get_color(tile_labels[i_to, j_to]) == color:
        i_to, j_to = get_random_indices()

def add_moves_to_board(board, tile_labels):
    n_moves = 32
    board_size = board.size[0]
    tile_size = board_size / 8
    half_tile_size = tile_size / 2
    moves = []
    from_squares = set()
    to_overlaps = dict()
    angle_indices = dict()
    for _ in range(n_moves):
        i_from, j_from = get_from_indices(tile_labels)
        from_color = get_color(tile_labels[i_from, j_from])
        i_to, j_to = get_to_indices(tile_labels, from_color)
        xy_from = (
            int(j_from * tile_size + half_tile_size),
            int(i_from * tile_size + half_tile_size)
        )
        xy_to = (
            int(j_to * tile_size + half_tile_size),
            int(i_to * tile_size + half_tile_size)
        )
        from_squares.add(xy_from)
        increment_key(to_overlaps, xy_to)
        moves.append((xy_from, xy_to, from_color))
    draw = ImageDraw.Draw(board)
    text_graphics = []
    for xy_from, xy_to, color in moves:
        n_to_overlaps = to_overlaps.get(xy_to, 0)
        if xy_to in from_squares:
            n_to_overlaps += 1
        if n_to_overlaps > 1:
            angles = np.linspace(
                0, 2 * np.pi,
                num=n_to_overlaps,
                endpoint=False
            )
            i = angle_indices.setdefault(xy_to, 0)
            angle_indices[xy_to] += 1
            xy_to = (
                xy_to[0] + 20 * np.cos(angles[i]),
                xy_to[1] + 20 * np.sin(angles[i])
            )
        inverted_color = WHITE if color is BLACK else BLACK
        draw_move_line(draw, xy_from, xy_to, color)
        draw_move_circle(draw, xy_from, color)
        text_graphics.append((xy_to, inverted_color, color))
    for xy, text_color, background_color in text_graphics:
        draw_move_text(draw, xy, text_color, background_color)

def extract_tiles_from_synthetic_board(board):
    board_size = board.size[0]
    tile_size = board_size // 8
    padding = 3
    padded_board = board.convert('L')
    padded_board = ImageOps.expand(padded_board, border=padding)
    tiles = np.zeros((64, 40, 40))
    i = 0
    tile_marks = np.linspace(padding, board_size + padding, 8, endpoint=False)
    for y in tile_marks:
        for x in tile_marks:
            x += randrange(-padding, padding + 1)
            y += randrange(-padding, padding + 1)
            tile = padded_board.crop((x, y, x + tile_size, y + tile_size))
            tile = np.array(tile)
            tile = resize(tile, (40, 40), anti_aliasing=True)
            tiles[i] = tile
            i += 1
    tiles = np.expand_dims(tiles, -1)
    return tiles

def extract_tiles_from_screenshot(screenshot, board_rect):
    tiles = np.zeros((64, 40, 40))
    tile_h = board_rect.height() / 8
    tile_w = board_rect.width() / 8
    for i in range(8):
        top = int(board_rect.top() + tile_h * i)
        bottom = int(top + tile_h)
        for j in range(8):
            left = int(board_rect.left() + tile_w * j)
            right = int(left + tile_w)
            tile = screenshot[top:bottom, left:right]
            tile = resize(tile, (40, 40), anti_aliasing=True)
            tiles[8 * i + j] = tile
    tiles = np.expand_dims(tiles, -1)
    return tiles

def generate_64_tiles(allowed_piece_versions):
    board = generate_checkerboard(800)
    add_text_to_board(board)
    board_labels = add_pieces_to_board(board, allowed_piece_versions)
    board = resize_board(board)
    add_moves_to_board(board, board_labels)
    tiles = extract_tiles_from_synthetic_board(board)
    labels = board_labels.reshape(64)
    return tiles, labels

def generate_synthetic_batches(n, allowed_piece_versions):
    X, Y = np.zeros((64 * n, 40, 40, 1)), np.zeros((64 * n))
    for i in range(n):
        tiles, labels = generate_64_tiles(allowed_piece_versions)
        top = 64 * i
        bottom = top + 64
        X[top:bottom] = tiles
        Y[top:bottom] = labels
    Y = to_categorical(Y, num_classes=len(TILE_LABELS))
    ImageCache.clear()
    return X, Y

def generate_folds(k, n_piece_versions):
    possible_versions = np.arange(n_piece_versions)
    rng = np.random.RandomState(7)
    rng.shuffle(possible_versions)
    splits = np.array_split(possible_versions, k)
    indices = np.eye(k, dtype=int)
    versions_tr = []
    versions_va = []
    for i in range(k):
        fold_tr = []
        fold_va = []
        for j, value in enumerate(indices[i]):
            if value == 0:
                fold_tr.append(splits[j])
            else:
                fold_va.append(splits[j])
        versions_tr.append(np.concatenate((fold_tr)))
        versions_va.append(np.concatenate((fold_va)))
    return versions_tr, versions_va

class TileClassifier:
    nClasses = len(TILE_LABELS)
    ConfidenceThreshold = 0.75
    ModelName = "tile_classifier/model"

    def __init__(self):
        training_meta = toml.load("./tile_classifier/training/meta.toml")

        self.model = None
        self.n_piece_versions = training_meta["nPieceVersions"]
        self.n_epochs = training_meta["nEpochs"]

        self.load_model()

    def create_model(self):
        convolution_l2 = l2(1e-2)
        optimizer = Adam(amsgrad=True)
        self.normalization_layer = Normalization()

        self.model = Sequential()

        self.model.add(self.normalization_layer)
        self.model.add(Conv2D(
            12, (3, 3),
            activation="relu",
            padding="same",
            kernel_regularizer=convolution_l2,
            bias_regularizer=convolution_l2,
            input_shape=(40, 40, 1)
        ))
        self.model.add(Conv2D(
            24, (3, 3),
            activation="relu",
            padding="same",
            kernel_regularizer=convolution_l2,
            bias_regularizer=convolution_l2
        ))
        self.model.add(MaxPool2D(pool_size=(2, 2)))
        self.model.add(Conv2D(
            16, (3, 3),
            activation="relu",
            padding="same",
            kernel_regularizer=convolution_l2,
            bias_regularizer=convolution_l2
        ))
        self.model.add(MaxPool2D(pool_size=(2, 2)))
        self.model.add(Flatten())
        self.model.add(Dropout(0.2))
        self.model.add(Dense(256, activation="relu"))
        self.model.add(Dense(128, activation="relu"))
        self.model.add(Dense(self.nClasses, activation="softmax"))

        self.model.compile(
            loss="categorical_crossentropy",
            optimizer=optimizer,
            metrics=["accuracy"]
        )

    def fit(self, X_tr, Y_tr, X_va, Y_va):
        self.normalization_layer.adapt(X_tr)
        self.model.fit(
            X_tr, Y_tr,
            validation_data=(X_va, Y_va),
            epochs=self.n_epochs,
            shuffle=True,
            batch_size=64,
            verbose=1
        )

    def train_model(self):
        all_piece_versions = np.arange(self.n_piece_versions)
        X_tr, Y_tr = generate_synthetic_batches(512, all_piece_versions)
        X_va, Y_va = generate_synthetic_batches(32, all_piece_versions)
        self.fit(X_tr, Y_tr, X_va, Y_va)

    def cross_validate(self, k):
        versions_tr, versions_va = generate_folds(k, self.n_piece_versions)
        for i in range(k):
            try:
                self.model.load_weights("./tile_classifier/training/cv_weights.h5")
            except Exception:
                self.model.save_weights("./tile_classifier/training/cv_weights.h5")
            print(f"Fold {i + 1}/{k}:")
            print(f"  Training Versions:   {versions_tr[i]}")
            print(f"  Validation Versions: {versions_va[i]}")
            X_tr, Y_tr = generate_synthetic_batches(256, versions_tr[i])
            X_va, Y_va = generate_synthetic_batches(32, versions_va[i])
            self.fit(X_tr, Y_tr, X_va, Y_va)

    def load_model(self):
        try:
            self.model = load_model(TileClassifier.ModelName)
        except Exception:
            self.create_model()
            self.train_model()
            self.model.save(TileClassifier.ModelName)

    def predict(self, screenshot, board_rect):
        tiles = extract_tiles_from_screenshot(screenshot, board_rect)
        labels_probabilistic = self.model.predict(tiles)
        highest_probabilities = labels_probabilistic.max(axis=1)
        least_high_probability = highest_probabilities.min()
        if least_high_probability < TileClassifier.ConfidenceThreshold:
            return None
        labels = np.argmax(labels_probabilistic, axis=1)
        labels = TILE_LABELS[labels]
        return labels.reshape(8, 8)
