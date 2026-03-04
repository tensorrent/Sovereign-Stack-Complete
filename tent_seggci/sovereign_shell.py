#!/usr/bin/env python3
"""
sovereign_shell.py — Interactive Sovereign Intelligence Shell
=============================================================
Container entrypoint. Loads the full stack, starts a session,
and provides an interactive REPL for querying the intelligence.

Environment variables (set by Docker):
  TRINITY_LIB     path to libtrinity.so
  SOVEREIGN_SDK   path to the SDK source tree
  SEGGCI_WS       path to the SEGGCI workspace (cognitive organs)
  MODE            GOD_MODE enables full diagnostic output

Usage inside container:
  python sovereign_shell.py                  # interactive
  python sovereign_shell.py --seed myname    # named session
  python sovereign_shell.py --demo           # run built-in demo
"""

import os
import sys
import time
import json
import ctypes
import argparse
import readline  # history + line editing in REPL

# ── Path setup ────────────────────────────────────────────────────────────────

SDK_PATH = os.environ.get("SOVEREIGN_SDK", os.path.dirname(__file__))
WS_PATH  = os.environ.get("SEGGCI_WS",    "/app/seggci_workspace")
LIB_PATH = os.environ.get("TRINITY_LIB",  os.path.join(SDK_PATH, "libtrinity.so"))
MODE     = os.environ.get("MODE", "NORMAL")
GOD_MODE = (MODE == "GOD_MODE")

for p in [SDK_PATH, WS_PATH]:
    if p not in sys.path and os.path.isdir(p):
        sys.path.insert(0, p)

# ── Load trinity library ──────────────────────────────────────────────────────

def load_trinity(lib_path: str):
    """Load libtrinity.so and configure ctypes signatures."""
    if not os.path.exists(lib_path):
        print(f"[FATAL] libtrinity.so not found at: {lib_path}")
        print(f"        Set TRINITY_LIB or ensure the build stage completed.")
        sys.exit(1)
    lib = ctypes.CDLL(lib_path)

    # BRA exports
    lib.bra_eigen_charge.restype  = ctypes.c_int32
    lib.bra_eigen_charge.argtypes = [
        ctypes.c_char_p, ctypes.c_size_t,
        ctypes.POINTER(ctypes.c_uint64),
        ctypes.POINTER(ctypes.c_int64),
        ctypes.POINTER(ctypes.c_int64),
    ]
    lib.bra_resonance_score.restype  = ctypes.c_int32
    lib.bra_resonance_score.argtypes = [
        ctypes.c_uint64, ctypes.c_int64, ctypes.c_int64,
        ctypes.c_uint64, ctypes.c_int64, ctypes.c_int64,
    ]
    lib.bra_verify_f369_table.restype = ctypes.c_int32
    lib.bra_verify.restype            = ctypes.c_double

    # Vexel exports
    lib.vexel_new.restype     = ctypes.c_void_p
    lib.vexel_new.argtypes    = [ctypes.c_char_p, ctypes.c_size_t, ctypes.c_uint64]
    lib.vexel_free.argtypes   = [ctypes.c_void_p]
    lib.vexel_record.restype  = ctypes.c_uint64
    lib.vexel_record.argtypes = [
        ctypes.c_void_p, ctypes.c_uint64,
        ctypes.c_uint16, ctypes.c_uint8, ctypes.c_uint8,
    ]
    lib.vexel_root.restype    = ctypes.c_uint64
    lib.vexel_root.argtypes   = [ctypes.c_void_p]
    lib.vexel_event_count.restype  = ctypes.c_uint64
    lib.vexel_event_count.argtypes = [ctypes.c_void_p]
    lib.vexel_mixdown.argtypes     = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_uint64)]
    lib.vexel_export.argtypes      = [
        ctypes.c_void_p, ctypes.c_char_p, ctypes.POINTER(ctypes.c_size_t)
    ]
    lib.vexel_restore.restype  = ctypes.c_void_p
    lib.vexel_restore.argtypes = [
        ctypes.c_char_p, ctypes.c_size_t, ctypes.c_uint64,
        ctypes.c_char_p, ctypes.c_size_t,
    ]
    lib.vexel_ulam_pos.argtypes = [
        ctypes.c_void_p,
        ctypes.POINTER(ctypes.c_int32), ctypes.POINTER(ctypes.c_int32),
    ]
    return lib


# ── Sovereign session ─────────────────────────────────────────────────────────

class SovereignSession:
    """
    A live sovereign intelligence session.
    Wraps the trinity library, TENT engine (if available), and vexel scroll.
    """
    MIXDOWN_DIR = os.path.join(SDK_PATH, "mixdowns")
    MAX_EXPORT  = 1 << 22  # 4MB scroll buffer

    def __init__(self, seed: str, lib, capacity: int = 10007):
        self.seed     = seed
        self.lib      = lib
        self.capacity = capacity
        self._ptr     = lib.vexel_new(seed.encode(), len(seed), capacity)
        self._tent    = None
        self._boot_time = time.time()
        self._queries   = 0

        # Try to load TENT engine
        try:
            from tent_v9 import TENTEngineV63, populate_all_wells
            self._tent = TENTEngineV63()
            populate_all_wells(self._tent)
        except ImportError:
            pass  # TENT not available — vexel-only mode

        os.makedirs(self.MIXDOWN_DIR, exist_ok=True)

    def eigen(self, text: str):
        """Compute BRA eigen charge for text."""
        b   = text.lower().encode()
        if not b:
            return (0, 0, 0)
        h   = ctypes.c_uint64(0)
        tr  = ctypes.c_int64(0)
        dt  = ctypes.c_int64(0)
        ok  = self.lib.bra_eigen_charge(b, len(b),
                  ctypes.byref(h), ctypes.byref(tr), ctypes.byref(dt))
        return (h.value, tr.value, dt.value) if ok else (0, 0, 0)

    def query(self, text: str) -> dict:
        """Run a query: eigen charge → TENT inference → vexel record."""
        h, tr, dt = self.eigen(text)
        self._queries += 1

        result = {"query": text, "root": self.root(), "eigen": h}

        if self._tent:
            r = self._tent.query(text)
            answer = r.get("answer", "—") if r else "—"
            score  = r.get("score", 0)    if r else 0
            ev_type = 1 if score >= 2 else (2 if score >= 1 else 3)
            result.update({"answer": answer, "score": score})
        else:
            ev_type = 2
            result["answer"] = "[TENT engine not loaded — vexel-only mode]"

        pin = self.lib.vexel_record(self._ptr, h, 0, ev_type, 0)
        result["root"]    = self.root()
        result["pin"]     = pin
        return result

    def root(self) -> int:
        return self.lib.vexel_root(self._ptr)

    def ulam(self) -> tuple:
        x, y = ctypes.c_int32(0), ctypes.c_int32(0)
        self.lib.vexel_ulam_pos(self._ptr, ctypes.byref(x), ctypes.byref(y))
        return (x.value, y.value)

    def stats(self) -> dict:
        return {
            "seed":     self.seed,
            "root":     f"0x{self.root():016x}",
            "events":   self.lib.vexel_event_count(self._ptr),
            "queries":  self._queries,
            "ulam":     self.ulam(),
            "uptime_s": round(time.time() - self._boot_time, 1),
            "tent":     self._tent is not None,
        }

    def export(self) -> bytes:
        buf = ctypes.create_string_buffer(self.MAX_EXPORT)
        sz  = ctypes.c_size_t(0)
        self.lib.vexel_export(self._ptr, buf, ctypes.byref(sz))
        return bytes(buf[:sz.value])

    def save_mixdown(self) -> str:
        """Write scroll to mixdowns directory. Returns path."""
        ts   = int(time.time())
        path = os.path.join(self.MIXDOWN_DIR, f"{self.seed}_{ts}.scroll")
        with open(path, "wb") as f:
            f.write(self.export())
        return path

    def __del__(self):
        if hasattr(self, '_ptr') and self._ptr:
            self.lib.vexel_free(self._ptr)


# ── REPL ──────────────────────────────────────────────────────────────────────

BANNER = """
╔══════════════════════════════════════════════════════════════╗
║  SOVEREIGN INTELLIGENCE SHELL                                ║
║  Trinity Core  ·  BRA Algebra  ·  Vexel Identity            ║
║  Type /help for commands  ·  Ctrl-D or /exit to leave        ║
╚══════════════════════════════════════════════════════════════╝"""

HELP = """
Commands:
  /stats          show session statistics
  /root           show current Merkle root
  /ulam           show current Ulam coordinate
  /save           save scroll to mixdowns/
  /god            toggle GOD_MODE diagnostic output
  /demo           run built-in demonstration
  /exit  or Ctrl-D  end session and save scroll
  
  Anything else is treated as a query to the intelligence.
"""

def run_demo(session: SovereignSession):
    """Built-in demonstration — exercises the full stack."""
    queries = [
        "what is entropy",
        "explain eigenvalues in quantum mechanics",
        "what is the pythagorean theorem",
        "how does a Merkle tree work",
        "what is the Ulam spiral",
    ]
    print("\n── Running demonstration ──────────────────────────")
    for q in queries:
        r = session.query(q)
        root_short = f"0x{r['root']:08x}"
        print(f"  Q: {q}")
        print(f"  A: {r['answer'][:80]}{'…' if len(r.get('answer','')) > 80 else ''}")
        print(f"     root={root_short}  pin={r['pin']}")
        print()
    print(f"── Demo complete  {len(queries)} queries  root=0x{session.root():016x}")


def run_repl(session: SovereignSession, god_mode: bool):
    """Interactive REPL loop."""
    global GOD_MODE
    GOD_MODE = god_mode
    print(BANNER)
    print(f"\n  Session : {session.seed}")
    print(f"  Root    : 0x{session.root():016x}")
    print(f"  TENT    : {'loaded' if session._tent else 'not available'}")
    print(f"  Mode    : {'GOD_MODE' if GOD_MODE else 'NORMAL'}\n")

    while True:
        try:
            line = input("sovereign> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break

        if not line:
            continue

        if line == "/exit":
            break
        elif line == "/help":
            print(HELP)
        elif line == "/stats":
            st = session.stats()
            for k, v in st.items():
                print(f"  {k:<12} {v}")
        elif line == "/root":
            print(f"  0x{session.root():016x}")
        elif line == "/ulam":
            x, y = session.ulam()
            print(f"  ({x}, {y})")
        elif line == "/save":
            path = session.save_mixdown()
            print(f"  Saved: {path}")
        elif line == "/god":
            GOD_MODE = not GOD_MODE
            print(f"  GOD_MODE: {'ON' if GOD_MODE else 'OFF'}")
        elif line == "/demo":
            run_demo(session)
        else:
            r = session.query(line)
            print(f"\n  {r['answer']}")
            if GOD_MODE:
                print(f"  ─")
                print(f"  eigen=0x{r['eigen']:016x}  pin={r['pin']}")
                print(f"  root =0x{r['root']:016x}")
                score_lbl = {0:"MISS",1:"QUERY",2:"RESONANCE"}.get(r.get('score',0),"?")
                print(f"  event={score_lbl}")
            print()

    # Clean exit — save scroll
    path = session.save_mixdown()
    st   = session.stats()
    print(f"\n  Session complete")
    print(f"  Queries  : {st['queries']}")
    print(f"  Events   : {st['events']}")
    print(f"  Root     : {st['root']}")
    print(f"  Scroll   : {path}")
    print(f"\n  The scroll travels with the intelligence.")


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Sovereign Intelligence Shell")
    parser.add_argument("--seed",     default="sovereign",  help="Session seed identity")
    parser.add_argument("--capacity", default=10007, type=int, help="Vexel prime capacity")
    parser.add_argument("--demo",     action="store_true",   help="Run demo and exit")
    parser.add_argument("--god",      action="store_true",   help="Enable GOD_MODE output")
    parser.add_argument("--verify",   action="store_true",   help="Verify library and exit")
    args = parser.parse_args()

    lib = load_trinity(LIB_PATH)

    if args.verify:
        table_ok = lib.bra_verify_f369_table()
        wave_err  = lib.bra_verify()
        print(f"Trinity Core verification")
        print(f"  F369 table : {'PASS' if table_ok else 'FAIL'}")
        print(f"  Wave parity: {'PASS' if wave_err == 0.0 else f'err={wave_err:.2e}'}")
        sys.exit(0 if table_ok else 1)

    session = SovereignSession(args.seed, lib, args.capacity)

    if args.demo:
        run_demo(session)
        session.save_mixdown()
        sys.exit(0)

    run_repl(session, god_mode=args.god or GOD_MODE)


if __name__ == "__main__":
    main()
