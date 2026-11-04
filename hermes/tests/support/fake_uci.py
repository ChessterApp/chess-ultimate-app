"""A stand-in UCI engine for the engine pool's fault tests (plan 31.10 P7a; tests/unit/test_p7_1031.py).

Speaks enough UCI for src/engine_pool.py and src/tools/stockfish._analyze_position. Behaviour by environment:
  FAKE_UCI_LOG    file: every command received is appended as "<pid> <command>", and "<pid> START" at start-up
  FAKE_UCI_MODE   normal (default) | die_on_go (exit at the first `go`) | die_once (exit at the first `go` of the first
                  process only, marker FAKE_UCI_LOG + ".died") | hang (a search ends only on `stop`) |
                  deaf (a search never ends, `stop` ignored)
  FAKE_UCI_PLY_MS ms per depth step of a depth search (default 1)
A search to depth D prints one `info` line per depth and line (score cp 10*line, depth d), then `bestmove e2e4`;
`go movetime M` searches M ms (a `depth` with it ends at whichever comes first); `stop` ends a search at once.
"""
import os
import queue
import sys
import threading
import time

LOG = os.environ.get("FAKE_UCI_LOG")
MODE = os.environ.get("FAKE_UCI_MODE", "normal")
PLY_MS = float(os.environ.get("FAKE_UCI_PLY_MS", "1"))
PID = os.getpid()


def log(text):
    if LOG:
        with open(LOG, "a") as fh:
            fh.write(f"{PID} {text}\n")


def out(text):
    sys.stdout.write(text + "\n")
    sys.stdout.flush()


def main():
    log("START")
    cmds: "queue.Queue" = queue.Queue()

    def _read():
        for line in sys.stdin:
            cmds.put(line.strip())
        cmds.put(None)

    threading.Thread(target=_read, daemon=True).start()
    multipv = 1
    while True:
        cmd = cmds.get()
        if cmd is None or cmd == "quit":
            log("QUIT" if cmd else "EOF")
            return
        log(cmd)
        if cmd == "uci":
            out("id name FakeUCI")
            out("uciok")
        elif cmd == "isready":
            out("readyok")
        elif cmd.startswith("setoption name MultiPV value "):
            multipv = int(cmd.rsplit(" ", 1)[1])
        elif cmd.startswith("go"):
            if MODE == "die_on_go":
                os._exit(3)
            if MODE == "die_once" and LOG and not os.path.exists(LOG + ".died"):
                open(LOG + ".died", "w").close()
                os._exit(3)
            parts = cmd.split()
            depth = int(parts[parts.index("depth") + 1]) if "depth" in parts else None
            movetime = int(parts[parts.index("movetime") + 1]) if "movetime" in parts else None
            started = time.monotonic()
            reached = 0
            stopped = False
            while True:
                if MODE not in ("hang", "deaf"):
                    if depth is not None and reached >= depth:
                        break
                    if movetime is not None and (time.monotonic() - started) * 1000 >= movetime:
                        break
                try:
                    nxt = cmds.get(timeout=PLY_MS / 1000.0)
                except queue.Empty:
                    nxt = ""
                if nxt is None:
                    return
                if nxt:
                    log(nxt)
                if nxt == "stop" and MODE != "deaf":
                    stopped = True
                    break
                if nxt == "isready":
                    out("readyok")
                if MODE in ("hang", "deaf"):
                    continue
                if reached < (depth if depth is not None else 30):
                    reached += 1
                    for k in range(1, multipv + 1):
                        out(f"info depth {reached} seldepth {reached} multipv {k} score cp {10 * k} nodes 100 "
                            f"pv e2e4 e7e5")
            log(f"END reached={reached} stopped={stopped}")
            out("bestmove e2e4 ponder e7e5")


if __name__ == "__main__":
    main()
