import tkinter as tk
from tkinter import messagebox, ttk
import json
import os
from datetime import datetime
from copy import deepcopy

# ─────────────────────────────────────────────
#  CONSTANTS
# ─────────────────────────────────────────────
SAVE_FILE_PREFIX = "chess_games"
MAX_GAMES = 10
SQUARE_SIZE = 72
BOARD_OFFSET = 40          # space for rank/file labels
ANIM_STEPS = 10
ANIM_DELAY = 12            # ms per animation frame

# ── Palette (modern dark theme) ───────────────
BG_APP       = "#0d0d17"
BG_PANEL     = "#171726"
BG_PANEL_ALT = "#1f1f33"
BG_CARD      = "#1c1c2e"
ACCENT       = "#e0b34c"
ACCENT_HOVER = "#f0c766"
ACCENT_DARK  = "#b8903a"
TEXT_PRIMARY = "#f2f0e6"
TEXT_MUTED   = "#8e8ea8"
TEXT_DIM     = "#54546a"
DANGER       = "#e2554f"
DANGER_HOVER = "#ea6e69"

LIGHT = "#eef0e3"
DARK  = "#7c8f5f"
HIGHLIGHT_VALID  = "#8fbf6b"
HIGHLIGHT_SELECT = "#f5e37a"
HIGHLIGHT_CHECK  = "#e2554f"
HIGHLIGHT_LAST   = "#cdd26a"

FONT_TITLE = ("Georgia", 34, "bold")
FONT_SUB   = ("Segoe UI", 11)
FONT_HEAD  = ("Segoe UI", 13, "bold")
FONT_BODY  = ("Segoe UI", 11)
FONT_SMALL = ("Segoe UI", 9)
FONT_MONO  = ("Consolas", 10)
PIECE_FONT = ("Segoe UI Symbol", 38)
CAP_FONT   = ("Segoe UI Symbol", 15)

UNICODE_PIECES = {
    ("white", "K"): "♔", ("white", "Q"): "♕",
    ("white", "R"): "♖", ("white", "B"): "♗",
    ("white", "N"): "♘", ("white", "P"): "♙",
    ("black", "K"): "♚", ("black", "Q"): "♛",
    ("black", "R"): "♜", ("black", "B"): "♝",
    ("black", "N"): "♞", ("black", "P"): "♟",
}

PIECE_VALUES = {"P": 1, "N": 3, "B": 3, "R": 5, "Q": 9, "K": 0}
CAP_ORDER = {"Q": 0, "R": 1, "B": 2, "N": 3, "P": 4}


# ─────────────────────────────────────────────
#  UI HELPERS
# ─────────────────────────────────────────────
def make_button(parent, text, command, bg=ACCENT, fg=BG_APP, hover_bg=None,
                 font=FONT_BODY, padx=16, pady=9, width=None, state=tk.NORMAL):
    """A flat button with a hover-brighten effect."""
    hover_bg = hover_bg or ACCENT_HOVER
    btn = tk.Button(parent, text=text, command=command, bg=bg, fg=fg,
                     activebackground=hover_bg, activeforeground=fg,
                     font=font, bd=0, padx=padx, pady=pady, cursor="hand2",
                     highlightthickness=0, relief="flat", state=state)
    if width:
        btn.config(width=width)

    def on_enter(_e):
        if btn["state"] != "disabled":
            btn.config(bg=hover_bg)

    def on_leave(_e):
        if btn["state"] != "disabled":
            btn.config(bg=bg)

    btn.bind("<Enter>", on_enter)
    btn.bind("<Leave>", on_leave)
    return btn


def make_card(parent, **kwargs):
    """A subtly-bordered panel to visually group content."""
    f = tk.Frame(parent, bg=BG_CARD, highlightbackground=BG_PANEL_ALT,
                 highlightthickness=1, **kwargs)
    return f


# ─────────────────────────────────────────────
#  CHESS LOGIC  (unchanged rules engine)
# ─────────────────────────────────────────────
def initial_board():
    """Return the starting position as an 8×8 list of (color, type) or None."""
    b = [[None]*8 for _ in range(8)]
    back = ["R","N","B","Q","K","B","N","R"]
    for c, color in ((0,"black"),(7,"white")):
        for j, piece in enumerate(back):
            b[c][j] = (color, piece)
    for j in range(8):
        b[1][j] = ("black","P")
        b[6][j] = ("white","P")
    return b

def in_bounds(r, c):
    return 0 <= r < 8 and 0 <= c < 8

def opponent(color):
    return "black" if color == "white" else "white"

def raw_moves(board, r, c):
    """All pseudo-legal target squares for the piece at (r,c)."""
    piece = board[r][c]
    if piece is None:
        return []
    color, ptype = piece
    moves = []

    def slide(dr, dc):
        nr, nc = r+dr, c+dc
        while in_bounds(nr, nc):
            if board[nr][nc] is None:
                moves.append((nr, nc))
            else:
                if board[nr][nc][0] != color:
                    moves.append((nr, nc))
                break
            nr += dr; nc += dc

    if ptype == "P":
        direction = -1 if color == "white" else 1
        start_row  =  6 if color == "white" else 1
        # forward
        nr = r + direction
        if in_bounds(nr, c) and board[nr][c] is None:
            moves.append((nr, c))
            # double push
            if r == start_row and board[r+2*direction][c] is None:
                moves.append((r+2*direction, c))
        # captures
        for dc in (-1, 1):
            nr, nc = r+direction, c+dc
            if in_bounds(nr, nc) and board[nr][nc] is not None and board[nr][nc][0] != color:
                moves.append((nr, nc))

    elif ptype == "N":
        for dr, dc in [(-2,-1),(-2,1),(-1,-2),(-1,2),(1,-2),(1,2),(2,-1),(2,1)]:
            nr, nc = r+dr, c+dc
            if in_bounds(nr, nc) and (board[nr][nc] is None or board[nr][nc][0] != color):
                moves.append((nr, nc))

    elif ptype == "B":
        for dr, dc in [(-1,-1),(-1,1),(1,-1),(1,1)]:
            slide(dr, dc)

    elif ptype == "R":
        for dr, dc in [(-1,0),(1,0),(0,-1),(0,1)]:
            slide(dr, dc)

    elif ptype == "Q":
        for dr, dc in [(-1,-1),(-1,0),(-1,1),(0,-1),(0,1),(1,-1),(1,0),(1,1)]:
            slide(dr, dc)

    elif ptype == "K":
        for dr, dc in [(-1,-1),(-1,0),(-1,1),(0,-1),(0,1),(1,-1),(1,0),(1,1)]:
            nr, nc = r+dr, c+dc
            if in_bounds(nr, nc) and (board[nr][nc] is None or board[nr][nc][0] != color):
                moves.append((nr, nc))

    return moves

def find_king(board, color):
    for r in range(8):
        for c in range(8):
            if board[r][c] == (color, "K"):
                return (r, c)
    return None

def is_in_check(board, color):
    kr, kc = find_king(board, color)
    opp = opponent(color)
    for r in range(8):
        for c in range(8):
            if board[r][c] is not None and board[r][c][0] == opp:
                if (kr, kc) in raw_moves(board, r, c):
                    return True
    return False

def legal_moves(board, r, c):
    """Moves that don't leave own king in check."""
    piece = board[r][c]
    if piece is None:
        return []
    color = piece[0]
    result = []
    for nr, nc in raw_moves(board, r, c):
        nb = deepcopy(board)
        nb[nr][nc] = nb[r][c]
        nb[r][c] = None
        if not is_in_check(nb, color):
            result.append((nr, nc))
    return result

def all_legal_moves(board, color):
    moves = []
    for r in range(8):
        for c in range(8):
            if board[r][c] is not None and board[r][c][0] == color:
                for m in legal_moves(board, r, c):
                    moves.append((r, c, m[0], m[1]))
    return moves

def is_checkmate(board, color):
    return is_in_check(board, color) and len(all_legal_moves(board, color)) == 0

def is_stalemate(board, color):
    return not is_in_check(board, color) and len(all_legal_moves(board, color)) == 0

def square_name(r, c):
    return "abcdefgh"[c] + str(8 - r)

def move_notation(board, fr, fc, tr, tc):
    piece = board[fr][fc]
    if piece is None:
        return ""
    ptype = piece[1]
    capture = "x" if board[tr][tc] is not None else ""
    prefix = "" if ptype == "P" else ptype
    return f"{prefix}{square_name(fr,fc)}{capture}{square_name(tr,tc)}"


# ─────────────────────────────────────────────
#  GAME STORAGE  (auto-incrementing files)
# ─────────────────────────────────────────────
def _all_save_files():
    """Return sorted list of all existing chess_games_N.txt files."""
    files = []
    i = 1
    while True:
        path = f"{SAVE_FILE_PREFIX}_{i}.txt"
        if os.path.exists(path):
            files.append(path)
            i += 1
        else:
            break
    return files

def _current_save_file():
    """Return the active file to write to (last one if under limit, else a new one)."""
    files = _all_save_files()
    if not files:
        return f"{SAVE_FILE_PREFIX}_1.txt"
    last = files[-1]
    try:
        with open(last, "r") as f:
            games = json.load(f)
        if len(games) >= MAX_GAMES:
            # start a new file
            n = len(files) + 1
            return f"{SAVE_FILE_PREFIX}_{n}.txt"
    except Exception:
        pass
    return last

def load_games():
    """Load all games across all save files, newest file last."""
    all_games = []
    for path in _all_save_files():
        try:
            with open(path, "r") as f:
                all_games.extend(json.load(f))
        except Exception:
            pass
    return all_games

def save_game(game):
    """Append a single completed game to the appropriate file."""
    path = _current_save_file()
    games = []
    if os.path.exists(path):
        try:
            with open(path, "r") as f:
                games = json.load(f)
        except Exception:
            games = []
    games.append(game)
    with open(path, "w") as f:
        json.dump(games, f, indent=2)


# ─────────────────────────────────────────────
#  MAIN APPLICATION
# ─────────────────────────────────────────────
class ChessApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Chess")
        self.resizable(False, False)
        self.configure(bg=BG_APP)
        self._show_main_menu()

    def _clear(self):
        for w in self.winfo_children():
            w.destroy()

    # ── Main Menu ──────────────────────────────
    def _show_main_menu(self):
        self._clear()
        self.title("Chess")

        outer = tk.Frame(self, bg=BG_APP, padx=70, pady=60)
        outer.pack()

        tk.Label(outer, text="♔  CHESS  ♚", font=FONT_TITLE,
                 bg=BG_APP, fg=ACCENT).pack(pady=(0, 6))
        tk.Label(outer, text="LOCAL TWO PLAYER", font=("Segoe UI", 10, "bold"),
                 bg=BG_APP, fg=TEXT_MUTED).pack(pady=(0, 36))

        card = make_card(outer, padx=30, pady=28)
        card.pack()

        make_button(card, "New Game", self._start_new_game,
                    bg=ACCENT, fg=BG_APP, hover_bg=ACCENT_HOVER,
                    font=FONT_HEAD, width=18).pack(pady=6)

        games = load_games()
        replay_state = tk.NORMAL if games else tk.DISABLED
        make_button(card, "Replay Game", self._show_replay_menu,
                    bg=BG_PANEL_ALT, fg=TEXT_PRIMARY, hover_bg="#2a2a45",
                    font=FONT_HEAD, width=18, state=replay_state).pack(pady=6)

        make_button(card, "Quit", self.quit,
                    bg=BG_PANEL, fg=TEXT_MUTED, hover_bg="#26263a",
                    font=FONT_HEAD, width=18).pack(pady=6)

        if games:
            tk.Label(outer, text=f"{len(games)} game(s) saved",
                     font=FONT_SMALL, bg=BG_APP, fg=TEXT_DIM).pack(pady=(20, 0))

    # ── New Game ───────────────────────────────
    def _start_new_game(self):
        self._clear()
        GameScreen(self)

    # ── Replay Menu ────────────────────────────
    def _show_replay_menu(self):
        self._clear()

        frame = tk.Frame(self, bg=BG_APP, padx=40, pady=30)
        frame.pack(fill="both", expand=True)

        tk.Label(frame, text="Select a Game to Replay",
                 font=("Georgia", 20, "bold"), bg=BG_APP, fg=ACCENT).pack(pady=(0, 20))

        listbox_frame = make_card(frame)
        listbox_frame.pack(fill="both", expand=True)

        sb = tk.Scrollbar(listbox_frame)
        sb.pack(side="right", fill="y")

        lb = tk.Listbox(listbox_frame, yscrollcommand=sb.set,
                        font=FONT_MONO, bg=BG_CARD, fg=TEXT_PRIMARY,
                        selectbackground=ACCENT, selectforeground=BG_APP,
                        bd=0, highlightthickness=0, activestyle="none",
                        width=54, height=12)
        lb.pack(side="left", fill="both", expand=True, padx=(10, 0), pady=10)
        sb.config(command=lb.yview)

        # Annotate each game with its source file for display
        annotated = []
        for path in _all_save_files():
            try:
                with open(path, "r") as fh:
                    file_games = json.load(fh)
                for g in file_games:
                    annotated.append((os.path.basename(path), g))
            except Exception:
                pass

        for i, (fname, g) in enumerate(annotated):
            date   = g.get("date", "")
            moves  = len(g.get("moves", []))
            result = g.get("result", "?")
            short_result = result.split("!")[0] if "!" in result else result
            lb.insert("end", f"  {i+1:>2}.  {date}   {moves:>3}mv   {short_result}")

        btn_frame = tk.Frame(frame, bg=BG_APP)
        btn_frame.pack(pady=16)

        def launch():
            sel = lb.curselection()
            if not sel:
                messagebox.showinfo("Select a game", "Please select a game from the list.")
                return
            idx = sel[0]
            _, game_data = annotated[idx]
            self._clear()
            ReplayScreen(self, game_data)

        make_button(btn_frame, "Replay Selected", launch,
                    bg=ACCENT, fg=BG_APP, hover_bg=ACCENT_HOVER,
                    font=FONT_BODY).pack(side="left", padx=8)
        make_button(btn_frame, "← Back", self._show_main_menu,
                    bg=BG_PANEL_ALT, fg=TEXT_PRIMARY, hover_bg="#2a2a45",
                    font=FONT_BODY).pack(side="left", padx=8)


# ─────────────────────────────────────────────
#  GAME SCREEN
# ─────────────────────────────────────────────
class GameScreen(tk.Frame):
    def __init__(self, master):
        super().__init__(master, bg=BG_APP)
        self.pack(fill="both", expand=True)
        self.master = master

        self.board       = initial_board()
        self.turn        = "white"
        self.selected    = None          # (r, c) of selected piece
        self.valid_moves = []
        self.last_move   = None          # (fr,fc,tr,tc)
        self.move_log    = []            # list of notation strings
        self.positions   = [deepcopy(self.board)]  # for replay
        self.captured    = {"white": [], "black": []}   # pieces captured BY each side
        self.captured_history = [deepcopy(self.captured)]
        self.game_over   = False
        self.animating   = False

        self._build_ui()
        self._draw_board()
        self._update_captured_panel()

    # ── UI Layout ──────────────────────────────
    def _build_ui(self):
        top = tk.Frame(self, bg=BG_APP)
        top.pack(fill="x", padx=14, pady=(12, 6))

        make_button(top, "← Menu", self._back_to_menu,
                    bg=BG_PANEL_ALT, fg=TEXT_PRIMARY, hover_bg="#2a2a45",
                    font=FONT_SUB, padx=12, pady=6).pack(side="left")

        status_wrap = tk.Frame(top, bg=BG_APP)
        status_wrap.pack(side="left", padx=20)

        self.turn_dot = tk.Canvas(status_wrap, width=16, height=16, bg=BG_APP,
                                   highlightthickness=0)
        self.turn_dot.pack(side="left", padx=(0, 8))
        self._draw_turn_dot()

        self.status_var = tk.StringVar(value="White's turn")
        tk.Label(status_wrap, textvariable=self.status_var,
                 font=FONT_HEAD, bg=BG_APP, fg=TEXT_PRIMARY).pack(side="left")

        main = tk.Frame(self, bg=BG_APP)
        main.pack(padx=14, pady=4)

        # Board canvas
        canvas_size = SQUARE_SIZE * 8 + BOARD_OFFSET * 2
        self.canvas = tk.Canvas(main, width=canvas_size, height=canvas_size,
                                bg=BG_APP, bd=0, highlightthickness=0)
        self.canvas.pack(side="left")
        self.canvas.bind("<Button-1>", self._on_click)

        # Right side panel
        side_panel = tk.Frame(main, bg=BG_APP, width=190)
        side_panel.pack(side="left", fill="y", padx=(14, 0))
        side_panel.pack_propagate(False)

        # Move log card
        log_card = make_card(side_panel)
        log_card.pack(fill="both", expand=True)

        tk.Label(log_card, text="MOVE LOG", font=("Segoe UI", 10, "bold"),
                 bg=BG_CARD, fg=ACCENT).pack(pady=(10, 6))

        self.log_text = tk.Text(log_card, font=FONT_MONO,
                                bg=BG_CARD, fg=TEXT_PRIMARY, bd=0,
                                state="disabled", wrap="word",
                                highlightthickness=0, padx=8)
        self.log_text.pack(fill="both", expand=True, padx=4, pady=(0, 10))

        # Captured pieces card
        cap_card = make_card(side_panel)
        cap_card.pack(fill="x", pady=(10, 0))

        tk.Label(cap_card, text="CAPTURED", font=("Segoe UI", 10, "bold"),
                 bg=BG_CARD, fg=ACCENT).pack(pady=(10, 6))

        self.cap_white_var = tk.StringVar(value="—")
        self.cap_black_var = tk.StringVar(value="—")
        self.material_var  = tk.StringVar(value="Material even")

        row_w = tk.Frame(cap_card, bg=BG_CARD)
        row_w.pack(fill="x", padx=10, anchor="w")
        tk.Label(row_w, text="White:", font=FONT_SMALL, bg=BG_CARD,
                 fg=TEXT_MUTED, width=6, anchor="w").pack(side="left")
        tk.Label(row_w, textvariable=self.cap_white_var, font=CAP_FONT,
                 bg=BG_CARD, fg=TEXT_PRIMARY, anchor="w",
                 justify="left", wraplength=140).pack(side="left")

        row_b = tk.Frame(cap_card, bg=BG_CARD)
        row_b.pack(fill="x", padx=10, pady=(2, 0), anchor="w")
        tk.Label(row_b, text="Black:", font=FONT_SMALL, bg=BG_CARD,
                 fg=TEXT_MUTED, width=6, anchor="w").pack(side="left")
        tk.Label(row_b, textvariable=self.cap_black_var, font=CAP_FONT,
                 bg=BG_CARD, fg=TEXT_PRIMARY, anchor="w",
                 justify="left", wraplength=140).pack(side="left")

        tk.Label(cap_card, textvariable=self.material_var, font=FONT_SMALL,
                 bg=BG_CARD, fg=ACCENT).pack(pady=(8, 10), padx=10, anchor="w")

    def _draw_turn_dot(self):
        self.turn_dot.delete("all")
        fill = "#FFFFFF" if self.turn == "white" else "#111111"
        outline = TEXT_MUTED
        self.turn_dot.create_oval(2, 2, 14, 14, fill=fill, outline=outline)

    # ── Drawing ────────────────────────────────
    def _draw_board(self, hide_square=None):
        self.canvas.delete("board", "piece")
        check_king = None
        if is_in_check(self.board, self.turn):
            check_king = find_king(self.board, self.turn)

        for r in range(8):
            for c in range(8):
                x1 = BOARD_OFFSET + c * SQUARE_SIZE
                y1 = BOARD_OFFSET + r * SQUARE_SIZE
                x2, y2 = x1 + SQUARE_SIZE, y1 + SQUARE_SIZE

                # base color
                base = LIGHT if (r + c) % 2 == 0 else DARK

                # overlays (priority order)
                if self.selected and (r, c) == self.selected:
                    color = HIGHLIGHT_SELECT
                elif (r, c) in self.valid_moves:
                    color = HIGHLIGHT_VALID
                elif self.last_move and (r, c) in (self.last_move[:2], self.last_move[2:]):
                    color = HIGHLIGHT_LAST
                elif check_king and (r, c) == check_king:
                    color = HIGHLIGHT_CHECK
                else:
                    color = base

                self.canvas.create_rectangle(x1, y1, x2, y2, fill=color, outline="", tags="board")

                # dot for valid move on empty square
                if (r, c) in self.valid_moves and self.board[r][c] is None:
                    cx, cy = (x1+x2)//2, (y1+y2)//2
                    self.canvas.create_oval(cx-10, cy-10, cx+10, cy+10,
                                            fill="#2b2b2b", outline="", stipple="gray50", tags="board")

                # piece
                if hide_square == (r, c):
                    continue
                piece = self.board[r][c]
                if piece:
                    sym = UNICODE_PIECES[piece]
                    fg = "#FFFFFF" if piece[0] == "white" else "#161616"
                    self.canvas.create_text(
                        (x1+x2)//2, (y1+y2)//2,
                        text=sym, font=PIECE_FONT,
                        fill=fg, tags="piece"
                    )

        # Rank / file labels
        for i in range(8):
            lx = BOARD_OFFSET + i * SQUARE_SIZE + SQUARE_SIZE // 2
            self.canvas.create_text(lx, BOARD_OFFSET - 14, text="abcdefgh"[i],
                                    font=FONT_SMALL, fill=TEXT_MUTED, tags="board")
            self.canvas.create_text(lx, BOARD_OFFSET + 8*SQUARE_SIZE + 14, text="abcdefgh"[i],
                                    font=FONT_SMALL, fill=TEXT_MUTED, tags="board")
            ly = BOARD_OFFSET + i * SQUARE_SIZE + SQUARE_SIZE // 2
            self.canvas.create_text(BOARD_OFFSET - 16, ly, text=str(8-i),
                                    font=FONT_SMALL, fill=TEXT_MUTED, tags="board")
            self.canvas.create_text(BOARD_OFFSET + 8*SQUARE_SIZE + 16, ly, text=str(8-i),
                                    font=FONT_SMALL, fill=TEXT_MUTED, tags="board")

    # ── Click handler ──────────────────────────
    def _on_click(self, event):
        if self.game_over or self.animating:
            return
        c = (event.x - BOARD_OFFSET) // SQUARE_SIZE
        r = (event.y - BOARD_OFFSET) // SQUARE_SIZE
        if not in_bounds(r, c):
            return

        if self.selected is None:
            # Select a piece
            piece = self.board[r][c]
            if piece and piece[0] == self.turn:
                self.selected = (r, c)
                self.valid_moves = legal_moves(self.board, r, c)
        else:
            fr, fc = self.selected
            if (r, c) in self.valid_moves:
                self._begin_animated_move(fr, fc, r, c)
                return
            elif self.board[r][c] and self.board[r][c][0] == self.turn:
                # re-select
                self.selected = (r, c)
                self.valid_moves = legal_moves(self.board, r, c)
            else:
                self.selected = None
                self.valid_moves = []

        self._draw_board()

    # ── Animation ──────────────────────────────
    def _begin_animated_move(self, fr, fc, tr, tc):
        piece = self.board[fr][fc]
        self.selected = None
        self.valid_moves = []
        self.animating = True
        self._draw_board(hide_square=(fr, fc))

        x1 = BOARD_OFFSET + fc * SQUARE_SIZE + SQUARE_SIZE // 2
        y1 = BOARD_OFFSET + fr * SQUARE_SIZE + SQUARE_SIZE // 2
        x2 = BOARD_OFFSET + tc * SQUARE_SIZE + SQUARE_SIZE // 2
        y2 = BOARD_OFFSET + tr * SQUARE_SIZE + SQUARE_SIZE // 2
        dx = (x2 - x1) / ANIM_STEPS
        dy = (y2 - y1) / ANIM_STEPS

        sym = UNICODE_PIECES[piece]
        fg = "#FFFFFF" if piece[0] == "white" else "#161616"
        anim_item = self.canvas.create_text(x1, y1, text=sym, font=PIECE_FONT,
                                             fill=fg, tags="anim")

        def step(i):
            if i >= ANIM_STEPS:
                self.canvas.delete("anim")
                self.animating = False
                self._apply_move(fr, fc, tr, tc)
                self._draw_board()
                return
            self.canvas.move(anim_item, dx, dy)
            self.after(ANIM_DELAY, lambda: step(i + 1))

        step(0)

    # ── Apply move ─────────────────────────────
    def _apply_move(self, fr, fc, tr, tc):
        notation = move_notation(self.board, fr, fc, tr, tc)

        mover_color = self.board[fr][fc][0]
        captured_piece = self.board[tr][tc]

        self.board[tr][tc] = self.board[fr][fc]
        self.board[fr][fc] = None

        if captured_piece:
            self.captured[mover_color].append(captured_piece[1])

        # Pawn promotion — ask the player
        piece = self.board[tr][tc]
        if piece and piece[1] == "P":
            if (piece[0] == "white" and tr == 0) or (piece[0] == "black" and tr == 7):
                chosen = self._promotion_dialog(piece[0])
                self.board[tr][tc] = (piece[0], chosen)
                notation += f"={chosen}"

        self.last_move  = (fr, fc, tr, tc)
        self.selected   = None
        self.valid_moves= []
        self.positions.append(deepcopy(self.board))
        self.captured_history.append(deepcopy(self.captured))
        self._update_captured_panel()

        # Check / checkmate / stalemate
        next_turn = opponent(self.turn)
        if is_checkmate(self.board, next_turn):
            notation += "#"
            self._log_move(notation)
            self._end_game(f"Checkmate! {self.turn.capitalize()} wins! 🏆")
            return
        elif is_stalemate(self.board, next_turn):
            self._log_move(notation)
            self._end_game("Stalemate! It's a draw.")
            return
        elif is_in_check(self.board, next_turn):
            notation += "+"

        self._log_move(notation)
        self.turn = next_turn
        self._draw_turn_dot()
        self.status_var.set(f"{self.turn.capitalize()}'s turn"
                            + (" — Check!" if is_in_check(self.board, self.turn) else ""))

    # ── Captured pieces panel ──────────────────
    def _update_captured_panel(self):
        white_caps = sorted(self.captured["white"], key=lambda p: CAP_ORDER.get(p, 9))
        black_caps = sorted(self.captured["black"], key=lambda p: CAP_ORDER.get(p, 9))

        self.cap_white_var.set("".join(UNICODE_PIECES[("black", p)] for p in white_caps) or "—")
        self.cap_black_var.set("".join(UNICODE_PIECES[("white", p)] for p in black_caps) or "—")

        diff = sum(PIECE_VALUES[p] for p in white_caps) - sum(PIECE_VALUES[p] for p in black_caps)
        if diff > 0:
            self.material_var.set(f"White ahead by {diff}")
        elif diff < 0:
            self.material_var.set(f"Black ahead by {-diff}")
        else:
            self.material_var.set("Material even")

    # ── Promotion dialog ───────────────────────
    def _promotion_dialog(self, color):
        """Block until the player picks a promotion piece. Returns piece letter."""
        chosen = tk.StringVar(value="Q")

        dlg = tk.Toplevel(self)
        dlg.title("Pawn Promotion")
        dlg.configure(bg=BG_APP)
        dlg.resizable(False, False)
        dlg.grab_set()          # modal
        dlg.protocol("WM_DELETE_WINDOW", lambda: None)  # prevent closing

        tk.Label(dlg, text=f"{color.capitalize()}: choose promotion",
                 font=FONT_HEAD, bg=BG_APP, fg=ACCENT,
                 padx=20, pady=14).pack()

        btn_frame = tk.Frame(dlg, bg=BG_APP)
        btn_frame.pack(padx=20, pady=(0, 20))

        options = [("Q", "Queen"), ("R", "Rook"), ("B", "Bishop"), ("N", "Knight")]
        for letter, name in options:
            sym = UNICODE_PIECES[(color, letter)]
            btn = tk.Button(
                btn_frame,
                text=f"{sym}\n{name}",
                font=("Segoe UI Symbol", 20),
                width=4, height=2,
                bg=BG_PANEL_ALT if color == "white" else BG_PANEL,
                fg=TEXT_PRIMARY,
                bd=0, cursor="hand2",
                activebackground=ACCENT, activeforeground=BG_APP,
                highlightthickness=0,
                command=lambda l=letter: [chosen.set(l), dlg.destroy()]
            )
            btn.pack(side="left", padx=6)
            btn.bind("<Enter>", lambda e, b=btn: b.config(bg=ACCENT, fg=BG_APP))
            btn.bind("<Leave>", lambda e, b=btn, cc=color: b.config(
                bg=BG_PANEL_ALT if cc == "white" else BG_PANEL, fg=TEXT_PRIMARY))

        self.wait_window(dlg)
        return chosen.get()

    # ── Log ────────────────────────────────────
    def _log_move(self, notation):
        self.move_log.append(notation)
        self.log_text.config(state="normal")

        move_num = len(self.move_log)
        if move_num % 2 == 1:
            self.log_text.insert("end", f"{(move_num+1)//2}. {notation} ")
        else:
            self.log_text.insert("end", f"{notation}\n")

        self.log_text.see("end")
        self.log_text.config(state="disabled")

    # ── Game Over ──────────────────────────────
    def _end_game(self, message):
        self.game_over = True
        self.status_var.set(message)
        self._draw_board()

        # Save game (bug fix: save_game() appends ONE game record, not a list)
        game_record = {
            "date":      datetime.now().strftime("%Y-%m-%d %H:%M"),
            "result":    message,
            "moves":     self.move_log,
            "positions": [[[list(sq) if sq else None for sq in row]
                           for row in pos] for pos in self.positions],
            "captured":  [deepcopy(c) for c in self.captured_history],
        }
        save_game(game_record)

        def back():
            popup.destroy()
            self.master._show_main_menu()

        popup = tk.Toplevel(self)
        popup.title("Game Over")
        popup.configure(bg=BG_APP)
        popup.resizable(False, False)
        popup.grab_set()

        tk.Label(popup, text=message, font=("Georgia", 16, "bold"),
                 bg=BG_APP, fg=ACCENT, padx=30, pady=20).pack()
        make_button(popup, "Back to Menu", back,
                    bg=ACCENT, fg=BG_APP, hover_bg=ACCENT_HOVER,
                    font=FONT_BODY).pack(pady=(0, 20))

    def _back_to_menu(self):
        if not self.game_over:
            if not messagebox.askyesno("Quit Game", "Abandon current game and return to menu?"):
                return
        self.master._show_main_menu()


# ─────────────────────────────────────────────
#  REPLAY SCREEN
# ─────────────────────────────────────────────
class ReplayScreen(tk.Frame):
    def __init__(self, master, game_data):
        super().__init__(master, bg=BG_APP)
        self.pack(fill="both", expand=True)
        self.master = master

        self.moves     = game_data.get("moves", [])
        self.positions = []
        raw = game_data.get("positions", [])
        for pos in raw:
            self.positions.append(
                [[tuple(sq) if sq else None for sq in row] for row in pos]
            )

        if not self.positions:
            messagebox.showerror("Error", "No position data for this game.")
            master._show_replay_menu()
            return

        # Captured-pieces history (older saves may not have this key)
        raw_caps = game_data.get("captured")
        if raw_caps and len(raw_caps) == len(self.positions):
            self.captured_history = raw_caps
        else:
            self.captured_history = [{"white": [], "black": []} for _ in self.positions]

        self.index     = 0
        self.total     = len(self.positions)
        self._auto_job = None   # after() id for auto-play

        self._build_ui()
        self._draw()

    # ── UI ─────────────────────────────────────
    def _build_ui(self):
        top = tk.Frame(self, bg=BG_APP)
        top.pack(fill="x", padx=14, pady=(12, 6))

        make_button(top, "← Back", self._back,
                    bg=BG_PANEL_ALT, fg=TEXT_PRIMARY, hover_bg="#2a2a45",
                    font=FONT_SUB, padx=12, pady=6).pack(side="left")

        self.status_var = tk.StringVar(value="Start position")
        tk.Label(top, textvariable=self.status_var,
                 font=FONT_HEAD, bg=BG_APP, fg=TEXT_PRIMARY).pack(side="left", padx=20)

        main = tk.Frame(self, bg=BG_APP)
        main.pack(padx=14, pady=4)

        canvas_size = SQUARE_SIZE * 8 + BOARD_OFFSET * 2
        self.canvas = tk.Canvas(main, width=canvas_size, height=canvas_size,
                                bg=BG_APP, bd=0, highlightthickness=0)
        self.canvas.pack(side="left")

        # Right panel: move list + captured + controls
        right = tk.Frame(main, bg=BG_APP, width=210)
        right.pack(side="left", fill="y", padx=(14, 0))
        right.pack_propagate(False)

        moves_card = make_card(right)
        moves_card.pack(fill="both", expand=True)

        tk.Label(moves_card, text="MOVES", font=("Segoe UI", 10, "bold"),
                 bg=BG_CARD, fg=ACCENT).pack(pady=(10, 6))

        self.move_list = tk.Listbox(moves_card, font=FONT_MONO,
                                    bg=BG_CARD, fg=TEXT_PRIMARY, bd=0,
                                    highlightthickness=0, activestyle="none",
                                    selectbackground=ACCENT, selectforeground=BG_APP)
        self.move_list.pack(fill="both", expand=True, padx=6, pady=(0, 8))
        self.move_list.bind("<<ListboxSelect>>", self._on_list_select)

        # Populate move list
        for i in range(0, len(self.moves), 2):
            n = i // 2 + 1
            w = self.moves[i]
            bl = self.moves[i+1] if i+1 < len(self.moves) else ""
            self.move_list.insert("end", f"  {n:>3}. {w:<8} {bl}")

        # Captured pieces card
        cap_card = make_card(right)
        cap_card.pack(fill="x", pady=(10, 0))

        tk.Label(cap_card, text="CAPTURED", font=("Segoe UI", 10, "bold"),
                 bg=BG_CARD, fg=ACCENT).pack(pady=(10, 6))

        self.cap_white_var = tk.StringVar(value="—")
        self.cap_black_var = tk.StringVar(value="—")
        self.material_var  = tk.StringVar(value="Material even")

        row_w = tk.Frame(cap_card, bg=BG_CARD)
        row_w.pack(fill="x", padx=10, anchor="w")
        tk.Label(row_w, text="White:", font=FONT_SMALL, bg=BG_CARD,
                 fg=TEXT_MUTED, width=6, anchor="w").pack(side="left")
        tk.Label(row_w, textvariable=self.cap_white_var, font=CAP_FONT,
                 bg=BG_CARD, fg=TEXT_PRIMARY, anchor="w",
                 justify="left", wraplength=150).pack(side="left")

        row_b = tk.Frame(cap_card, bg=BG_CARD)
        row_b.pack(fill="x", padx=10, pady=(2, 0), anchor="w")
        tk.Label(row_b, text="Black:", font=FONT_SMALL, bg=BG_CARD,
                 fg=TEXT_MUTED, width=6, anchor="w").pack(side="left")
        tk.Label(row_b, textvariable=self.cap_black_var, font=CAP_FONT,
                 bg=BG_CARD, fg=TEXT_PRIMARY, anchor="w",
                 justify="left", wraplength=150).pack(side="left")

        tk.Label(cap_card, textvariable=self.material_var, font=FONT_SMALL,
                 bg=BG_CARD, fg=ACCENT).pack(pady=(8, 10), padx=10, anchor="w")

        # Controls
        ctrl_card = make_card(right)
        ctrl_card.pack(fill="x", pady=(10, 0))

        ctrl = tk.Frame(ctrl_card, bg=BG_CARD)
        ctrl.pack(pady=12)

        btn_kwargs = dict(font=("Segoe UI Symbol", 15), bd=0, bg=BG_PANEL_ALT,
                          fg=TEXT_PRIMARY, activebackground=ACCENT,
                          activeforeground=BG_APP, cursor="hand2", width=3,
                          highlightthickness=0)

        def hover_ctrl(b):
            b.bind("<Enter>", lambda e: b.config(bg=ACCENT, fg=BG_APP))
            b.bind("<Leave>", lambda e: b.config(bg=BG_PANEL_ALT, fg=TEXT_PRIMARY))
            return b

        hover_ctrl(tk.Button(ctrl, text="|◀", command=self._go_start, **btn_kwargs)).grid(row=0, column=0, padx=2)
        hover_ctrl(tk.Button(ctrl, text="◀",  command=self._prev,     **btn_kwargs)).grid(row=0, column=1, padx=2)
        self.play_btn = tk.Button(ctrl, text="▶", command=self._toggle_auto, **btn_kwargs)
        hover_ctrl(self.play_btn).grid(row=0, column=2, padx=2)
        hover_ctrl(tk.Button(ctrl, text="▶",  command=self._next,     **btn_kwargs)).grid(row=0, column=3, padx=2)
        hover_ctrl(tk.Button(ctrl, text="▶|", command=self._go_end,   **btn_kwargs)).grid(row=0, column=4, padx=2)

        # Speed slider
        speed_frame = tk.Frame(ctrl_card, bg=BG_CARD)
        speed_frame.pack(pady=(0, 10))
        tk.Label(speed_frame, text="Speed", font=FONT_SMALL,
                 bg=BG_CARD, fg=TEXT_MUTED).pack()
        self.speed_var = tk.IntVar(value=1000)
        tk.Scale(speed_frame, from_=300, to=2000, orient="horizontal",
                 variable=self.speed_var, resolution=100,
                 bg=BG_CARD, fg=TEXT_PRIMARY, troughcolor=BG_PANEL_ALT,
                 highlightthickness=0, showvalue=False, bd=0,
                 activebackground=ACCENT,
                 length=170).pack()

    # ── Drawing ────────────────────────────────
    def _draw(self):
        board = self.positions[self.index]
        self.canvas.delete("all")

        last_move = None
        if self.index > 0:
            # figure out last move squares by comparing positions
            prev = self.positions[self.index - 1]
            moved_from = moved_to = None
            for r in range(8):
                for c in range(8):
                    if prev[r][c] != board[r][c]:
                        if prev[r][c] is not None and board[r][c] is None:
                            moved_from = (r, c)
                        if board[r][c] is not None:
                            moved_to = (r, c)
            if moved_from and moved_to:
                last_move = (moved_from, moved_to)

        for r in range(8):
            for c in range(8):
                x1 = BOARD_OFFSET + c * SQUARE_SIZE
                y1 = BOARD_OFFSET + r * SQUARE_SIZE
                x2, y2 = x1 + SQUARE_SIZE, y1 + SQUARE_SIZE

                base = LIGHT if (r + c) % 2 == 0 else DARK
                if last_move and (r,c) in last_move:
                    color = HIGHLIGHT_LAST
                else:
                    color = base

                self.canvas.create_rectangle(x1, y1, x2, y2, fill=color, outline="")

                piece = board[r][c]
                if piece:
                    sym = UNICODE_PIECES[piece]
                    fg = "#FFFFFF" if piece[0] == "white" else "#161616"
                    self.canvas.create_text(
                        (x1+x2)//2, (y1+y2)//2,
                        text=sym, font=PIECE_FONT, fill=fg
                    )

        # Labels
        for i in range(8):
            lx = BOARD_OFFSET + i * SQUARE_SIZE + SQUARE_SIZE // 2
            self.canvas.create_text(lx, BOARD_OFFSET - 14, text="abcdefgh"[i],
                                    font=FONT_SMALL, fill=TEXT_MUTED)
            self.canvas.create_text(lx, BOARD_OFFSET + 8*SQUARE_SIZE + 14, text="abcdefgh"[i],
                                    font=FONT_SMALL, fill=TEXT_MUTED)
            ly = BOARD_OFFSET + i * SQUARE_SIZE + SQUARE_SIZE // 2
            self.canvas.create_text(BOARD_OFFSET - 16, ly, text=str(8-i),
                                    font=FONT_SMALL, fill=TEXT_MUTED)
            self.canvas.create_text(BOARD_OFFSET + 8*SQUARE_SIZE + 16, ly, text=str(8-i),
                                    font=FONT_SMALL, fill=TEXT_MUTED)

        # Status
        if self.index == 0:
            self.status_var.set("Start position")
        elif self.index == self.total - 1:
            self.status_var.set(f"Final position  ({self.total-1} moves)")
        else:
            move_n = self.index
            side   = "White" if move_n % 2 == 1 else "Black"
            notation = self.moves[self.index - 1] if self.index - 1 < len(self.moves) else ""
            self.status_var.set(f"Move {move_n}  ({side}: {notation})")

        # Highlight move list row
        move_row = max(0, (self.index - 1) // 2)
        self.move_list.selection_clear(0, "end")
        if self.index > 0:
            self.move_list.selection_set(move_row)
            self.move_list.see(move_row)

        self._update_captured_panel()

    # ── Captured pieces panel ──────────────────
    def _update_captured_panel(self):
        caps = self.captured_history[self.index]
        white_caps = sorted(caps.get("white", []), key=lambda p: CAP_ORDER.get(p, 9))
        black_caps = sorted(caps.get("black", []), key=lambda p: CAP_ORDER.get(p, 9))

        self.cap_white_var.set("".join(UNICODE_PIECES[("black", p)] for p in white_caps) or "—")
        self.cap_black_var.set("".join(UNICODE_PIECES[("white", p)] for p in black_caps) or "—")

        diff = sum(PIECE_VALUES[p] for p in white_caps) - sum(PIECE_VALUES[p] for p in black_caps)
        if diff > 0:
            self.material_var.set(f"White ahead by {diff}")
        elif diff < 0:
            self.material_var.set(f"Black ahead by {-diff}")
        else:
            self.material_var.set("Material even")

    # ── Navigation ─────────────────────────────
    def _go_start(self):
        self._stop_auto()
        self.index = 0
        self._draw()

    def _go_end(self):
        self._stop_auto()
        self.index = self.total - 1
        self._draw()

    def _prev(self):
        self._stop_auto()
        if self.index > 0:
            self.index -= 1
            self._draw()

    def _next(self):
        if self.index < self.total - 1:
            self.index += 1
            self._draw()

    def _on_list_select(self, event):
        sel = self.move_list.curselection()
        if not sel:
            return
        # each row = 2 moves; clicking row N → go to position N*2+1 (after white's move)
        row = sel[0]
        target = row * 2 + 1
        target = min(target, self.total - 1)
        self._stop_auto()
        self.index = target
        self._draw()

    # ── Auto-play ──────────────────────────────
    def _toggle_auto(self):
        if self._auto_job is not None:
            self._stop_auto()
        else:
            self._start_auto()

    def _start_auto(self):
        self.play_btn.config(text="⏸")
        self._auto_step()

    def _auto_step(self):
        if self.index < self.total - 1:
            self._next()
            delay = self.speed_var.get()
            self._auto_job = self.after(delay, self._auto_step)
        else:
            self._stop_auto()

    def _stop_auto(self):
        if self._auto_job is not None:
            self.after_cancel(self._auto_job)
            self._auto_job = None
        self.play_btn.config(text="▶")

    def _back(self):
        self._stop_auto()
        self.master._show_replay_menu()


# ─────────────────────────────────────────────
#  ENTRY POINT
# ─────────────────────────────────────────────
if __name__ == "__main__":
    app = ChessApp()
    app.mainloop()
