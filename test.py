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
import engine

ROOT = Path(__file__).resolve().parent
COMMAND = [sys.executable, "-u", str(ROOT / "engine.py")]
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
    raise SystemExit(0)

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
    allie = chess.engine.SimpleEngine.popen_uci(COMMAND, timeout=600)
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
        allie.quit()
        if sf:
            sf.quit()
else:
    # Raw wire test also checks readiness during search and stop.
    transcript = (REPORT / "uci.log").open("w", buffering=1)
    errors = (REPORT / "stderr.log").open("w")
    p = subprocess.Popen(COMMAND, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                         stderr=errors, text=True, bufsize=1)
    q = queue.Queue()
    def reader():
        for line in p.stdout:
            q.put(line.strip())
        q.put(None)
    threading.Thread(target=reader, daemon=True).start()
    def send(s):
        transcript.write("> " + s + "\n")
        p.stdin.write(s + "\n")
        p.stdin.flush()
    def until(prefix, timeout=120):
        lines, end = [], time.monotonic() + timeout
        while True:
            line = q.get(timeout=max(0.01, end - time.monotonic()))
            if line is None:
                raise AssertionError("Engine exited; see stderr.log")
            transcript.write("< " + line + "\n")
            lines.append(line)
            if line.startswith(prefix):
                return lines
            if time.monotonic() >= end:
                raise TimeoutError(prefix)
    try:
        send("uci")
        until("uciok")
        send("isready")
        until("readyok", 600)
        send("ucinewgame")
        send("setoption name UCI_Elo value 1800")
        total = 0
        for _ in range(4):
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
        if p.poll() is None:
            p.kill()
            p.wait()
        transcript.close()
        errors.close()
