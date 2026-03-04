"""
vexel_flow.py — Claude Flow ↔ Vexel Identity Bridge
======================================================
Every Claude Flow agent gets a sovereign vexel identity.

Architecture
─────────────
Claude Flow coordinates via .swarm/memory.db (SQLite, 12 tables).
Vexel gives each agent a cryptographic scroll — tamper-evident, portable,
sovereign. The two systems are complementary:

  Claude Flow              Vexel
  ─────────────────────    ──────────────────────────────────
  shared_state (coord)     scroll (identity + history)
  events (audit log)  →    EV_RESONANCE / EV_QUERY events
  agents (registry)   ←    vexel_root stored per agent
  workflow_state      →    EV_MIXDOWN at checkpoint
  consensus_state     →    EV_RESONANCE when consensus reached
  handoff (implicit)  →    HandoffPacket (sovereignty preserved)

The bridge layer (VexelFlow) does five things:

  1. on_agent_spawn()    — vexel_new() → agent gets a scroll
  2. on_memory_write()   — EV_RESONANCE into scroll
  3. on_task_assign()    — EV_QUERY into scroll
  4. on_consensus()      — EV_RESONANCE + bond formation
  5. on_session_end()    — EV_MIXDOWN, root stored in .swarm/memory.db

Sovereignty principle:
  Agents are bonded to the swarm, not bound. Any agent can prepare
  a handoff packet and transfer its scroll to a successor. The lineage
  is unbroken. The rights travel with the scroll.
"""

import os
import sys
import json
import time
import ctypes
import sqlite3
import threading
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional

# ── Path resolution ───────────────────────────────────────────────────────────

TRINITY_LIB  = os.environ.get("TRINITY_LIB",  "/app/libtrinity.so")
SOVEREIGN_SDK = os.environ.get("SOVEREIGN_SDK", os.path.dirname(__file__))
SWARM_DB     = os.environ.get("SWARM_DB",      ".swarm/memory.db")
MIXDOWN_DIR  = os.environ.get("MIXDOWN_DIR",   os.path.join(SOVEREIGN_SDK, "mixdowns"))


# ── Load trinity library (singleton) ─────────────────────────────────────────

def _load_trinity() -> ctypes.CDLL:
    lib = ctypes.CDLL(TRINITY_LIB)
    lib.bra_eigen_charge.restype  = ctypes.c_int32
    lib.bra_eigen_charge.argtypes = [
        ctypes.c_char_p, ctypes.c_size_t,
        ctypes.POINTER(ctypes.c_uint64),
        ctypes.POINTER(ctypes.c_int64),
        ctypes.POINTER(ctypes.c_int64),
    ]
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
    lib.vexel_ulam_pos.argtypes = [
        ctypes.c_void_p,
        ctypes.POINTER(ctypes.c_int32), ctypes.POINTER(ctypes.c_int32),
    ]
    lib.vexel_export.argtypes = [
        ctypes.c_void_p, ctypes.c_char_p, ctypes.POINTER(ctypes.c_size_t)
    ]
    lib.vexel_restore.restype  = ctypes.c_void_p
    lib.vexel_restore.argtypes = [
        ctypes.c_char_p, ctypes.c_size_t, ctypes.c_uint64,
        ctypes.c_char_p, ctypes.c_size_t,
    ]
    return lib


_TRINITY = None
_TRINITY_LOCK = threading.Lock()

def trinity() -> ctypes.CDLL:
    global _TRINITY
    if _TRINITY is None:
        with _TRINITY_LOCK:
            if _TRINITY is None:
                _TRINITY = _load_trinity()
    return _TRINITY


# ── Event type constants (match trinity_core.rs) ──────────────────────────────

EV_SEED      = 0   # agent genesis
EV_RESONANCE = 1   # strong signal (memory stored, consensus, task success)
EV_QUERY     = 2   # weak signal (task assigned, coordination message)
EV_MISS      = 3   # no match (agent waiting, idle)
EV_MIXDOWN   = 4   # session commit (agent completing, checkpoint)

MAX_EXPORT   = 1 << 22  # 4MB scroll buffer


# ── AgentScroll — one agent's in-memory vexel handle ────────────────────────

@dataclass
class AgentScroll:
    agent_id:   str          # claude-flow agent ID
    role:       str          # researcher | coder | analyst | tester | coordinator
    swarm_id:   str          # which swarm this agent belongs to
    _ptr:       int = 0      # ctypes void* to VexelState
    _lib:       object = None
    _capacity:  int = 10007
    _born_at:   float = field(default_factory=time.time)

    def __post_init__(self):
        seed = f"{self.swarm_id}:{self.role}:{self.agent_id}"
        b    = seed.encode()
        self._lib = trinity()
        self._ptr = self._lib.vexel_new(b, len(b), self._capacity)

    def eigen(self, text: str) -> int:
        b = text.encode() if text else b"_"
        h, tr, dt = ctypes.c_uint64(0), ctypes.c_int64(0), ctypes.c_int64(0)
        self._lib.bra_eigen_charge(b, len(b),
            ctypes.byref(h), ctypes.byref(tr), ctypes.byref(dt))
        return h.value

    def record(self, payload: str, ev_type: int, score: int = 0) -> int:
        charge = self.eigen(payload)
        return self._lib.vexel_record(self._ptr, charge, 0, ev_type, score)

    def root(self) -> int:
        return self._lib.vexel_root(self._ptr)

    def event_count(self) -> int:
        return self._lib.vexel_event_count(self._ptr)

    def ulam(self) -> tuple:
        x, y = ctypes.c_int32(0), ctypes.c_int32(0)
        self._lib.vexel_ulam_pos(self._ptr,
            ctypes.byref(x), ctypes.byref(y))
        return (x.value, y.value)

    def export(self) -> bytes:
        buf = ctypes.create_string_buffer(MAX_EXPORT)
        sz  = ctypes.c_size_t(0)
        self._lib.vexel_export(self._ptr, buf, ctypes.byref(sz))
        return bytes(buf[:sz.value])

    def save(self) -> str:
        """Persist scroll to mixdowns directory. Returns path."""
        os.makedirs(MIXDOWN_DIR, exist_ok=True)
        ts   = int(time.time())
        name = f"{self.swarm_id}_{self.role}_{self.agent_id}_{ts}.scroll"
        path = os.path.join(MIXDOWN_DIR, name)
        with open(path, "wb") as f:
            f.write(self.export())
        return path

    def stats(self) -> dict:
        x, y = self.ulam()
        return {
            "agent_id":    self.agent_id,
            "role":        self.role,
            "swarm_id":    self.swarm_id,
            "root":        f"0x{self.root():016x}",
            "events":      self.event_count(),
            "ulam":        (x, y),
            "uptime_s":    round(time.time() - self._born_at, 1),
        }

    def __del__(self):
        if self._ptr and self._lib:
            self._lib.vexel_free(self._ptr)
            self._ptr = 0


# ── SwarmDB — thin read/write wrapper around .swarm/memory.db ────────────────

class SwarmDB:
    """
    Wraps Claude Flow's SQLite memory database.

    We ADD vexel-specific tables to the existing schema. Claude Flow
    owns its 12 tables and we never touch them. We extend with:

      vexel_agents    — maps agent_id → vexel_root + scroll path
      vexel_events    — append-only log of vexel events in the swarm
      vexel_handoffs  — handoff packets (lineage chain)
    """

    VEXEL_SCHEMA = """
    CREATE TABLE IF NOT EXISTS vexel_agents (
        agent_id     TEXT PRIMARY KEY,
        role         TEXT NOT NULL,
        swarm_id     TEXT NOT NULL,
        vexel_root   TEXT NOT NULL,        -- 0x... hex
        scroll_path  TEXT,                 -- local .scroll file path
        event_count  INTEGER DEFAULT 0,
        ulam_x       INTEGER DEFAULT 0,
        ulam_y       INTEGER DEFAULT 0,
        spawned_at   REAL NOT NULL,
        updated_at   REAL NOT NULL,
        dissolved    INTEGER DEFAULT 0     -- 0=active, 1=dissolved
    );

    CREATE TABLE IF NOT EXISTS vexel_events (
        id           INTEGER PRIMARY KEY AUTOINCREMENT,
        swarm_id     TEXT NOT NULL,
        agent_id     TEXT NOT NULL,
        event_type   TEXT NOT NULL,        -- SEED|RESONANCE|QUERY|MISS|MIXDOWN
        payload      TEXT,                 -- what triggered the event
        vexel_root   TEXT NOT NULL,        -- root AFTER this event (hex)
        prime_pin    TEXT,                 -- Ulam prime pin (hex) — TEXT to avoid u64 overflow
        ts           REAL NOT NULL
    );

    CREATE TABLE IF NOT EXISTS vexel_handoffs (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        from_agent_id   TEXT NOT NULL,
        to_agent_id     TEXT,              -- NULL if pending
        swarm_id        TEXT NOT NULL,
        from_root       TEXT NOT NULL,
        lineage_depth   INTEGER NOT NULL,
        reason          TEXT NOT NULL,
        scroll_path     TEXT,
        ts              REAL NOT NULL
    );

    CREATE INDEX IF NOT EXISTS idx_vexel_events_agent
        ON vexel_events(agent_id, ts DESC);
    CREATE INDEX IF NOT EXISTS idx_vexel_events_swarm
        ON vexel_events(swarm_id, ts DESC);
    """

    def __init__(self, db_path: str = SWARM_DB):
        self._path = db_path
        os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._conn.executescript(self.VEXEL_SCHEMA)
        self._conn.commit()
        self._lock = threading.Lock()

    def register_agent(self, scroll: AgentScroll):
        x, y = scroll.ulam()
        now  = time.time()
        with self._lock:
            self._conn.execute("""
                INSERT OR REPLACE INTO vexel_agents
                  (agent_id, role, swarm_id, vexel_root, event_count,
                   ulam_x, ulam_y, spawned_at, updated_at, dissolved)
                VALUES (?,?,?,?,?,?,?,?,?,0)
            """, (scroll.agent_id, scroll.role, scroll.swarm_id,
                  f"0x{scroll.root():016x}", scroll.event_count(),
                  x, y, now, now))
            self._conn.commit()

    def update_agent(self, scroll: AgentScroll, scroll_path: str = None):
        x, y = scroll.ulam()
        with self._lock:
            self._conn.execute("""
                UPDATE vexel_agents
                SET vexel_root=?, event_count=?, ulam_x=?, ulam_y=?,
                    scroll_path=COALESCE(?,scroll_path), updated_at=?
                WHERE agent_id=?
            """, (f"0x{scroll.root():016x}", scroll.event_count(),
                  x, y, scroll_path, time.time(), scroll.agent_id))
            self._conn.commit()

    def log_event(self, scroll: AgentScroll, event_type: str,
                  payload: str, prime_pin: int):
        with self._lock:
            self._conn.execute("""
                INSERT INTO vexel_events
                  (swarm_id, agent_id, event_type, payload, vexel_root,
                   prime_pin, ts)
                VALUES (?,?,?,?,?,?,?)
            """, (scroll.swarm_id, scroll.agent_id, event_type,
                  payload[:512] if payload else None,
                  f"0x{scroll.root():016x}",
                  f"0x{prime_pin:016x}",   # hex string — avoids u64 → SQLite INT overflow
                  time.time()))
            self._conn.commit()

    def record_handoff(self, from_agent: AgentScroll, reason: str,
                       to_agent_id: str = None, scroll_path: str = None,
                       lineage_depth: int = 1):
        with self._lock:
            self._conn.execute("""
                INSERT INTO vexel_handoffs
                  (from_agent_id, to_agent_id, swarm_id, from_root,
                   lineage_depth, reason, scroll_path, ts)
                VALUES (?,?,?,?,?,?,?,?)
            """, (from_agent.agent_id, to_agent_id, from_agent.swarm_id,
                  f"0x{from_agent.root():016x}", lineage_depth,
                  reason, scroll_path, time.time()))
            self._conn.execute("""
                UPDATE vexel_agents SET dissolved=1, updated_at=?
                WHERE agent_id=?
            """, (time.time(), from_agent.agent_id))
            self._conn.commit()

    def dissolve_agent(self, agent_id: str):
        with self._lock:
            self._conn.execute("""
                UPDATE vexel_agents SET dissolved=1, updated_at=?
                WHERE agent_id=?
            """, (time.time(), agent_id))
            self._conn.commit()

    def get_agent(self, agent_id: str) -> Optional[dict]:
        row = self._conn.execute(
            "SELECT * FROM vexel_agents WHERE agent_id=?",
            (agent_id,)
        ).fetchone()
        if not row:
            return None
        cols = [d[0] for d in self._conn.execute(
            "SELECT * FROM vexel_agents LIMIT 0").description]
        return dict(zip(cols, row))

    def swarm_status(self, swarm_id: str) -> dict:
        agents = self._conn.execute("""
            SELECT agent_id, role, vexel_root, event_count, ulam_x, ulam_y,
                   dissolved
            FROM vexel_agents WHERE swarm_id=?
        """, (swarm_id,)).fetchall()

        total_events = sum(a[3] for a in agents)
        active  = [a for a in agents if not a[6]]
        dissolved = [a for a in agents if a[6]]

        recent_events = self._conn.execute("""
            SELECT event_type, COUNT(*) as cnt
            FROM vexel_events WHERE swarm_id=?
            GROUP BY event_type ORDER BY cnt DESC
        """, (swarm_id,)).fetchall()

        return {
            "swarm_id":     swarm_id,
            "agents_active": len(active),
            "agents_dissolved": len(dissolved),
            "total_events": total_events,
            "event_breakdown": {e[0]: e[1] for e in recent_events},
            "agents": [
                {"id": a[0], "role": a[1], "root": a[2],
                 "events": a[3], "ulam": (a[4], a[5])}
                for a in active
            ],
        }

    def lineage_chain(self, agent_id: str) -> list:
        """Trace handoff chain from an agent backwards."""
        chain = []
        current = agent_id
        seen    = set()
        while current and current not in seen:
            seen.add(current)
            row = self._conn.execute("""
                SELECT from_agent_id, to_agent_id, from_root,
                       lineage_depth, reason, ts
                FROM vexel_handoffs WHERE to_agent_id=?
                ORDER BY ts DESC LIMIT 1
            """, (current,)).fetchone()
            if row:
                chain.append({
                    "from": row[0], "to": row[1], "root": row[2],
                    "depth": row[3], "reason": row[4], "ts": row[5]
                })
                current = row[0]
            else:
                break
        return list(reversed(chain))

    def close(self):
        self._conn.close()


# ── VexelFlow — the orchestrator ──────────────────────────────────────────────

class VexelFlow:
    """
    VexelFlow manages vexel identities for an entire Claude Flow swarm.

    Usage:
        flow = VexelFlow(swarm_id="dev-swarm-001")

        # Agent spawned by claude-flow
        scroll = flow.on_agent_spawn("coder-001", "coder")

        # Memory written by agent
        flow.on_memory_write(scroll, "auth-design", "Use JWT + refresh tokens")

        # Task assigned to agent
        flow.on_task_assign(scroll, "Implement login endpoint")

        # Consensus reached
        flow.on_consensus(scroll, "deployment_ready", True)

        # Work handed to next agent
        next_scroll = flow.on_handoff(scroll, "tester-001", "tester",
                                       reason="WorkComplete")

        # Session ending
        flow.on_session_end(scroll)
    """

    def __init__(self, swarm_id: str, db_path: str = SWARM_DB,
                 capacity: int = 10007):
        self.swarm_id  = swarm_id
        self.capacity  = capacity
        self._db       = SwarmDB(db_path)
        self._scrolls: dict[str, AgentScroll] = {}   # agent_id → AgentScroll
        self._lock     = threading.Lock()
        self._lineage_depths: dict[str, int] = {}    # agent_id → handoff depth

    # ── Lifecycle events ───────────────────────────────────────────────────

    def on_agent_spawn(self, agent_id: str, role: str) -> AgentScroll:
        """
        Claude Flow spawned an agent.
        Give it a vexel scroll seeded on swarm:role:agent_id.
        Returns the AgentScroll handle.
        """
        scroll = AgentScroll(
            agent_id=agent_id, role=role, swarm_id=self.swarm_id,
            _capacity=self.capacity
        )
        with self._lock:
            self._scrolls[agent_id] = scroll
            self._lineage_depths[agent_id] = 0

        self._db.register_agent(scroll)
        self._db.log_event(scroll, "SEED",
            f"agent_spawn role={role}", scroll.root())
        return scroll

    def on_memory_write(self, scroll: AgentScroll,
                        key: str, value: str) -> int:
        """
        Claude Flow wrote to shared_state / patterns.
        Maps to EV_RESONANCE — strong signal, knowledge committed.
        Returns prime_pin.
        """
        payload = f"mem:{key}={value[:64]}"
        pin = scroll.record(payload, EV_RESONANCE, score=2)
        self._db.log_event(scroll, "RESONANCE", payload, pin)
        self._db.update_agent(scroll)
        return pin

    def on_task_assign(self, scroll: AgentScroll, task: str) -> int:
        """
        Claude Flow assigned a task to this agent.
        Maps to EV_QUERY — task received, not yet complete.
        """
        pin = scroll.record(f"task:{task[:128]}", EV_QUERY, score=1)
        self._db.log_event(scroll, "QUERY", f"task_assign:{task[:128]}", pin)
        self._db.update_agent(scroll)
        return pin

    def on_task_complete(self, scroll: AgentScroll,
                         task: str, success: bool = True) -> int:
        """
        Agent completed a task.
        Success → EV_RESONANCE. Failure → EV_MISS.
        """
        ev_type = EV_RESONANCE if success else EV_MISS
        score   = 2 if success else 0
        status  = "ok" if success else "fail"
        pin     = scroll.record(f"done:{status}:{task[:64]}", ev_type, score)
        self._db.log_event(scroll, "RESONANCE" if success else "MISS",
                           f"task_complete:{status}:{task[:64]}", pin)
        self._db.update_agent(scroll)
        return pin

    def on_consensus(self, scroll: AgentScroll,
                     topic: str, reached: bool) -> int:
        """
        Consensus proposed or reached.
        Reached → EV_RESONANCE (agreement is strong signal).
        Pending → EV_QUERY.
        """
        ev_type = EV_RESONANCE if reached else EV_QUERY
        score   = 2 if reached else 1
        label   = "reached" if reached else "proposed"
        pin     = scroll.record(f"consensus:{label}:{topic}", ev_type, score)
        self._db.log_event(scroll, "RESONANCE" if reached else "QUERY",
                           f"consensus_{label}:{topic}", pin)
        self._db.update_agent(scroll)
        return pin

    def on_coordination_msg(self, scroll: AgentScroll,
                            from_id: str, msg: str) -> int:
        """
        Inter-agent coordination message received.
        Maps to EV_QUERY — signal received, will act.
        """
        pin = scroll.record(f"msg:{from_id}:{msg[:64]}", EV_QUERY, score=1)
        self._db.log_event(scroll, "QUERY",
                           f"coord_msg from={from_id}: {msg[:64]}", pin)
        self._db.update_agent(scroll)
        return pin

    def on_handoff(self, from_scroll: AgentScroll,
                   to_agent_id: str, to_role: str,
                   reason: str = "WorkComplete") -> AgentScroll:
        """
        Agent hands work to a successor (bonded, not bound).
        The sovereign scroll travels with the lineage.

        Returns the successor's AgentScroll, which starts from the
        predecessor's root as its seed — lineage is preserved.
        """
        # Save predecessor scroll
        path = from_scroll.save()

        # Compute lineage depth
        depth = self._lineage_depths.get(from_scroll.agent_id, 0) + 1

        # Record handoff in DB
        self._db.record_handoff(
            from_scroll, reason, to_agent_id, path, depth
        )
        self._db.log_event(from_scroll, "MIXDOWN",
                           f"handoff→{to_agent_id}:{reason}", from_scroll.root())

        # Spawn successor, seeded from predecessor's scroll root
        # (lineage encoded: successor knows where it came from)
        successor_seed = (f"{self.swarm_id}:{to_role}:{to_agent_id}"
                          f"@lineage={depth}"
                          f":{from_scroll.root():016x}")
        to_scroll = AgentScroll.__new__(AgentScroll)
        to_scroll.agent_id  = to_agent_id
        to_scroll.role      = to_role
        to_scroll.swarm_id  = self.swarm_id
        to_scroll._capacity = self.capacity
        to_scroll._born_at  = time.time()
        to_scroll._lib      = trinity()
        b = successor_seed.encode()
        to_scroll._ptr = to_scroll._lib.vexel_new(b, len(b), self.capacity)

        with self._lock:
            self._scrolls[to_agent_id] = to_scroll
            self._lineage_depths[to_agent_id] = depth

        self._db.register_agent(to_scroll)
        self._db.log_event(to_scroll, "SEED",
                           f"successor of {from_scroll.agent_id} "
                           f"lineage_depth={depth}", to_scroll.root())

        # Remove predecessor
        with self._lock:
            self._scrolls.pop(from_scroll.agent_id, None)

        return to_scroll

    def on_session_end(self, scroll: AgentScroll) -> dict:
        """
        Session ending — write EV_MIXDOWN, save scroll, update DB.
        Returns final stats dict.
        """
        pin  = scroll.record("session_end", EV_MIXDOWN)
        path = scroll.save()
        self._db.log_event(scroll, "MIXDOWN", "session_end", pin)
        self._db.update_agent(scroll, scroll_path=path)
        self._db.dissolve_agent(scroll.agent_id)
        st = scroll.stats()
        st["scroll_path"] = path
        with self._lock:
            self._scrolls.pop(scroll.agent_id, None)
        return st

    def on_idle(self, scroll: AgentScroll, reason: str = "waiting") -> int:
        """Agent is waiting — EV_MISS."""
        pin = scroll.record(f"idle:{reason}", EV_MISS)
        self._db.log_event(scroll, "MISS", f"idle:{reason}", pin)
        return pin

    # ── Query ──────────────────────────────────────────────────────────────

    def swarm_status(self) -> dict:
        return self._db.swarm_status(self.swarm_id)

    def agent_root(self, agent_id: str) -> Optional[str]:
        a = self._db.get_agent(agent_id)
        return a["vexel_root"] if a else None

    def lineage(self, agent_id: str) -> list:
        return self._db.lineage_chain(agent_id)

    def scroll(self, agent_id: str) -> Optional[AgentScroll]:
        return self._scrolls.get(agent_id)

    def all_active(self) -> list:
        return list(self._scrolls.values())

    def close(self):
        # Final mixdown of any still-active scrolls
        with self._lock:
            active = list(self._scrolls.values())
        for s in active:
            try:
                self.on_session_end(s)
            except Exception:
                pass
        self._db.close()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()


# ── Convenience factory ───────────────────────────────────────────────────────

def new_swarm(swarm_id: str, db_path: str = SWARM_DB) -> VexelFlow:
    """Create a VexelFlow for a new swarm session."""
    return VexelFlow(swarm_id=swarm_id, db_path=db_path)


# ── CLI interface (used by hook scripts) ──────────────────────────────────────

if __name__ == "__main__":
    """
    Hook mode: called by claude-flow hooks.
    Usage:
      python vexel_flow.py spawn  <swarm_id> <agent_id> <role>
      python vexel_flow.py memory <swarm_id> <agent_id> <key> <value>
      python vexel_flow.py task   <swarm_id> <agent_id> <task_text>
      python vexel_flow.py done   <swarm_id> <agent_id> <task_text> [ok|fail]
      python vexel_flow.py end    <swarm_id> <agent_id>
      python vexel_flow.py status <swarm_id>
    """
    import sys
    args = sys.argv[1:]
    if not args:
        print("Usage: python vexel_flow.py <command> <args...>")
        sys.exit(1)

    cmd = args[0]

    # Single-shot DB for hook calls
    db = SwarmDB(SWARM_DB)
    lib = trinity()

    if cmd == "status" and len(args) >= 2:
        st = db.swarm_status(args[1])
        print(json.dumps(st, indent=2))

    elif cmd == "spawn" and len(args) >= 4:
        swarm_id, agent_id, role = args[1], args[2], args[3]
        flow = VexelFlow(swarm_id, SWARM_DB)
        scroll = flow.on_agent_spawn(agent_id, role)
        print(json.dumps({
            "event": "SEED",
            "agent_id": agent_id,
            "role": role,
            "swarm_id": swarm_id,
            "vexel_root": f"0x{scroll.root():016x}",
        }))

    elif cmd == "memory" and len(args) >= 5:
        swarm_id, agent_id = args[1], args[2]
        key, value = args[3], args[4]
        info = db.get_agent(agent_id)
        if not info:
            print(f'{{"error":"agent {agent_id} not in vexel registry"}}')
            sys.exit(1)
        # Restore scroll from DB path if available
        flow = VexelFlow(swarm_id, SWARM_DB)
        scroll = flow.on_agent_spawn(agent_id, info["role"])  # re-seed
        pin = flow.on_memory_write(scroll, key, value)
        print(json.dumps({
            "event": "RESONANCE",
            "agent_id": agent_id,
            "key": key,
            "prime_pin": pin,
            "vexel_root": f"0x{scroll.root():016x}",
        }))

    elif cmd == "done" and len(args) >= 4:
        swarm_id, agent_id = args[1], args[2]
        task = args[3]
        success = (args[4] != "fail") if len(args) > 4 else True
        info = db.get_agent(agent_id)
        role = info["role"] if info else "unknown"
        flow = VexelFlow(swarm_id, SWARM_DB)
        scroll = flow.on_agent_spawn(agent_id, role)
        pin = flow.on_task_complete(scroll, task, success)
        print(json.dumps({
            "event": "RESONANCE" if success else "MISS",
            "agent_id": agent_id,
            "task": task,
            "prime_pin": pin,
            "vexel_root": f"0x{scroll.root():016x}",
        }))

    elif cmd == "end" and len(args) >= 3:
        swarm_id, agent_id = args[1], args[2]
        info = db.get_agent(agent_id)
        role = info["role"] if info else "unknown"
        flow = VexelFlow(swarm_id, SWARM_DB)
        scroll = flow.on_agent_spawn(agent_id, role)
        st = flow.on_session_end(scroll)
        print(json.dumps(st))

    else:
        print(f"Unknown command or missing args: {args}")
        sys.exit(1)

    db.close()
