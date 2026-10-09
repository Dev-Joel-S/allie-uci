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
        send("info string Lade Rust-Modul und PyTorch")
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
        send("info string Lade Modellgewichte und quantisiere INT8; das kann dauern")
        model = Model(path, device="cpu", dtype=torch.bfloat16,
                      int8=True, backend="rust", threads=threads)
        send("info string Modell geladen; initialisiere Calibrated-Suche")
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


import importlib
import sys
from pathlib import Path

def check_backend():
    try:
        lib = importlib.import_module("allie_fast")
    except ImportError as exc:
        raise RuntimeError(
            f"Cannot import allie_fast with {sys.executable}: {exc}. "
            "Run install.sh from the updated repository.") from exc
    expected = Path(__file__).resolve().parent / "python-packages"
    location = getattr(lib, "__file__", None)
    if not location or not Path(location).resolve().is_relative_to(expected.resolve()):
        raise RuntimeError(f"Wrong allie_fast location: {location}; expected {expected}")
    missing = [name for name in
               ("Engine", "Server", "Position", "KL", "Coverage", "place", "uci_stop")
               if not hasattr(lib, name)]
    if getattr(lib, "INTERFACE", None) != 2 or missing:
        raise RuntimeError(
            f"Incompatible allie_fast at {location}: "
            f"INTERFACE={getattr(lib, 'INTERFACE', None)}, missing={missing}. "
            "Run install.sh. The module does not require an attribute named fast.")
    lib.uci_stop(False)
    return lib


def stop_process(process):
    """Stop and reap a subprocess owned by this test."""
    import subprocess
    if process.poll() is None:
        process.terminate()
    try:
        process.wait(timeout=3)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=3)

def exit_with_parent():
    """Linux: even SIGKILL of a test parent must not orphan a model process."""
    parent = os.environ.get("ALLIE_TEST_PARENT")
    if parent is None:
        return
    import ctypes
    import signal
    libc = ctypes.CDLL(None, use_errno=True)
    if libc.prctl(1, signal.SIGKILL, 0, 0, 0) != 0:
        raise OSError(ctypes.get_errno(), "prctl(PR_SET_PDEATHSIG)")
    if os.getppid() != int(parent):
        os._exit(1)

def test_signal(signum, frame):
    raise SystemExit(128 + signum)


def wait_uci(q, process, prefix, timeout, transcript, output, heartbeat=5):
    import queue
    started = time.monotonic()
    end = started + timeout
    next_status = started + heartbeat
    lines = []
    while True:
        now = time.monotonic()
        if now >= end:
            raise TimeoutError(
                f"Keine Antwort {prefix!r} nach {timeout}s; "
                f"Prozesscode={process.poll()}. Siehe test-results/stderr.log")
        try:
            line = q.get(timeout=min(1, end - now))
        except queue.Empty:
            now = time.monotonic()
            if now >= next_status:
                print(f"Warte auf {prefix.strip()}: {now-started:.0f}s; "
                      f"Prozess {'läuft' if process.poll() is None else 'beendet'}",
                      file=output, flush=True)
                next_status = now + heartbeat
            continue
        if line is None:
            raise AssertionError(
                f"Engine beendet (code={process.poll()}); letzte Ausgabe={lines[-8:]}; "
                "siehe test-results/stderr.log")
        transcript.write("< " + line + "\n")
        lines.append(line)
        if line.startswith(("info string", "info nodes", "bestmove")):
            print(line, file=output, flush=True)
        if line.startswith("info string ERROR"):
            raise RuntimeError(line + "; siehe test-results/stderr.log")
        if line.startswith(prefix):
            return lines


def run_tests():
    import logging
    import os
    import queue
    import re
    import subprocess
    import sys
    import threading
    import time
    from pathlib import Path
    import chess
    import chess.engine
    import chess.pgn
    engine = sys.modules[__name__]
    
    ROOT = Path(__file__).resolve().parent
    COMMAND = [sys.executable, "-u", str(ROOT / "engine.py")]
    child_env = dict(os.environ, ALLIE_TEST_PARENT=str(os.getpid()))
    REPORT = ROOT / "test-results"
    REPORT.mkdir(exist_ok=True)
    
    # Parsing and legal-history regression tests, without loading the model.
    cases = [
        "e2e4 e7e5 g1f3 b8c6 f1b5 a7a6 b5a4 g8f6 e1g1",
        "e2e4 a7a6 e4e5 d7d5 e5d6",
        "a2a4 h7h5 a4a5 h5h4 a5a6 h4h3 a6b7 h3g2 b7a8q",
        "f2f3 e7e5 g2g4 d8h4",
    ]
    for moves in cases:
        board, history = engine.position(["startpos", "moves", *moves.split()])
        assert board.is_valid() and len(history) == len(moves.split())
    b1, _ = engine.position(["startpos", "moves", "e2e4"])
    b2, _ = engine.position(["fen", *chess.STARTING_FEN.split(), "moves", "e2e4"])
    assert b1 == b2
    for bad in (["startpos", "moves", "e2e5"], ["fen", *chess.Board.empty().fen().split()]):
        try:
            engine.position(bad)
        except ValueError:
            pass
        else:
            raise AssertionError("Invalid position accepted")
    v, f = engine.limits("wtime 9000 btime 8000 winc 1000 binc 2000 movestogo 10".split())
    assert v["binc"] == 2000 and v["movestogo"] == 10
    print("PASS: position parsing, castling, en passant, promotion, mate, clocks",
          file=engine.OUT, flush=True)
    if "--unit" in sys.argv:
        import io
        class Process:
            def poll(self):
                return None
        for received, expected in [
            (["readyok"], None),
            (["info string ERROR backend kaputt"], RuntimeError),
            ([None], AssertionError),
            ([], TimeoutError),
        ]:
            responses = queue.Queue()
            for line in received:
                responses.put(line)
            try:
                result = wait_uci(responses, Process(), "readyok", 0.03,
                                  io.StringIO(), io.StringIO())
                assert expected is None and result == ["readyok"]
            except (RuntimeError, AssertionError, TimeoutError) as exc:
                assert expected is not None and isinstance(exc, expected), str(exc)
        print("PASS: UCI wait, backend errors, process exit, timeout",
              file=engine.OUT, flush=True)
        return
    
    logging.basicConfig(filename=REPORT / "python-chess.log", level=logging.DEBUG,
                        format="%(asctime)s %(message)s")
    if "--game" in sys.argv:
        # Real Allie against real Stockfish, two separate UCI processes.
        game = chess.pgn.Game()
        game.headers.update(Event="Allie Rust calibrated integration test",
                            White="Allie 2.0", Black="Stockfish",
                            TimeControl="600+5")
        board, node = game.board(), game
        clocks = [600.0, 600.0]
        allie = chess.engine.SimpleEngine.popen_uci(COMMAND, timeout=600, env=child_env)
        sf = None
        searched = 0
        try:
            sf = chess.engine.SimpleEngine.popen_uci("stockfish", timeout=30)
            allie.configure({"UCI_Elo": 1500, "OpponentElo": 1500, "BaseTime": 600})
            allie.ping()
            sf.ping()
            for ply in range(1000):
                if board.is_game_over(claim_draw=True):
                    break
                side = 0 if board.turn else 1
                start = time.monotonic()
                limit = (chess.engine.Limit(white_clock=clocks[0], black_clock=clocks[1],
                         white_inc=5, black_inc=5) if side == 0
                         else chess.engine.Limit(time=0.05))
                r = (allie if side == 0 else sf).play(
                    board, limit, info=chess.engine.INFO_ALL)
                clocks[side] -= time.monotonic() - start
                if clocks[side] <= 0:
                    raise AssertionError(f"Flag fall at ply {ply}")
                assert r.move in board.legal_moves, "Illegal bestmove"
                if side == 0:
                    searched += r.info.get("nodes", 0)
                board.push(r.move)
                node = node.add_variation(r.move)
                node.set_clock(clocks[side] + 5)
                clocks[side] += 5
                (REPORT / "game.pgn").write_text(str(game) + "\n")
            assert board.is_game_over(claim_draw=True), "Ply cap reached: incomplete game"
            assert searched > 0, "No evidence of Rust search"
            game.headers["Result"] = board.result(claim_draw=True)
            (REPORT / "game.pgn").write_text(str(game) + "\n")
            print(f"PASS: complete game {game.headers['Result']}, Rust leaves {searched}",
                  file=engine.OUT, flush=True)
        finally:
            allie.close()
            if sf:
                sf.close()
    else:
        # Raw wire test also checks readiness during search and stop.
        transcript = (REPORT / "uci.log").open("w", buffering=1)
        errors = (REPORT / "stderr.log").open("w")
        p = subprocess.Popen(COMMAND, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE, text=True, bufsize=1, env=child_env,
                             start_new_session=True)
        q = queue.Queue()
        def reader():
            for line in p.stdout:
                q.put(line.strip())
            q.put(None)
        def error_reader():
            for line in p.stderr:
                errors.write(line)
                errors.flush()
                print(line.rstrip(), file=engine.OUT, flush=True)
        stderr_thread = threading.Thread(target=error_reader, daemon=True)
        stderr_thread.start()
        threading.Thread(target=reader, daemon=True).start()
        def send(s):
            transcript.write("> " + s + "\n")
            try:
                p.stdin.write(s + "\n")
                p.stdin.flush()
            except BrokenPipeError as exc:
                raise AssertionError(f"Engine pipe closed; see {REPORT / 'stderr.log'}") from exc
        def until(prefix, timeout=120):
            return wait_uci(q, p, prefix, timeout, transcript, engine.OUT)
        try:
            send("uci")
            until("uciok")
            print("Lade echte Allie-Engine (Zeitlimit 600s)...", file=engine.OUT, flush=True)
            send("isready")
            until("readyok", 600)
            send("ucinewgame")
            send("setoption name UCI_Elo value 1800")
            total = 0
            for test_number in range(1, 5):
                print(f"Teste Rust-Suche {test_number}/4...", file=engine.OUT, flush=True)
                send("position fen " + chess.STARTING_FEN + " moves e2e4 e7e5 g1f3 b8c6")
                send("go wtime 180000 btime 180000 winc 2000 binc 2000 movetime 5000")
                lines = until("bestmove ")
                board = chess.Board()
                for move in "e2e4 e7e5 g1f3 b8c6".split():
                    board.push_uci(move)
                assert chess.Move.from_uci(lines[-1].split()[1]) in board.legal_moves
                total += sum(int(m.group(1)) for s in lines
                             if (m := re.search(r"rust_leaves=(\d+)", s)))
            assert total > 0, "Rust search never evaluated leaves"
            send("go infinite")
            send("isready")
            until("readyok", 5)
            start = time.monotonic()
            send("stop")
            until("bestmove ", 30)
            latency = time.monotonic() - start
            # Current native inference batches cannot be preempted.
            assert latency < 2, f"stop took {latency:.3f}s (target <2s)"
            send("position startpos moves f2f3 e7e5 g2g4 d8h4")
            send("go movetime 50")
            assert until("bestmove ")[-1] == "bestmove 0000"
            send("quit")
            assert p.wait(timeout=10) == 0
            print(f"PASS: real model/UCI, Rust leaves={total}, stop={latency:.3f}s",
                  file=engine.OUT, flush=True)
        finally:
            stop_process(p)
            stderr_thread.join(timeout=2)
            transcript.close()
            if not stderr_thread.is_alive():
                errors.close()
    
if __name__ == "__main__":
    import signal
    exit_with_parent()
    if "--unit" in sys.argv or "--test" in sys.argv or "--game" in sys.argv:
        for sig in (signal.SIGTERM, signal.SIGHUP):
            signal.signal(sig, test_signal)
        try:
            run_tests()
        except KeyboardInterrupt:
            raise SystemExit(130)
    else:
        os._exit(Adapter().run())
