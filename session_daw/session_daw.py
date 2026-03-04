"""
SESSION DAW  —  Persistent Memory as a Digital Audio Workstation
════════════════════════════════════════════════════════════════════════

The concept:

  Every session = one CHANNEL in the DAW.
  The scroll (VexelEvents) = the WAVEFORM recorded into that channel.
  When the session ends → MIXDOWN → the waveform becomes a STEM.
  The stem stays in its channel forever. Immutable. The waveform is the record.

  Next session → new channel. Sessions never bleed into each other.

  In the background, all stems are continuously mixed down as KNOWLEDGE:
    - Each stem is a queryable layer (solo one channel)
    - All stems together are the SONG (query the full project)
    - The song length is not 3 hours — it's N stems, each their own session length

  VOICING = instrument separation per stem.
  Same stem, different voicing → different "instrument":
    spatial    = rotation/reflection events  (the rhythm section)
    harmonic   = color/recolor events        (the melody/chords)
    rhythmic   = structural complexity       (the percussion)
    score      = hit/miss outcomes           (the dynamics)
    full_mix   = everything                  (the master bus)

  This gives full separation — pull the drums out of the mix on any session.

Architecture mapping (mirrors vexel.rs exactly):
  CYLINDER  = Ulam spiral prime positions  →  storage address system
  SHEET     = scroll bytes (32-byte VexelEvents, append-only)
  VEXEL     = (cylinder_coord, sheet, merkle_root)
  PIN       = nearest prime on cylinder to BRA charge
  HOLE      = event that aligned with a prime pin (cut into the sheet)
  MIXDOWN   = session end → Merkle root snapshot → stem rendered

Author: Brad Wallace / sovereign stack
"""

from __future__ import annotations

import struct
import time
import json
import hashlib
from pathlib import Path
from typing  import Optional, Iterator
from dataclasses import dataclass, field


# ─────────────────────────────────────────────────────────────────────────────
# IMPORTS from sovereign stack
# ─────────────────────────────────────────────────────────────────────────────
from arc_bra import (
    eigen_charge, bra_resonance_score, EigenCharge,
    _ulam_coord, ulam_scroll_address,
)


# ─────────────────────────────────────────────────────────────────────────────
# CONSTANTS  —  mirrors vexel.rs EventType
# ─────────────────────────────────────────────────────────────────────────────
EV_SEED      = 0x01   # Channel opened  — session seed recorded
EV_QUERY     = 0x02   # User query processed
EV_RESONANCE = 0x03   # Pin aligned — well fired, score > 0
EV_MISS      = 0x04   # No alignment — nothing fired
EV_MIXDOWN   = 0x05   # Channel closed — Merkle root snapshot
EV_BACKUP    = 0x06   # Waveform exported to external store

EV_NAMES = {
    EV_SEED: "SEED", EV_QUERY: "QUERY", EV_RESONANCE: "RESONANCE",
    EV_MISS: "MISS", EV_MIXDOWN: "MIXDOWN", EV_BACKUP: "BACKUP",
}

# ─────────────────────────────────────────────────────────────────────────────
# VOICINGS  —  instrument separation
# Each voicing is a filter on event_type.
# Same waveform, different voicing = different instrument reading of the same take.
# ─────────────────────────────────────────────────────────────────────────────
VOICE_SPATIAL   = "spatial"    # rotation/reflection resonance events
VOICE_HARMONIC  = "harmonic"   # color/query events — the melody layer
VOICE_RHYTHMIC  = "rhythmic"   # seed + structural intake — the pulse
VOICE_SCORE     = "score"      # hits and misses only — the dynamics
VOICE_FULL      = "full_mix"   # master bus — everything

VOICING_FILTER: dict[str, set[int]] = {
    VOICE_SPATIAL:  {EV_RESONANCE},
    VOICE_HARMONIC: {EV_QUERY, EV_RESONANCE},
    VOICE_RHYTHMIC: {EV_SEED, EV_QUERY},
    VOICE_SCORE:    {EV_RESONANCE, EV_MISS},
    VOICE_FULL:     {EV_SEED, EV_QUERY, EV_RESONANCE,
                     EV_MISS, EV_MIXDOWN, EV_BACKUP},
}


# ─────────────────────────────────────────────────────────────────────────────
# PRIMITIVES  —  FNV-64 and Merkle (mirrors vexel.rs)
# ─────────────────────────────────────────────────────────────────────────────
FNV_OFFSET = 0xcbf29ce484222325
FNV_PRIME  = 0x100000001b3
U64        = 0xFFFFFFFFFFFFFFFF

def _fnv64(data: bytes) -> int:
    h = FNV_OFFSET
    for b in data:
        h ^= b
        h  = (h * FNV_PRIME) & U64
    return h

def _merkle(leaves: list[int]) -> int:
    if not leaves:
        return 0
    while len(leaves) > 1:
        if len(leaves) % 2:
            leaves.append(leaves[-1])
        leaves = [_fnv64(
            (a & U64).to_bytes(8,'little') + (b & U64).to_bytes(8,'little'))
            for a, b in zip(leaves[::2], leaves[1::2])]
    return leaves[0]


# ─────────────────────────────────────────────────────────────────────────────
# VEXEL EVENT  —  32 bytes, fixed width, mirrors vexel.rs VexelEvent
# Layout: session_id(8) + charge(8) + prime_pin(8) + ts(4) + well(2) + type(1) + score(1)
# ─────────────────────────────────────────────────────────────────────────────
_EV_FMT  = "<QQQIHBB"
_EV_SIZE = struct.calcsize(_EV_FMT)
assert _EV_SIZE == 32

@dataclass
class VexelEvent:
    session_id : int    # u64
    charge     : int    # u64  BRA eigen hash of this event's content
    prime_pin  : int    # u64  nearest prime pin on cylinder (0 = no hit)
    timestamp  : int    # u32  session-scoped µs clock (truncated)
    well_id    : int    # u16  matched well index (0xFFFF = none)
    event_type : int    # u8
    score      : int    # u8   BRA resonance 0/1/2

    def pack(self) -> bytes:
        return struct.pack(_EV_FMT,
            self.session_id & U64, self.charge & U64, self.prime_pin & U64,
            self.timestamp & 0xFFFFFFFF, self.well_id & 0xFFFF,
            self.event_type & 0xFF, self.score & 0xFF)

    @classmethod
    def unpack(cls, b: bytes) -> "VexelEvent":
        sid,ch,pin,ts,well,et,sc = struct.unpack(_EV_FMT, b[:32])
        return cls(sid,ch,pin,ts,well,et,sc)

    def leaf(self) -> int:
        return _fnv64(self.pack())

    def type_name(self) -> str:
        return EV_NAMES.get(self.event_type, f"0x{self.event_type:02x}")


# ─────────────────────────────────────────────────────────────────────────────
# CHANNEL SCROLL  —  the waveform for one session
# Append-only. Once written, immutable.
# ─────────────────────────────────────────────────────────────────────────────
class ChannelScroll:
    """
    The raw waveform — a sequence of 32-byte VexelEvents.
    This IS the session's audio data.
    O(1) append. O(n) Merkle root. O(1) random access.
    """

    def __init__(self, session_id: int):
        self.session_id = session_id
        self._events: list[VexelEvent] = []

    def append(self, ev: VexelEvent) -> int:
        self._events.append(ev)
        return ev.leaf()

    def root(self) -> int:
        """Merkle root — the waveform's fingerprint at this moment."""
        return _merkle([e.leaf() for e in self._events])

    def __len__(self) -> int:
        return len(self._events)

    def __getitem__(self, i: int) -> VexelEvent:
        return self._events[i]

    def iter_voice(self, voicing: str) -> Iterator[VexelEvent]:
        """Yield events that pass the voicing filter — instrument separation."""
        allowed = VOICING_FILTER.get(voicing, set())
        for ev in self._events:
            if ev.event_type in allowed:
                yield ev

    def to_bytes(self) -> bytes:
        """Serialize the full waveform — 32 bytes per event."""
        return b"".join(e.pack() for e in self._events)

    @classmethod
    def from_bytes(cls, session_id: int, raw: bytes) -> "ChannelScroll":
        sc = cls(session_id)
        for i in range(0, len(raw), 32):
            chunk = raw[i:i+32]
            if len(chunk) == 32:
                sc._events.append(VexelEvent.unpack(chunk))
        return sc

    def mixdown(self, clock: int) -> tuple[int,int,int,int]:
        """
        MIDI mixdown — compress session to summary tuple.
        (session_id, event_count, root_hash, clock)
        Mirrors vexel.rs Scroll::mixdown().
        """
        return (self.session_id, len(self._events), self.root(), clock)


# ─────────────────────────────────────────────────────────────────────────────
# STEM  —  a closed, rendered session
# The channel strip after mixdown. Immutable. Queryable by voicing.
# ─────────────────────────────────────────────────────────────────────────────
@dataclass
class Stem:
    """
    A completed session. The waveform is sealed.
    You can play it back in any voicing — full mix or isolated instrument.
    You can diff it against other stems at the BRA charge level.
    You cannot add events to it.
    """
    stem_id    : str          # "{session_id:016x}"
    session_id : int
    root_hash  : int          # Merkle root at mixdown
    event_count: int
    clock      : int          # session duration in ticks
    seed_label : str          # human-readable session name
    closed_at  : float        # wall clock at mixdown
    bra_charge : EigenCharge  # eigen_charge(root_hash) — stem's fingerprint
    waveform   : bytes        # raw scroll bytes — 32 × event_count
    meta       : dict = field(default_factory=dict)

    # ── Playback ──────────────────────────────────────────────────────────

    def play(self, voicing: str = VOICE_FULL) -> list[VexelEvent]:
        """
        Play back the stem filtered by voicing.
        VOICE_SPATIAL  → rotation/reflection events only
        VOICE_HARMONIC → all query + resonance events
        VOICE_RHYTHMIC → seed + query intake
        VOICE_SCORE    → hit/miss outcomes (the dynamics layer)
        VOICE_FULL     → everything (master bus)
        """
        sc = ChannelScroll.from_bytes(self.session_id, self.waveform)
        return list(sc.iter_voice(voicing))

    def score(self) -> dict:
        """Dynamics layer — the hit/miss ratio."""
        evs    = self.play(VOICE_SCORE)
        hits   = sum(1 for e in evs if e.event_type == EV_RESONANCE)
        misses = sum(1 for e in evs if e.event_type == EV_MISS)
        total  = hits + misses
        return {
            "hits":     hits,
            "misses":   misses,
            "hit_rate": hits / max(total, 1),
            "avg_bra":  sum(e.score for e in evs) / max(total, 1),
        }

    # ── Serialisation ─────────────────────────────────────────────────────

    def to_json(self) -> dict:
        import base64
        return {
            "stem_id":      self.stem_id,
            "session_id":   self.session_id,
            "root_hash":    self.root_hash,
            "event_count":  self.event_count,
            "clock":        self.clock,
            "seed_label":   self.seed_label,
            "closed_at":    self.closed_at,
            "bra_hash":     self.bra_charge.hash,
            "bra_trace":    self.bra_charge.trace,
            "bra_det":      self.bra_charge.det,
            "waveform":     base64.b64encode(self.waveform).decode(),
            "meta":         self.meta,
        }

    @classmethod
    def from_json(cls, d: dict) -> "Stem":
        import base64
        return cls(
            stem_id    = d["stem_id"],
            session_id = d["session_id"],
            root_hash  = d["root_hash"],
            event_count= d["event_count"],
            clock      = d["clock"],
            seed_label = d["seed_label"],
            closed_at  = d["closed_at"],
            bra_charge = EigenCharge(d["bra_hash"], d["bra_trace"], d["bra_det"]),
            waveform   = base64.b64decode(d["waveform"]),
            meta       = d.get("meta", {}),
        )


# ─────────────────────────────────────────────────────────────────────────────
# SESSION CHANNEL  —  the active recording track
# One per session. Records events. Sealed at mixdown → becomes a Stem.
# ─────────────────────────────────────────────────────────────────────────────
class SessionChannel:
    """
    An open recording channel. Write events until mixdown().
    After mixdown the channel is sealed — the waveform is immutable.

    The channel knows its position on the Ulam spiral at all times
    (derived from the live Merkle root → cylinder coordinate).
    """

    CYLINDER = 10_000   # prime pins up to this value

    def __init__(self, seed: str):
        self.seed_label  = seed
        self._seed_hash  = _fnv64(seed.encode())
        self._epoch      = int(time.time() * 1_000_000) & U64
        self.session_id  = (self._seed_hash ^ self._epoch) & U64
        self._scroll     = ChannelScroll(self.session_id)
        self._clock      = 0
        self._closed     = False
        # Record SEED event — this opens the channel
        self._write(EV_SEED, self._seed_hash, 0xFFFF, 0)

    # ── Internal write ────────────────────────────────────────────────────

    def _write(self, ev_type: int, charge: int,
               well_id: int, score: int) -> VexelEvent:
        self._clock += 1
        _, _, pin = ulam_scroll_address(charge % self.CYLINDER, self.CYLINDER)
        ev = VexelEvent(
            session_id = self.session_id,
            charge     = charge & U64,
            prime_pin  = pin,
            timestamp  = self._clock & 0xFFFFFFFF,
            well_id    = well_id & 0xFFFF,
            event_type = ev_type,
            score      = score & 0xFF,
        )
        self._scroll.append(ev)
        return ev

    # ── Public recording API ──────────────────────────────────────────────

    def record_query(self, charge: int, well_id: int = 0xFFFF) -> VexelEvent:
        """A query was processed. charge = BRA hash of the query content."""
        assert not self._closed, "Channel sealed — call open_channel() for a new session"
        return self._write(EV_QUERY, charge, well_id, 0)

    def record_resonance(self, charge: int,
                         well_id: int, score: int) -> VexelEvent:
        """Pin aligned — pattern matched. score = 0/1/2."""
        assert not self._closed
        return self._write(EV_RESONANCE, charge, well_id, score)

    def record_miss(self, charge: int) -> VexelEvent:
        """No resonance — nothing fired."""
        assert not self._closed
        return self._write(EV_MISS, charge, 0xFFFF, 0)

    def record_backup(self, charge: int) -> VexelEvent:
        """Scroll exported to external store."""
        assert not self._closed
        return self._write(EV_BACKUP, charge, 0xFFFF, 0)

    # ── Mixdown ───────────────────────────────────────────────────────────

    def mixdown(self, meta: dict = None) -> Stem:
        """
        Close the channel. Render the stem. Seal the waveform.
        No more events can be written after this.

        The stem's BRA charge = eigen_charge(Merkle root).
        This fingerprint is how the stem is found in cross-session queries.
        """
        assert not self._closed, "Already mixed down"
        # Write the MIXDOWN marker into the scroll before sealing
        root_before = self._scroll.root()
        self._write(EV_MIXDOWN, root_before, 0xFFFF, 0)
        self._closed = True

        root_hash  = self._scroll.root()
        waveform   = self._scroll.to_bytes()
        bra_charge = eigen_charge(root_hash.to_bytes(8, 'little'))

        return Stem(
            stem_id    = f"{self.session_id:016x}",
            session_id = self.session_id,
            root_hash  = root_hash,
            event_count= len(self._scroll),
            clock      = self._clock,
            seed_label = self.seed_label,
            closed_at  = time.time(),
            bra_charge = bra_charge,
            waveform   = waveform,
            meta       = meta or {},
        )

    # ── State ─────────────────────────────────────────────────────────────

    @property
    def ulam_position(self) -> tuple[int,int]:
        """Current cylinder coordinate — storage address of the live root."""
        return _ulam_coord(self._scroll.root() % self.CYLINDER)

    @property
    def is_closed(self) -> bool:
        return self._closed


# ─────────────────────────────────────────────────────────────────────────────
# STEM MIXER  —  the DAW project
# Holds all stems. Provides the bus: solo, mix, full song, diff.
# Persists as an append-only JSON-lines .daw file.
# ─────────────────────────────────────────────────────────────────────────────
class StemMixer:
    """
    The DAW project — all channels, all stems, all time.

    Channels are isolated during recording.
    Stems are indexed by BRA charge after mixdown.
    Queries hit the bus — resonant stems respond, others stay silent.

    API:
      open_channel(seed)                → SessionChannel (open, record, mixdown)
      commit(stem)                      → add closed stem to project
      solo(stem_id, voicing)            → one channel, one instrument
      mix(query_charge, voicing)        → all channels, resonant only
      song(voicing)                     → all channels, all events, in order
      diff(stem_a, stem_b)              → charge-level comparison
      project_summary()                 → song header / project stats
    """

    def __init__(self, project_path: str = None):
        self._stems: dict[str, Stem] = {}
        self._path  = Path(project_path) if project_path else None
        if self._path and self._path.exists():
            self._load()

    # ── Channel management ────────────────────────────────────────────────

    def open_channel(self, seed: str) -> SessionChannel:
        """Open a new recording channel. New session, new channel, always."""
        return SessionChannel(seed)

    def commit(self, stem: Stem) -> None:
        """
        Commit a closed stem to the project.
        This is 'render to track' — the waveform is now in the mixer.
        """
        self._stems[stem.stem_id] = stem
        if self._path:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            with open(self._path, "a") as f:
                f.write(json.dumps(stem.to_json()) + "\n")

    # ── Bus queries ───────────────────────────────────────────────────────

    def solo(self, stem_id: str,
             voicing: str = VOICE_FULL) -> Optional[list[VexelEvent]]:
        """
        Pull one channel in isolation.
        voicing = which instrument you want to hear.
        Returns None if stem not found.
        """
        stem = self._stems.get(stem_id)
        return stem.play(voicing) if stem else None

    def mix(self, query_charge: EigenCharge,
            voicing: str  = VOICE_FULL,
            min_res: int  = 1) -> list[tuple[int, Stem, list[VexelEvent]]]:
        """
        Cross-session resonance query — the mix bus.
        Every stem's BRA fingerprint is tested against query_charge.
        Only stems with resonance >= min_res return signal.
        Returns [(resonance, stem, events)] sorted by resonance DESC.

        min_res=2 → exact fingerprint matches only
        min_res=1 → near-resonance (trace/det proximity)
        """
        out = []
        for stem in self._stems.values():
            r = bra_resonance_score(query_charge, stem.bra_charge)
            if r >= min_res:
                out.append((r, stem, stem.play(voicing)))
        out.sort(key=lambda x: (-x[0], -x[1].event_count))
        return out

    def song(self, voicing: str = VOICE_FULL) -> list[tuple[Stem, VexelEvent]]:
        """
        The full song — all events from all stems, ordered by session close time.
        The song is not one long file. It's N stems played in sequence.
        Each stem is its own channel. They're layered here for the full picture.
        voicing filters which instrument you're hearing across all channels.
        """
        out: list[tuple[Stem, VexelEvent]] = []
        for stem in sorted(self._stems.values(), key=lambda s: s.closed_at):
            for ev in stem.play(voicing):
                out.append((stem, ev))
        return out

    def diff(self, id_a: str, id_b: str) -> dict:
        """
        Compare two sessions at the BRA charge level.
        Structural resonance between stems — did they do the same work?
        """
        a = self._stems.get(id_a)
        b = self._stems.get(id_b)
        if not a or not b:
            return {"error": "stem not found"}
        r = bra_resonance_score(a.bra_charge, b.bra_charge)
        return {
            "stem_a":      id_a,
            "stem_b":      id_b,
            "resonance":   r,
            "hash_match":  a.bra_charge.hash  == b.bra_charge.hash,
            "trace_delta": abs(a.bra_charge.trace - b.bra_charge.trace),
            "det_delta":   abs(a.bra_charge.det   - b.bra_charge.det),
            "events_a":    a.event_count,
            "events_b":    b.event_count,
            "score_a":     a.score(),
            "score_b":     b.score(),
        }

    # ── Background mixdown → knowledge ────────────────────────────────────

    def sync_to_library(self, library, min_score: float = 1.0) -> int:
        """
        Background mixdown: push high-score resonance events from all stems
        into the persistent pattern library as knowledge entries.
        This is the stems-become-knowledge pass — running silently in the background.
        Returns number of patterns committed.
        """
        committed = 0
        for stem in self._stems.values():
            hits = [e for e in stem.play(VOICE_SCORE)
                    if e.event_type == EV_RESONANCE and e.score >= 2]
            for ev in hits:
                program = stem.meta.get("programs", {}).get(str(ev.charge), "")
                if not program:
                    continue
                try:
                    library.store(
                        task_id       = stem.stem_id,
                        rule          = f"stem:{stem.seed_label}:pin{ev.prime_pin}",
                        program       = program,
                        train_score   = ev.score / 2.0,
                        pattern_class = "stem_knowledge",
                    )
                    committed += 1
                except Exception:
                    pass
        return committed

    # ── Project info ──────────────────────────────────────────────────────

    def project_summary(self) -> dict:
        stems = sorted(self._stems.values(), key=lambda s: s.closed_at)
        if not stems:
            return {"stems": 0, "total_events": 0}
        total_ev   = sum(s.event_count for s in stems)
        all_scores = [s.score() for s in stems]
        total_hits = sum(d["hits"]   for d in all_scores)
        total_miss = sum(d["misses"] for d in all_scores)
        return {
            "stems":        len(stems),
            "total_events": total_ev,
            "total_hits":   total_hits,
            "total_misses": total_miss,
            "hit_rate":     total_hits / max(total_hits + total_miss, 1),
            "oldest":       stems[0].seed_label,
            "newest":       stems[-1].seed_label,
            "project":      str(self._path) if self._path else "(in-memory)",
        }

    def stem_count(self) -> int:
        return len(self._stems)

    def stems(self) -> list[Stem]:
        return sorted(self._stems.values(), key=lambda s: s.closed_at)

    # ── Persistence ───────────────────────────────────────────────────────

    def _load(self) -> None:
        with open(self._path) as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        s = Stem.from_json(json.loads(line))
                        self._stems[s.stem_id] = s
                        self._stems[s.stem_id] = s
                    except Exception:
                        pass

    def save(self, path: str = None) -> None:
        """Full rewrite — use for compaction."""
        p = Path(path) if path else self._path
        if not p:
            raise ValueError("No project path")
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "w") as f:
            for stem in self.stems():
                f.write(json.dumps(stem.to_json()) + "\n")

    def export_waveform(self, stem_id: str, path: str) -> None:
        """Export raw scroll bytes for a single stem — the raw audio file."""
        stem = self._stems.get(stem_id)
        if not stem:
            raise KeyError(f"Stem '{stem_id}' not found")
        Path(path).write_bytes(stem.waveform)


# ─────────────────────────────────────────────────────────────────────────────
# ARC SESSION DAW  —  connects the DAW to the ARC sovereign pipeline
# ─────────────────────────────────────────────────────────────────────────────
class ARCSessionDAW:
    """
    Thin bridge: StemMixer ↔ ARC sovereign stack.

    Usage:
        daw = ARCSessionDAW("project.daw")

        with daw.session("eval_run_001") as ch:
            for task in tasks:
                tc  = task_charge(task)
                cfg = sovereign_solve_config(task, bra_store=daw.bra_store)
                if cfg["bra_resonance"] == 2:
                    ch.record_resonance(tc.hash, well_id=0, score=2)
                else:
                    result = solver.solve(task)
                    ev_type = EV_RESONANCE if result["solved"] else EV_MISS
                    if result["solved"]:
                        ch.record_resonance(tc.hash, well_id=1, score=1)
                    else:
                        ch.record_miss(tc.hash)
        # stem auto-committed when context exits

        # Cross-session query: which sessions worked on tasks like this one?
        hits = daw.query(task_charge(task), voicing=VOICE_SCORE)
    """

    def __init__(self, project_path: str = None):
        from arc_bra import BRAPatternStore
        self.mixer     = StemMixer(project_path)
        self.bra_store = BRAPatternStore()

    class _Ctx:
        def __init__(self, daw: "ARCSessionDAW", seed: str):
            self._daw  = daw
            self._seed = seed
            self.ch: Optional[SessionChannel] = None
            self.stem: Optional[Stem]         = None

        def __enter__(self) -> SessionChannel:
            self.ch = self._daw.mixer.open_channel(self._seed)
            return self.ch

        def __exit__(self, *_):
            if self.ch and not self.ch.is_closed:
                self.stem = self.ch.mixdown()
                self._daw.mixer.commit(self.stem)
            return False

    def session(self, seed: str) -> "_Ctx":
        return self._Ctx(self, seed)

    def query(self, charge: EigenCharge,
              voicing: str = VOICE_FULL,
              min_res: int = 1):
        return self.mixer.mix(charge, voicing=voicing, min_res=min_res)

    def song(self, voicing: str = VOICE_FULL):
        return self.mixer.song(voicing)

    def summary(self) -> dict:
        return self.mixer.project_summary()


# ─────────────────────────────────────────────────────────────────────────────
# SMOKE TEST
# ─────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import tempfile, sys
    sys.path.insert(0, "/mnt/user-data/outputs")

    print("SESSION DAW — smoke test")
    print("=" * 55)

    tmp  = tempfile.mkdtemp()
    proj = f"{tmp}/test.daw"
    mixer = StemMixer(proj)

    # ── Session 1: recolor task solved
    ch1 = mixer.open_channel("arc_eval_run_001")
    q1  = eigen_charge(b"task:t001:recolor_1_to_2")
    ch1.record_query(q1.hash)
    ch1.record_resonance(q1.hash, well_id=1, score=2)
    stem1 = ch1.mixdown(meta={"pattern": "recolor"})
    mixer.commit(stem1)

    # ── Session 2: rotation task solved
    ch2 = mixer.open_channel("arc_eval_run_002")
    q2  = eigen_charge(b"task:t002:rot90")
    ch2.record_query(q2.hash)
    ch2.record_resonance(q2.hash, well_id=2, score=2)
    stem2 = ch2.mixdown(meta={"pattern": "rot90"})
    mixer.commit(stem2)

    # ── Session 3: hard task, miss
    ch3 = mixer.open_channel("arc_eval_run_003")
    q3  = eigen_charge(b"task:t003:unknown")
    ch3.record_query(q3.hash)
    ch3.record_miss(q3.hash)
    stem3 = ch3.mixdown()
    mixer.commit(stem3)

    print(f"\n{mixer.stem_count()} stems committed")

    # Solo — pull session 1 score voicing only
    solo = mixer.solo(stem1.stem_id, voicing=VOICE_SCORE)
    print(f"\nSolo stem1 [{VOICE_SCORE}]: {len(solo)} events")
    for ev in solo:
        print(f"  {ev.type_name():<12} score={ev.score}  pin={ev.prime_pin}")

    # Full song — harmonic voicing across all sessions
    song = mixer.song(voicing=VOICE_HARMONIC)
    print(f"\nFull song [{VOICE_HARMONIC}]: {len(song)} events across all stems")
    for stem, ev in song:
        print(f"  [{stem.seed_label[-3:]}] {ev.type_name():<12} charge={ev.charge:016x}")

    # Mix bus query — which stems resonate with session 1's fingerprint?
    hits = mixer.mix(stem1.bra_charge, min_res=1)
    print(f"\nMix bus (resonance≥1): {len(hits)} stem(s) respond")
    for r, stem, evs in hits:
        print(f"  resonance={r}  stem={stem.seed_label[-10:]}  events={len(evs)}")

    # Diff two sessions
    d = mixer.diff(stem1.stem_id, stem2.stem_id)
    print(f"\nDiff: stem1 vs stem2  resonance={d['resonance']}  trace_delta={d['trace_delta']}")

    # Reload from disk — waveform integrity check
    mixer2 = StemMixer(proj)
    assert mixer2.stem_count() == 3, f"Expected 3 stems, got {mixer2.stem_count()}"
    s1r    = mixer2._stems[stem1.stem_id]
    assert s1r.waveform == stem1.waveform, "Waveform mismatch after reload"
    assert len(stem1.waveform) == stem1.event_count * 32

    print(f"\nReloaded from disk:   {mixer2.stem_count()} stems  ✓")
    print(f"Waveform integrity:   {len(stem1.waveform)} bytes ({stem1.event_count} events × 32)  ✓")
    print(f"\nSummary:")
    for k, v in mixer.project_summary().items():
        print(f"  {k}: {v}")

    print(f"\nSMOKE TEST PASSED ✓")
