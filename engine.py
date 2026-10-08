"""Experimental UCI bridge. The normal backend is exclusively Allie's Rust calibrated search."""
import os
import sys
import traceback
import threading
import time
from pathlib import Path

# Keep Python libraries' prints away from the UCI pipe.
OUT = sys.stdout
sys.stdout = sys.stderr
import chess

LOCK = threading.Lock()
def send(s):
    with LOCK:
        OUT.write(s.replace("\n", " ") + "\n")
        OUT.flush()

OPTIONS = {
    "uci_elo": [1500, 800, 2600, "UCI_Elo"],
    "opponentelo": [1500, 0, 3000, "OpponentElo"],
    "basetime": [180, 0, 10800, "BaseTime"],
    "moveoverhead": [100, 0, 5000, "MoveOverhead"],
}
def position(args):
    if not args:
        raise ValueError("position is empty")
    if args[0] == "startpos":
        board, i = chess.Board(), 1
    elif args[0] == "fen" and len(args) >= 7:
        board, i = chess.Board(" ".join(args[1:7])), 7
        if board.fen() != chess.Board().fen():
            raise ValueError("Only the starting FEN plus full moves is supported")
    else:
        raise ValueError("Expected startpos or starting FEN")
    moves = []
    if i < len(args):
        if args[i] != "moves":
            raise ValueError("Expected moves")
        moves = args[i + 1:]
    for move in moves:
        board.push_uci(move)
    if len(moves) > 1013:
        raise ValueError("Allie context limit: at most 1013 plies before search")
    return board, moves

def limits(args):
    values, roots, flags = {}, [], set()
    numeric = {"wtime", "btime", "winc", "binc", "movetime", "movestogo", "nodes"}
    keywords = numeric | {"searchmoves", "infinite", "ponder", "depth", "mate"}
    i = 0
    while i < len(args):
        key = args[i]
        i += 1
        if key in {"depth", "mate"}:
            raise ValueError("depth/mate search is unsupported; use clocks or movetime")
        if key in numeric:
            if i == len(args):
                raise ValueError("Missing value for " + key)
            value = int(args[i])
            if value < 0 or (key in {"nodes", "movestogo"} and value == 0):
                raise ValueError("Invalid value for " + key)
            values[key] = value
            i += 1
        elif key in {"infinite", "ponder"}:
            flags.add(key)
        elif key == "searchmoves":
            while i < len(args) and args[i] not in keywords:
                roots.append(args[i])
                i += 1
    if roots:
        raise ValueError("searchmoves is unsupported by this calibrated bridge")
    return values, flags

class Adapter:
    def __init__(self):
        self.board, self.moves = chess.Board(), []
        self.valid = True
        self.thread = None
        self.stop = threading.Event()
        self.ponderhit = threading.Event()
        self.engine = self.game = self.searcher = None
        self.key = None
        self.quit = False

    def load(self):
        if self.engine is not None:
            return
        from backend_check import check_backend
        check_backend()
        import torch
        import allie_fast
        from allie.lichess.model import Model
        from allie.lichess.fastrs import RustFast
        from allie.lichess.engine import Engine
        from allie.lichess.treers import KL
        from allie.lichess import calibration
        if not hasattr(allie_fast, "uci_stop"):
            raise RuntimeError("Missing UCI cancellation patch")
        threads = int(os.environ.get("ALLIE_THREADS", min(8, os.cpu_count() or 1)))
        torch.set_num_threads(threads)
        path = Path(__file__).with_name("model-path.txt").read_text().strip()
        model = Model(path, device="cpu", dtype=torch.bfloat16,
                      int8=True, backend="rust", threads=threads)
        if not isinstance(model.fast, RustFast):
            raise RuntimeError("Calibrated mode requires the Rust backend")
        torch.set_num_threads(1)
        self.engine = Engine(model)
        self.searcher = KL(calibration.GROW, calibration.READ, views=calibration.VIEWS)
        send("info string backend=rust mode=calibrated")

    def cancel(self, wait=True):
        self.stop.set()
        lib = sys.modules.get("allie_fast")
        if lib is not None and hasattr(lib, "uci_stop"):
            lib.uci_stop(True)
        if wait and self.thread:
            self.thread.join()
            self.thread = None

    def go(self, values, flags):
        self.cancel()
        self.load()
        import allie_fast
        allie_fast.uci_stop(False)
        self.stop.clear()
        self.ponderhit.clear()
        self.thread = threading.Thread(target=self.work,
            args=(values, flags), daemon=True)
        self.thread.start()

    def work(self, values, flags):
        try:
            self.search(values, flags)
        except Exception as exc:
            traceback.print_exc(file=sys.stderr)
            sys.stderr.flush()
            send("info string ERROR " + str(exc))
            # A model/backend failure is not a chess move or resignation.
            os._exit(1)

    def search(self, values, flags):
        import torch
        from allie.lichess.engine import Game, Play, calibrated
        from allie.lichess import behaviour
        from allie.lichess.tokens import HEADER, fill
        start = time.monotonic()
        white = self.board.turn == chess.WHITE
        side = 0 if white else 1
        clocks = [values.get(k) for k in ("wtime", "btime")]
        clocks = [None if x is None else x / 1000 for x in clocks]
        incs = [values.get(k, 0) / 1000 for k in ("winc", "binc")]
        clock = clocks[side]
        overhead = OPTIONS["moveoverhead"][0] / 1000
        allowed = float("inf")
        if clock is not None:
            allowed = max(0, clock - overhead)
            if "movestogo" in values:
                allowed = min(allowed, clock / values["movestogo"] + incs[side])
        if "movetime" in values:
            allowed = min(allowed, max(0, values["movetime"] / 1000 - overhead))
        deadline = start + allowed

        # The upstream model has one base time and one increment header.
        # An asymmetric increment is represented as unknown in the header;
        # exact side-specific increments still drive clock features and timing.
        inc = incs[0] if incs[0] == incs[1] and incs[0].is_integer() else None
        inc = int(inc) if inc is not None and inc <= 180 else None
        elo = OPTIONS["uci_elo"][0]
        opp = OPTIONS["opponentelo"][0] or elo
        ratings = (elo, opp) if white else (opp, elo)
        base = OPTIONS["basetime"][0] or None
        key = (ratings, base, inc, tuple(incs))
        if self.game is None or self.key != key:
            class TimedGame(Game):
                def features(g):
                    cs = fill(g.clocks, g.base)
                    result = [[-1, -1, -1] for _ in g.tokens]
                    for p in range(HEADER - 1, len(g.tokens)):
                        k = p - HEADER + 1
                        def c(j):
                            return (g.base if g.base is not None else -1) if j < 0 else (
                                cs[j] if cs[j] is not None else -1)
                        own, other = c(k - 2), c(k - 1)
                        previous = -1
                        if k >= 4 and c(k - 4) >= 0 and own >= 0:
                            previous = max(-1, c(k - 4) - own + g.incs[k % 2])
                        result[p] = [own, other, previous]
                    # UCI reports the current snapshot, not post-move event times.
                    k = len(g.moves) % 2
                    for j, v in enumerate((g.current[k], g.current[1-k])):
                        if v is not None:
                            result[-1][j] = v
                    return result

                def think(g, play, clock, distribution):
                    t = behaviour.think(distribution, g.rng, clock,
                                        g.incs[len(g.moves) % 2],
                                        len(g.moves), play.lag)
                    return min(t, max(0, g.deadline - time.monotonic()))

            speedtime = (base or 180) + 40 * max(incs)
            speed = "bullet" if speedtime < 180 else "blitz" if speedtime < 480 else (
                "rapid" if speedtime < 1500 else "classical")
            self.game = TimedGame(self.engine, *ratings, base, inc, speed=speed, seed=0)
            self.key = key
        g = self.game
        g.incs, g.current, g.deadline = incs, clocks, deadline
        g.update(self.moves, *clocks)
        if self.board.is_game_over():
            send("bestmove 0000")
            return
        play = Play(mode="calibrated", rating=elo, resign=False, draws=False, lag=0)
        evaluated = 0
        def search(game, budget, end):
            nonlocal evaluated
            if self.stop.is_set():
                return None
            budget = min(budget, values.get("nodes", budget))
            result = self.searcher(game, budget, min(end, deadline))
            evaluated = game.last_search.get("evaluated", 0)
            return result
        with torch.inference_mode():
            # Direct call avoids Game.decide's random context-overflow fallback.
            decision = calibrated(g, play, search, clock)
        if "infinite" in flags or "ponder" in flags:
            while not self.stop.wait(0.02):
                if "ponder" in flags and self.ponderhit.is_set():
                    break
        else:
            self.stop.wait(max(0, min(deadline, start + decision.think) - time.monotonic()))
        elapsed = int(1000 * (time.monotonic() - start))
        send(f"info nodes {evaluated} time {elapsed} pv {decision.move}")
        send(f"info string calibrated rust_leaves={evaluated} cut={decision.cut}")
        if not self.quit:
            send("bestmove " + decision.move)

    def run(self):
        for line in sys.stdin:
            words = line.split()
            if not words:
                continue
            cmd, args = words[0], words[1:]
            try:
                if cmd == "uci":
                    send("id name Allie 2.0 Calibrated NixOS experimental")
                    send("id author Yiming Zhang; UCI bridge")
                    for value, low, high, name in OPTIONS.values():
                        send(f"option name {name} type spin default {value} min {low} max {high}")
                    send("option name Ponder type check default false")
                    send("uciok")
                elif cmd == "isready":
                    self.load()
                    send("readyok")
                elif cmd == "setoption":
                    self.cancel()
                    lower = [x.lower() for x in args]
                    at = lower.index("value")
                    name = " ".join(args[1:at]).lower()
                    if name == "ponder":
                        continue
                    if name not in OPTIONS:
                        send("info string unknown option " + name)
                        continue
                    value = int(" ".join(args[at+1:]))
                    spec = OPTIONS[name]
                    if not spec[1] <= value <= spec[2]:
                        raise ValueError("Option out of range")
                    spec[0] = value
                    self.game = None
                elif cmd == "ucinewgame":
                    self.cancel()
                    self.game = None
                    self.board, self.moves, self.valid = chess.Board(), [], True
                elif cmd == "position":
                    self.cancel()
                    self.valid = False
                    self.board, self.moves = position(args)
                    self.valid = True
                elif cmd == "go":
                    if not self.valid:
                        raise ValueError("No supported position")
                    self.go(*limits(args))
                elif cmd == "stop":
                    self.cancel(wait=False)
                elif cmd == "ponderhit":
                    self.ponderhit.set()
                elif cmd == "quit":
                    break
                # debug, register and unknown optional commands are ignored.
            except Exception as exc:
                traceback.print_exc(file=sys.stderr)
                sys.stderr.flush()
                send("info string ERROR " + str(exc))
                # Never play from an old position after rejecting a go command.
                if cmd in {"go", "isready"}:
                    self.quit = True
                    self.cancel(wait=False)
                    return 1
        self.quit = True
        self.cancel(wait=False)
        if self.thread:
            self.thread.join(timeout=2)
        return 0

if __name__ == "__main__":
    os._exit(Adapter().run())
