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

LIGHT = "#F0D9B5"
DARK  = "#B58863"
HIGHLIGHT_VALID  = "#AAD651"   # green tint for valid moves
HIGHLIGHT_SELECT = "#F6F669"   # yellow tint for selected piece
HIGHLIGHT_CHECK  = "#FF4444"   # red for king in check
HIGHLIGHT_LAST   = "#CDD26A"   # subtle last-move highlight

UNICODE_PIECES = {
    ("white", "K"): "♔", ("white", "Q"): "♕",
    ("white", "R"): "♖", ("white", "B"): "♗",
    ("white", "N"): "♘", ("white", "P"): "♙",
    ("black", "K"): "♚", ("black", "Q"): "♛",
    ("black", "R"): "♜", ("black", "B"): "♝",
    ("black", "N"): "♞", ("black", "P"): "♟",
}

# ─────────────────────────────────────────────
#  CHESS LOGIC
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
        self.configure(bg="#1a1a2e")
        self._show_main_menu()

    def _clear(self):
        for w in self.winfo_children():
            w.destroy()

    # ── Main Menu ──────────────────────────────
    def _show_main_menu(self):
        self._clear()
        self.title("Chess")

        frame = tk.Frame(self, bg="#1a1a2e", padx=60, pady=50)
        frame.pack()

        tk.Label(frame, text="♔  CHESS  ♚", font=("Georgia", 36, "bold"),
                 bg="#1a1a2e", fg="#F0D9B5").pack(pady=(0,8))
        tk.Label(frame, text="Local Two Player", font=("Georgia", 12),
                 bg="#1a1a2e", fg="#888").pack(pady=(0,40))

        btn_style = dict(font=("Georgia", 14), width=18, bd=0, pady=10,
                         cursor="hand2", activeforeground="#1a1a2e")

        tk.Button(frame, text="New Game", bg="#F0D9B5", fg="#1a1a2e",
                  activebackground="#d4bc96",
                  command=self._start_new_game, **btn_style).pack(pady=8)

        games = load_games()
        replay_state = tk.NORMAL if games else tk.DISABLED
        tk.Button(frame, text="Replay Game", bg="#B58863", fg="#1a1a2e",
                  activebackground="#9a7250",
                  command=self._show_replay_menu, state=replay_state,
                  **btn_style).pack(pady=8)

        tk.Button(frame, text="Quit", bg="#333355", fg="#F0D9B5",
                  activebackground="#444466",
                  command=self.quit, **btn_style).pack(pady=8)

        if games:
            tk.Label(frame, text=f"{len(games)} game(s) saved",
                     font=("Georgia", 10), bg="#1a1a2e", fg="#555").pack(pady=(20,0))

    # ── New Game ───────────────────────────────
    def _start_new_game(self):
        self._clear()
        GameScreen(self)

    # ── Replay Menu ────────────────────────────
    def _show_replay_menu(self):
        self._clear()
        games = load_games()

        frame = tk.Frame(self, bg="#1a1a2e", padx=40, pady=30)
        frame.pack(fill="both", expand=True)

        tk.Label(frame, text="Select a Game to Replay",
                 font=("Georgia", 20, "bold"), bg="#1a1a2e", fg="#F0D9B5").pack(pady=(0,20))

        listbox_frame = tk.Frame(frame, bg="#1a1a2e")
        listbox_frame.pack(fill="both", expand=True)

        sb = tk.Scrollbar(listbox_frame)
        sb.pack(side="right", fill="y")

        lb = tk.Listbox(listbox_frame, yscrollcommand=sb.set,
                        font=("Courier", 11), bg="#0d0d1a", fg="#F0D9B5",
                        selectbackground="#B58863", selectforeground="#1a1a2e",
                        bd=0, highlightthickness=0, activestyle="none",
                        width=50, height=12)
        lb.pack(side="left", fill="both", expand=True)
        sb.config(command=lb.yview)

        games = load_games()
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
            result = g.get("result", "?")
            date   = g.get("date", "")
            moves  = len(g.get("moves", []))
            lb.insert("end", f"  {i+1:>2}.  {date}   {moves}mv   {fname}")

        btn_frame = tk.Frame(frame, bg="#1a1a2e")
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

        tk.Button(btn_frame, text="Replay Selected", font=("Georgia", 13),
                  bg="#F0D9B5", fg="#1a1a2e", bd=0, padx=16, pady=8,
                  cursor="hand2", activebackground="#d4bc96",
                  command=launch).pack(side="left", padx=8)

        tk.Button(btn_frame, text="← Back", font=("Georgia", 13),
                  bg="#333355", fg="#F0D9B5", bd=0, padx=16, pady=8,
                  cursor="hand2", activebackground="#444466",
                  command=self._show_main_menu).pack(side="left", padx=8)


# ─────────────────────────────────────────────
#  GAME SCREEN
# ─────────────────────────────────────────────
class GameScreen(tk.Frame):
    def __init__(self, master):
        super().__init__(master, bg="#1a1a2e")
        self.pack(fill="both", expand=True)
        self.master = master

        self.board      = initial_board()
        self.turn       = "white"
        self.selected   = None          # (r, c) of selected piece
        self.valid_moves= []
        self.last_move  = None          # (fr,fc,tr,tc)
        self.move_log   = []            # list of notation strings
        self.positions  = [deepcopy(self.board)]  # for replay
        self.game_over  = False

        self._build_ui()
        self._draw_board()

    # ── UI Layout ──────────────────────────────
    def _build_ui(self):
        top = tk.Frame(self, bg="#1a1a2e")
        top.pack(fill="x", padx=10, pady=6)

        tk.Button(top, text="← Menu", font=("Georgia", 11),
                  bg="#333355", fg="#F0D9B5", bd=0, padx=10, pady=4,
                  cursor="hand2", activebackground="#444466",
                  command=self._back_to_menu).pack(side="left")

        self.status_var = tk.StringVar(value="White's turn")
        tk.Label(top, textvariable=self.status_var,
                 font=("Georgia", 14, "bold"), bg="#1a1a2e", fg="#F0D9B5").pack(side="left", padx=20)

        main = tk.Frame(self, bg="#1a1a2e")
        main.pack(padx=10, pady=4)

        # Board canvas
        canvas_size = SQUARE_SIZE * 8 + BOARD_OFFSET * 2
        self.canvas = tk.Canvas(main, width=canvas_size, height=canvas_size,
                                bg="#1a1a2e", bd=0, highlightthickness=0)
        self.canvas.pack(side="left")
        self.canvas.bind("<Button-1>", self._on_click)

        # Move log panel
        log_frame = tk.Frame(main, bg="#0d0d1a", width=180)
        log_frame.pack(side="left", fill="y", padx=(12,0))
        log_frame.pack_propagate(False)

        tk.Label(log_frame, text="Move Log", font=("Georgia", 12, "bold"),
                 bg="#0d0d1a", fg="#F0D9B5").pack(pady=8)

        self.log_text = tk.Text(log_frame, font=("Courier", 10),
                                bg="#0d0d1a", fg="#ccc", bd=0,
                                state="disabled", wrap="word")
        self.log_text.pack(fill="both", expand=True, padx=6, pady=(0,8))

    # ── Drawing ────────────────────────────────
    def _draw_board(self):
        self.canvas.delete("all")
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

                self.canvas.create_rectangle(x1, y1, x2, y2, fill=color, outline="")

                # dot for valid move on empty square
                if (r, c) in self.valid_moves and self.board[r][c] is None:
                    cx, cy = (x1+x2)//2, (y1+y2)//2
                    self.canvas.create_oval(cx-10, cy-10, cx+10, cy+10,
                                            fill="#3a3a3a", outline="", stipple="gray50")

                # piece
                piece = self.board[r][c]
                if piece:
                    sym = UNICODE_PIECES[piece]
                    fg = "#FFFFFF" if piece[0] == "white" else "#1a1a2e"
                    self.canvas.create_text(
                        (x1+x2)//2, (y1+y2)//2,
                        text=sym, font=("Segoe UI Symbol", 38),
                        fill=fg
                    )

        # Rank / file labels
        for i in range(8):
            # files (a-h)
            lx = BOARD_OFFSET + i * SQUARE_SIZE + SQUARE_SIZE // 2
            self.canvas.create_text(lx, BOARD_OFFSET - 14, text="abcdefgh"[i],
                                    font=("Georgia", 10), fill="#888")
            self.canvas.create_text(lx, BOARD_OFFSET + 8*SQUARE_SIZE + 14, text="abcdefgh"[i],
                                    font=("Georgia", 10), fill="#888")
            # ranks (8-1)
            ly = BOARD_OFFSET + i * SQUARE_SIZE + SQUARE_SIZE // 2
            self.canvas.create_text(BOARD_OFFSET - 16, ly, text=str(8-i),
                                    font=("Georgia", 10), fill="#888")
            self.canvas.create_text(BOARD_OFFSET + 8*SQUARE_SIZE + 16, ly, text=str(8-i),
                                    font=("Georgia", 10), fill="#888")

    # ── Click handler ──────────────────────────
    def _on_click(self, event):
        if self.game_over:
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
                self._apply_move(fr, fc, r, c)
            elif self.board[r][c] and self.board[r][c][0] == self.turn:
                # re-select
                self.selected = (r, c)
                self.valid_moves = legal_moves(self.board, r, c)
            else:
                self.selected = None
                self.valid_moves = []

        self._draw_board()

    # ── Apply move ─────────────────────────────
    def _apply_move(self, fr, fc, tr, tc):
        notation = move_notation(self.board, fr, fc, tr, tc)

        self.board[tr][tc] = self.board[fr][fc]
        self.board[fr][fc] = None

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
        self.status_var.set(f"{'⬜' if self.turn=='white' else '⬛'}  {self.turn.capitalize()}'s turn"
                            + (" — Check!" if is_in_check(self.board, self.turn) else ""))

    # ── Promotion dialog ───────────────────────
    def _promotion_dialog(self, color):
        """Block until the player picks a promotion piece. Returns piece letter."""
        chosen = tk.StringVar(value="Q")

        dlg = tk.Toplevel(self)
        dlg.title("Pawn Promotion")
        dlg.configure(bg="#1a1a2e")
        dlg.resizable(False, False)
        dlg.grab_set()          # modal
        dlg.protocol("WM_DELETE_WINDOW", lambda: None)  # prevent closing

        tk.Label(dlg, text=f"{color.capitalize()}: choose promotion",
                 font=("Georgia", 13, "bold"), bg="#1a1a2e", fg="#F0D9B5",
                 padx=20, pady=12).pack()

        btn_frame = tk.Frame(dlg, bg="#1a1a2e")
        btn_frame.pack(padx=20, pady=(0, 20))

        options = [("Q", "Queen"), ("R", "Rook"), ("B", "Bishop"), ("N", "Knight")]
        for letter, name in options:
            sym = UNICODE_PIECES[(color, letter)]
            tk.Button(
                btn_frame,
                text=f"{sym}\n{name}",
                font=("Segoe UI Symbol", 22),
                width=4, height=2,
                bg="#F0D9B5" if color == "white" else "#333355",
                fg="#1a1a2e" if color == "white" else "#F0D9B5",
                bd=0, cursor="hand2",
                activebackground="#d4bc96",
                command=lambda l=letter: [chosen.set(l), dlg.destroy()]
            ).pack(side="left", padx=6)

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

        # Save game
        games = load_games()
        games.append({
            "date":      datetime.now().strftime("%Y-%m-%d %H:%M"),
            "result":    message,
            "moves":     self.move_log,
            "positions": [[[list(sq) if sq else None for sq in row]
                           for row in pos] for pos in self.positions]
        })
        save_games(games)

        def back():
            popup.destroy()
            self.master._show_main_menu()

        popup = tk.Toplevel(self)
        popup.title("Game Over")
        popup.configure(bg="#1a1a2e")
        popup.resizable(False, False)
        popup.grab_set()

        tk.Label(popup, text=message, font=("Georgia", 16, "bold"),
                 bg="#1a1a2e", fg="#F0D9B5", padx=30, pady=20).pack()
        tk.Button(popup, text="Back to Menu", font=("Georgia", 12),
                  bg="#F0D9B5", fg="#1a1a2e", bd=0, padx=16, pady=8,
                  cursor="hand2", command=back).pack(pady=(0, 20))

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
        super().__init__(master, bg="#1a1a2e")
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

        self.index     = 0
        self.total     = len(self.positions)
        self._auto_job = None   # after() id for auto-play

        self._build_ui()
        self._draw()

    # ── UI ─────────────────────────────────────
    def _build_ui(self):
        top = tk.Frame(self, bg="#1a1a2e")
        top.pack(fill="x", padx=10, pady=6)

        tk.Button(top, text="← Back", font=("Georgia", 11),
                  bg="#333355", fg="#F0D9B5", bd=0, padx=10, pady=4,
                  cursor="hand2", activebackground="#444466",
                  command=self._back).pack(side="left")

        self.status_var = tk.StringVar(value="Start position")
        tk.Label(top, textvariable=self.status_var,
                 font=("Georgia", 13, "bold"), bg="#1a1a2e", fg="#F0D9B5").pack(side="left", padx=20)

        main = tk.Frame(self, bg="#1a1a2e")
        main.pack(padx=10, pady=4)

        canvas_size = SQUARE_SIZE * 8 + BOARD_OFFSET * 2
        self.canvas = tk.Canvas(main, width=canvas_size, height=canvas_size,
                                bg="#1a1a2e", bd=0, highlightthickness=0)
        self.canvas.pack(side="left")

        # Right panel: move list + controls
        right = tk.Frame(main, bg="#0d0d1a", width=200)
        right.pack(side="left", fill="y", padx=(12,0))
        right.pack_propagate(False)

        tk.Label(right, text="Moves", font=("Georgia", 12, "bold"),
                 bg="#0d0d1a", fg="#F0D9B5").pack(pady=8)

        self.move_list = tk.Listbox(right, font=("Courier", 10),
                                    bg="#0d0d1a", fg="#ccc", bd=0,
                                    highlightthickness=0, activestyle="none",
                                    selectbackground="#B58863", selectforeground="#1a1a2e")
        self.move_list.pack(fill="both", expand=True, padx=6)
        self.move_list.bind("<<ListboxSelect>>", self._on_list_select)

        # Populate move list
        for i in range(0, len(self.moves), 2):
            n = i // 2 + 1
            w = self.moves[i]
            bl = self.moves[i+1] if i+1 < len(self.moves) else ""
            self.move_list.insert("end", f"  {n:>3}. {w:<8} {bl}")

        # Controls
        ctrl = tk.Frame(right, bg="#0d0d1a")
        ctrl.pack(pady=10)

        btn = dict(font=("Segoe UI Symbol", 16), bd=0, bg="#1a1a2e",
                   fg="#F0D9B5", activebackground="#333355",
                   activeforeground="#F0D9B5", cursor="hand2", width=3)

        tk.Button(ctrl, text="|◀", command=self._go_start, **btn).grid(row=0, column=0, padx=2)
        tk.Button(ctrl, text="◀",  command=self._prev,     **btn).grid(row=0, column=1, padx=2)
        self.play_btn = tk.Button(ctrl, text="▶", command=self._toggle_auto, **btn)
        self.play_btn.grid(row=0, column=2, padx=2)
        tk.Button(ctrl, text="▶",  command=self._next,     **btn).grid(row=0, column=3, padx=2)
        tk.Button(ctrl, text="▶|", command=self._go_end,   **btn).grid(row=0, column=4, padx=2)

        # Speed slider
        speed_frame = tk.Frame(right, bg="#0d0d1a")
        speed_frame.pack(pady=(0,8))
        tk.Label(speed_frame, text="Speed", font=("Georgia", 9),
                 bg="#0d0d1a", fg="#888").pack()
        self.speed_var = tk.IntVar(value=1000)
        tk.Scale(speed_frame, from_=300, to=2000, orient="horizontal",
                 variable=self.speed_var, resolution=100,
                 bg="#0d0d1a", fg="#F0D9B5", troughcolor="#333355",
                 highlightthickness=0, showvalue=False,
                 length=160).pack()

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
                    fg = "#FFFFFF" if piece[0] == "white" else "#1a1a2e"
                    self.canvas.create_text(
                        (x1+x2)//2, (y1+y2)//2,
                        text=sym, font=("Segoe UI Symbol", 38), fill=fg
                    )

        # Labels
        for i in range(8):
            lx = BOARD_OFFSET + i * SQUARE_SIZE + SQUARE_SIZE // 2
            self.canvas.create_text(lx, BOARD_OFFSET - 14, text="abcdefgh"[i],
                                    font=("Georgia", 10), fill="#888")
            self.canvas.create_text(lx, BOARD_OFFSET + 8*SQUARE_SIZE + 14, text="abcdefgh"[i],
                                    font=("Georgia", 10), fill="#888")
            ly = BOARD_OFFSET + i * SQUARE_SIZE + SQUARE_SIZE // 2
            self.canvas.create_text(BOARD_OFFSET - 16, ly, text=str(8-i),
                                    font=("Georgia", 10), fill="#888")
            self.canvas.create_text(BOARD_OFFSET + 8*SQUARE_SIZE + 16, ly, text=str(8-i),
                                    font=("Georgia", 10), fill="#888")

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
