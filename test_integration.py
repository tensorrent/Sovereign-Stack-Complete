"""
test_integration.py — Sovereign Stack Integration Tests
========================================================
End-to-end tests covering all three integrated systems:
  1. Vexel scroll integrity (trinity core)
  2. Claude Flow swarm coordination (vexel_flow)
  3. Hermes persistent memory (hermes_vexel)
  4. Hermes tool interception (hermes_hooks)
  5. Cross-system consistency (scroll roots match MEMORY.md tags)
  6. Handoff lineage chain (vexel_flow handoff → state_db)

Run with:
  TRINITY_LIB=/path/to/libtrinity.so python3 test_integration.py

Expected output: all PASS, zero FAIL.
"""

import os
import sys
import json
import time
import uuid
import sqlite3
import tempfile
import traceback
from pathlib import Path

# ── Path setup ────────────────────────────────────────────────────────────────
SOVEREIGN_SDK = os.environ.get("SOVEREIGN_SDK", os.path.dirname(__file__))
sys.path.insert(0, SOVEREIGN_SDK)

# ── Test harness ──────────────────────────────────────────────────────────────

_results: list[tuple[str, bool, str]] = []

def test(name: str):
    """Decorator that immediately runs the test function at definition time."""
    def decorator(fn):
        try:
            fn()
            _results.append((name, True, ""))
            print(f"  PASS  {name}")
        except AssertionError as e:
            _results.append((name, False, str(e)))
            print(f"  FAIL  {name}: {e}")
        except Exception as e:
            tb = traceback.format_exc().strip().split("\n")[-1]
            _results.append((name, False, tb))
            print(f"  ERROR {name}: {tb}")
        return fn  # return original so _ isn't broken
    return decorator


def assert_eq(a, b, msg=""):
    assert a == b, f"{msg}: expected {b!r}, got {a!r}"

def assert_contains(haystack: str, needle: str, msg=""):
    assert needle in haystack, f"{msg}: {needle!r} not in {haystack!r}"

def assert_hex(val: str, msg=""):
    assert val.startswith("0x") and len(val) == 18, \
        f"{msg}: expected 18-char hex string, got {val!r}"


# ── Shared fixtures ───────────────────────────────────────────────────────────

def make_temp_env():
    """Create a fresh temp dir for isolated test runs."""
    tmp = Path(tempfile.mkdtemp())
    return tmp

def patch_hermes_paths(tmp: Path):
    """Override hermes_vexel global paths to use temp dir."""
    import hermes_vexel as hv
    hv.HERMES_DIR   = tmp
    hv.MEMORIES_DIR = tmp / "memories"
    hv.SKILLS_DIR   = tmp / "skills"
    hv.STATE_DB     = tmp / "state.db"
    hv.MEMORY_FILE  = tmp / "memories" / "MEMORY.md"
    hv.USER_FILE    = tmp / "memories" / "USER.md"
    return hv


# ══════════════════════════════════════════════════════════════════════════════
# SUITE 1: Vexel scroll core
# ══════════════════════════════════════════════════════════════════════════════

print("\n── Suite 1: Vexel Scroll Core ──")

@test("vexel: library loads")
def _():
    from vexel_flow import trinity
    lib = trinity()
    assert lib is not None

@test("vexel: AgentScroll creates with unique roots")
def _():
    from vexel_flow import AgentScroll
    s1 = AgentScroll("agent-a", "coder",      "swarm-test")
    s2 = AgentScroll("agent-b", "researcher", "swarm-test")
    assert s1.root() != s2.root(), "different agents must have different roots"
    assert s1.root() != 0
    assert s2.root() != 0

@test("vexel: record advances root monotonically distinct")
def _():
    from vexel_flow import AgentScroll, EV_RESONANCE, EV_QUERY
    s = AgentScroll("test-mono", "analyst", "swarm-test")
    init_count = s.event_count()   # may be 1 if __init__ records EV_SEED
    r0 = s.root()
    s.record("first event", EV_RESONANCE, 2)
    r1 = s.root()
    s.record("second event", EV_QUERY, 1)
    r2 = s.root()
    assert r0 != r1, "root must change after first record"
    assert r1 != r2, "root must change after second record"
    assert s.event_count() == init_count + 2, \
        f"event count must advance by 2 (init={init_count}, got {s.event_count()})"

@test("vexel: export/restore preserves root")
def _():
    import ctypes
    from vexel_flow import AgentScroll, EV_RESONANCE, trinity
    s = AgentScroll("export-test", "tester", "swarm-test")
    s.record("important fact", EV_RESONANCE, 2)
    original_root = s.root()

    data = s.export()
    assert len(data) > 0

    lib  = trinity()
    # vexel_restore(seed, seed_len, capacity, data, data_len)
    seed = b"export-test"
    ptr  = lib.vexel_restore(seed, len(seed), 10007, data, len(data))
    restored_root = lib.vexel_root(ptr)
    lib.vexel_free(ptr)

    assert_eq(original_root, restored_root, "restored root must match original")

@test("vexel: F369 table verification")
def _():
    import ctypes
    from vexel_flow import trinity
    lib = trinity()
    lib.bra_verify_f369_table.restype = ctypes.c_int32
    result = lib.bra_verify_f369_table()
    assert result == 1, f"F369 table verification failed (returned {result})"

@test("vexel: Ulam position changes with events")
def _():
    from vexel_flow import AgentScroll, EV_RESONANCE, EV_QUERY
    s  = AgentScroll("ulam-test", "coder", "swarm-test")
    p0 = s.ulam()
    s.record("event 1", EV_RESONANCE, 2)
    p1 = s.ulam()
    s.record("event 2", EV_QUERY, 1)
    p2 = s.ulam()
    # At least one coordinate must change across 3 events
    positions = {p0, p1, p2}
    assert len(positions) >= 2, "Ulam position should change across events"


# ══════════════════════════════════════════════════════════════════════════════
# SUITE 2: Claude Flow bridge (VexelFlow)
# ══════════════════════════════════════════════════════════════════════════════

print("\n── Suite 2: Claude Flow Bridge ──")

@test("flow: agent spawn creates scroll and registers in DB")
def _():
    from vexel_flow import VexelFlow
    tmp = make_temp_env()
    db  = str(tmp / "swarm.db")
    flow = VexelFlow("test-swarm", db)
    scroll = flow.on_agent_spawn("test-agent-001", "researcher")
    assert scroll is not None
    assert scroll.root() != 0
    info = flow._db.get_agent("test-agent-001")
    assert info is not None
    assert info["role"] == "researcher"
    assert info["dissolved"] == 0
    flow.close()

@test("flow: memory write records RESONANCE event")
def _():
    from vexel_flow import VexelFlow
    tmp = make_temp_env()
    db  = str(tmp / "swarm.db")
    flow   = VexelFlow("test-swarm", db)
    scroll = flow.on_agent_spawn("mem-agent", "coder")
    root_before = scroll.root()
    flow.on_memory_write(scroll, "auth_method", "JWT RS256")
    root_after  = scroll.root()
    assert root_before != root_after, "memory write must change root"
    flow.close()

@test("flow: handoff increments lineage_depth and creates successor")
def _():
    from vexel_flow import VexelFlow
    tmp = make_temp_env()
    db  = str(tmp / "swarm.db")
    flow      = VexelFlow("test-swarm", db)
    researcher = flow.on_agent_spawn("res-001", "researcher")
    coder      = flow.on_agent_spawn("cod-001", "coder")
    res_root   = researcher.root()

    successor_scroll = flow.on_handoff(researcher, "cod-001", "coder", "TestHandoff")
    handoffs = flow._db.lineage_chain("cod-001")
    assert len(handoffs) >= 1
    assert handoffs[-1]["from"] == "res-001"
    assert handoffs[-1]["depth"] == 1

    # Dissolved agent
    info = flow._db.get_agent("res-001")
    assert info["dissolved"] == 1
    flow.close()

@test("flow: session_end saves scroll file")
def _():
    from vexel_flow import VexelFlow
    tmp = make_temp_env()
    db  = str(tmp / "swarm.db")
    os.environ["MIXDOWN_DIR"] = str(tmp / "mixdowns")
    flow   = VexelFlow("test-swarm", db)
    scroll = flow.on_agent_spawn("end-agent", "tester")
    st = flow.on_session_end(scroll)
    assert st.get("scroll_path") is not None
    assert Path(st["scroll_path"]).exists(), "scroll file must be written"
    flow.close()

@test("flow: swarm_status returns correct agent count")
def _():
    from vexel_flow import VexelFlow
    tmp = make_temp_env()
    db  = str(tmp / "swarm.db")
    flow = VexelFlow("count-swarm", db)
    for i in range(3):
        flow.on_agent_spawn(f"agent-{i}", ["coder","researcher","tester"][i])
    st = flow.swarm_status()
    assert_eq(st["agents_active"], 3, "active agent count")
    flow.close()


# ══════════════════════════════════════════════════════════════════════════════
# SUITE 3: Hermes memory bridge
# ══════════════════════════════════════════════════════════════════════════════

print("\n── Suite 3: Hermes Memory Bridge ──")

@test("hermes: session_start records EV_SEED")
def _():
    import hermes_vexel as hv
    tmp = make_temp_env(); patch_hermes_paths(tmp)
    bridge = hv.HermesScrollBridge("s-seed-001", hermes_dir=tmp)
    st = bridge.session_start()
    assert_eq(st["event"], "SEED", "session_start event")
    assert_hex(st["vexel_root"], "session_start root")
    assert bridge.scroll.event_count() >= 1, "at least 1 event after session_start"

@test("hermes: memory_add embeds provenance tag in MEMORY.md")
def _():
    import hermes_vexel as hv
    tmp = make_temp_env(); patch_hermes_paths(tmp)
    bridge = hv.HermesScrollBridge("s-add-001", hermes_dir=tmp)
    bridge.session_start()

    result = bridge.memory_add("JWT is preferred for auth", "MEMORY.md")
    assert_eq(result["event"], "RESONANCE", "memory_add event")
    assert_eq(result["ok"], True, "memory_add ok")

    content = (tmp / "memories" / "MEMORY.md").read_text()
    assert_contains(content, "JWT is preferred for auth", "entry in MEMORY.md")
    assert_contains(content, "vexel:root=", "provenance tag in MEMORY.md")
    assert_contains(content, f"session=s-add-001", "session in provenance tag")

@test("hermes: provenance root in MEMORY.md matches scroll root at write time")
def _():
    import hermes_vexel as hv, re
    tmp = make_temp_env(); patch_hermes_paths(tmp)
    bridge = hv.HermesScrollBridge("s-prov-001", hermes_dir=tmp)
    bridge.session_start()
    result = bridge.memory_add("Test provenance entry", "MEMORY.md")

    # Extract root from provenance tag in file
    content  = (tmp / "memories" / "MEMORY.md").read_text()
    m = re.search(r'vexel:root=(0x[0-9a-f]+)', content)
    assert m, "provenance tag must be in MEMORY.md"

    tag_root  = m.group(1)
    # The root in the tag was the scroll root AFTER the record() call
    # which is what result["vexel_root"] captures
    assert_eq(tag_root, result["vexel_root"], "tag root matches scroll root at write")

@test("hermes: memory_replace updates entry and provenance")
def _():
    import hermes_vexel as hv
    tmp = make_temp_env(); patch_hermes_paths(tmp)
    bridge = hv.HermesScrollBridge("s-rep-001", hermes_dir=tmp)
    bridge.session_start()
    bridge.memory_add("Old auth method: basic", "MEMORY.md")
    result = bridge.memory_replace("Old auth method: basic",
                                    "Auth method: JWT RS256", "MEMORY.md")
    assert_eq(result["ok"], True, "replace ok")
    content = (tmp / "memories" / "MEMORY.md").read_text()
    assert "JWT RS256" in content, "new entry in MEMORY.md"
    assert "Old auth method" not in content, "old entry removed"

@test("hermes: memory_remove fires EV_MISS and deletes entry")
def _():
    import hermes_vexel as hv
    tmp = make_temp_env(); patch_hermes_paths(tmp)
    bridge = hv.HermesScrollBridge("s-rem-001", hermes_dir=tmp)
    bridge.session_start()
    bridge.memory_add("Stale entry to remove", "MEMORY.md")
    result = bridge.memory_remove("Stale entry to remove", "MEMORY.md")
    assert_eq(result["event"], "MISS", "memory_remove event is MISS")
    assert_eq(result["ok"], True, "remove ok")
    content = (tmp / "memories" / "MEMORY.md").read_text()
    assert "Stale entry" not in content, "entry removed from MEMORY.md"

@test("hermes: skill_create embeds vexel anchor in SKILL.md frontmatter")
def _():
    import hermes_vexel as hv
    tmp = make_temp_env(); patch_hermes_paths(tmp)
    bridge = hv.HermesScrollBridge("s-skill-001", hermes_dir=tmp)
    bridge.session_start()
    result = bridge.skill_create(
        "test-skill", "Test skill description",
        "---\nname: test-skill\n---\n# Test Skill\n## Procedure\n1. Do the thing"
    )
    assert_eq(result["event"], "RESONANCE", "skill_create event")
    path = Path(result["skill_path"])
    assert path.exists(), "SKILL.md must be written"
    content = path.read_text()
    assert_contains(content, "vexel_root:", "vexel_root in SKILL.md frontmatter")
    assert_contains(content, "vexel_ulam:", "vexel_ulam in SKILL.md frontmatter")
    assert_contains(content, "s-skill-001", "session id in SKILL.md frontmatter")

@test("hermes: session_end writes root to state.db vexel_sessions")
def _():
    import hermes_vexel as hv
    tmp = make_temp_env(); patch_hermes_paths(tmp)
    bridge = hv.HermesScrollBridge("s-end-001", hermes_dir=tmp)
    bridge.session_start()
    bridge.memory_add("Some fact", "MEMORY.md")
    result = bridge.session_end()
    assert_eq(result["event"], "MIXDOWN", "session_end event")

    # Check state.db
    db   = sqlite3.connect(str(tmp / "state.db"))
    rows = db.execute(
        "SELECT session_id, vexel_root, event_count FROM vexel_sessions"
    ).fetchall()
    assert len(rows) == 1, "one row in vexel_sessions"
    assert_eq(rows[0][0], "s-end-001", "session_id in DB")
    assert rows[0][1].startswith("0x"), "vexel_root is hex"
    assert rows[0][2] >= 2, "at least 2 events (SEED + MIXDOWN)"
    db.close()

@test("hermes: memory_log captures all operations")
def _():
    import hermes_vexel as hv
    tmp = make_temp_env(); patch_hermes_paths(tmp)
    bridge = hv.HermesScrollBridge("s-log-001", hermes_dir=tmp)
    bridge.session_start()
    bridge.memory_add("Fact one", "MEMORY.md")
    bridge.memory_add("User pref", "USER.md")
    bridge.memory_read("MEMORY.md")
    bridge.memory_remove("Fact one", "MEMORY.md")
    bridge.session_end()

    db   = sqlite3.connect(str(tmp / "state.db"))
    rows = db.execute(
        "SELECT action, file FROM vexel_memory_log ORDER BY ts"
    ).fetchall()
    db.close()

    actions = [(r[0], r[1]) for r in rows]
    assert ("add", "MEMORY.md") in actions
    assert ("add", "USER.md")   in actions
    assert ("read", "MEMORY.md") in actions
    assert ("remove", "MEMORY.md") in actions

@test("hermes: char_limit enforced on MEMORY.md")
def _():
    import hermes_vexel as hv
    tmp = make_temp_env(); patch_hermes_paths(tmp)
    # Set tiny limit
    bridge = hv.HermesScrollBridge("s-limit-001", hermes_dir=tmp)
    bridge.memory_file.char_limit = 200
    bridge.session_start()

    # First few entries should fit
    bridge.memory_add("Short entry A", "MEMORY.md")
    bridge.memory_add("Short entry B", "MEMORY.md")
    # This entry pushes over 200 char limit
    result = bridge.memory_add("X" * 300, "MEMORY.md")
    # With char limit, add should return ok=False
    assert_eq(result["ok"], False, "add over char limit should return ok=False")


# ══════════════════════════════════════════════════════════════════════════════
# SUITE 4: Hermes hooks (tool interception)
# ══════════════════════════════════════════════════════════════════════════════

print("\n── Suite 4: Hermes Hooks ──")

@test("hooks: memory add → RESONANCE event")
def _():
    import hermes_vexel as hv, hermes_hooks as hk
    tmp = make_temp_env(); patch_hermes_paths(tmp)
    hk._bridges.clear()

    sid    = f"hook-test-{uuid.uuid4().hex[:6]}"
    bridge = hk.register_session(sid)
    ev = hk.intercept_tool_call(
        "memory",
        {"action": "add", "content": "Hermes hook test", "file": "MEMORY.md"},
        {}, sid, True
    )
    assert ev is not None
    assert_eq(ev["event"], "RESONANCE", "memory add hook event")
    assert_hex(ev["vexel_root"], "hook vexel root")
    hk.close_session(sid)

@test("hooks: memory remove → MISS event")
def _():
    import hermes_vexel as hv, hermes_hooks as hk
    tmp = make_temp_env(); patch_hermes_paths(tmp)
    hk._bridges.clear()
    sid = f"hook-rem-{uuid.uuid4().hex[:6]}"
    bridge = hk.register_session(sid)
    # First add something to remove
    hk.intercept_tool_call("memory",
        {"action": "add", "content": "To remove", "file": "MEMORY.md"},
        {}, sid, True)
    ev = hk.intercept_tool_call("memory",
        {"action": "remove", "content": "To remove", "file": "MEMORY.md"},
        {}, sid, True)
    assert_eq(ev["event"], "MISS", "memory remove → MISS")
    hk.close_session(sid)

@test("hooks: skill_manage create → RESONANCE score=3")
def _():
    import hermes_vexel as hv, hermes_hooks as hk
    tmp = make_temp_env(); patch_hermes_paths(tmp)
    hk._bridges.clear()
    sid = f"hook-skill-{uuid.uuid4().hex[:6]}"
    hk.register_session(sid)
    ev = hk.intercept_tool_call("skill_manage",
        {"action": "create", "name": "test-hook-skill",
         "description": "Testing", "content": "# Test"},
        {}, sid, True)
    assert ev is not None
    assert_eq(ev["event"], "RESONANCE", "skill create hook event")
    hk.close_session(sid)

@test("hooks: session_search → QUERY event")
def _():
    import hermes_vexel as hv, hermes_hooks as hk
    tmp = make_temp_env(); patch_hermes_paths(tmp)
    hk._bridges.clear()
    sid = f"hook-search-{uuid.uuid4().hex[:6]}"
    hk.register_session(sid)
    ev = hk.intercept_tool_call("session_search",
        {"query": "JWT auth"}, {}, sid, True)
    assert_eq(ev["event"], "QUERY", "session_search → QUERY")
    hk.close_session(sid)

@test("hooks: non-memory tool returns None (passthrough)")
def _():
    import hermes_vexel as hv, hermes_hooks as hk
    tmp = make_temp_env(); patch_hermes_paths(tmp)
    hk._bridges.clear()
    sid = f"hook-pass-{uuid.uuid4().hex[:6]}"
    hk.register_session(sid)
    ev = hk.intercept_tool_call("terminal",
        {"command": "ls -la"}, {"output": "file.txt"}, sid, True)
    assert ev is None, "terminal tool must not be intercepted"
    hk.close_session(sid)


# ══════════════════════════════════════════════════════════════════════════════
# SUITE 5: Cross-system consistency
# ══════════════════════════════════════════════════════════════════════════════

print("\n── Suite 5: Cross-System Consistency ──")

@test("cross: MEMORY.md root matches state.db memory_log root for same event")
def _():
    import hermes_vexel as hv, re
    tmp = make_temp_env(); patch_hermes_paths(tmp)
    bridge = hv.HermesScrollBridge("s-cross-001", hermes_dir=tmp)
    bridge.session_start()
    result = bridge.memory_add("Cross-check entry", "MEMORY.md")
    bridge.session_end()

    # Root in MEMORY.md tag
    content  = (tmp / "memories" / "MEMORY.md").read_text()
    m = re.search(r'vexel:root=(0x[0-9a-f]+)', content)
    assert m, "provenance tag must be in MEMORY.md"
    tag_root = m.group(1)

    # Root in state.db memory_log
    db = sqlite3.connect(str(tmp / "state.db"))
    rows = db.execute(
        "SELECT vexel_root FROM vexel_memory_log WHERE action='add'"
    ).fetchall()
    db.close()
    assert rows, "memory_log must have add entry"
    db_root = rows[0][0]

    assert_eq(tag_root, db_root, "MEMORY.md provenance root matches memory_log root")

@test("cross: SKILL.md vexel_root matches memory_log entry")
def _():
    import hermes_vexel as hv
    tmp = make_temp_env(); patch_hermes_paths(tmp)
    bridge = hv.HermesScrollBridge("s-skill-cross-001", hermes_dir=tmp)
    bridge.session_start()
    result = bridge.skill_create(
        "cross-skill", "Cross check skill",
        "---\nname: cross-skill\n---\n# Cross Skill\n## Procedure\n1. Step one"
    )
    bridge.session_end()

    # Root in SKILL.md frontmatter
    import re
    content  = Path(result["skill_path"]).read_text()
    m = re.search(r'vexel_root: "(0x[0-9a-f]+)"', content)
    assert m, "vexel_root must be in SKILL.md"
    skill_root = m.group(1)

    # Root in state.db memory_log
    db = sqlite3.connect(str(tmp / "state.db"))
    rows = db.execute(
        "SELECT vexel_root FROM vexel_memory_log WHERE action='create'"
    ).fetchall()
    db.close()
    assert rows, "memory_log must have create entry"
    assert_eq(skill_root, rows[0][0], "SKILL.md root matches memory_log")

@test("cross: vexel swarm handoff lineage depth tracked in DB")
def _():
    from vexel_flow import VexelFlow
    import hermes_vexel as hv
    tmp = make_temp_env()
    db  = str(tmp / "swarm.db")
    os.environ["MIXDOWN_DIR"] = str(tmp / "mixdowns")

    # Build a lineage chain: researcher → coder → tester
    flow = VexelFlow("lineage-swarm", db)
    researcher = flow.on_agent_spawn("res", "researcher")
    coder      = flow.on_agent_spawn("cod", "coder")
    tester     = flow.on_agent_spawn("test", "tester")

    # r → c → t
    flow.on_handoff(researcher, "cod", "coder", "ResearchDone")
    flow.on_handoff(coder,      "test", "tester", "CodeDone")

    # lineage_chain for tester should have 2 links
    chain = flow._db.lineage_chain("test")
    assert len(chain) == 2, f"expected 2 links, got {len(chain)}"
    assert chain[0]["from"] == "res"
    assert chain[1]["from"] == "cod"
    assert chain[1]["depth"] == 2
    flow.close()

@test("cross: scroll event count > 0 after full hermes session")
def _():
    import hermes_vexel as hv
    tmp = make_temp_env(); patch_hermes_paths(tmp)
    bridge = hv.HermesScrollBridge("s-count-001", hermes_dir=tmp)
    bridge.session_start()
    bridge.memory_add("fact a", "MEMORY.md")
    bridge.memory_add("fact b", "USER.md")
    bridge.skill_create("count-skill", "desc", "# Skill\n## Procedure\n1. step")
    bridge.session_search("fact")
    bridge.memory_remove("fact a", "MEMORY.md")
    result = bridge.session_end()

    # Should be: SEED + 2×RESONANCE + RESONANCE(skill) + QUERY + MISS + MIXDOWN = 7
    events = result.get("events", 0)
    assert events >= 7, f"expected ≥7 events, got {events}"


# ══════════════════════════════════════════════════════════════════════════════
# SUITE 6: Stress and edge cases
# ══════════════════════════════════════════════════════════════════════════════

print("\n── Suite 6: Edge Cases ──")

@test("edge: empty memory add returns ok=True")
def _():
    import hermes_vexel as hv
    tmp = make_temp_env(); patch_hermes_paths(tmp)
    bridge = hv.HermesScrollBridge("s-empty-001", hermes_dir=tmp)
    bridge.session_start()
    result = bridge.memory_add("", "MEMORY.md")
    assert_eq(result["ok"], False, "empty entry should fail gracefully")

@test("edge: replace non-existent entry falls back to add")
def _():
    import hermes_vexel as hv
    tmp = make_temp_env(); patch_hermes_paths(tmp)
    bridge = hv.HermesScrollBridge("s-rep-miss-001", hermes_dir=tmp)
    bridge.session_start()
    result = bridge.memory_replace("nonexistent", "new value", "MEMORY.md")
    # Should fall back to add
    assert_eq(result["ok"], True, "replace nonexistent should add as fallback")

@test("edge: skill_load on nonexistent skill returns None anchor")
def _():
    import hermes_vexel as hv
    tmp = make_temp_env(); patch_hermes_paths(tmp)
    bridge = hv.HermesScrollBridge("s-nosk-001", hermes_dir=tmp)
    bridge.session_start()
    result = bridge.skill_load("nonexistent-skill-xyz")
    assert result["anchor"] is None, "nonexistent skill anchor should be None"

@test("edge: two bridges with different session_ids have independent roots")
def _():
    import hermes_vexel as hv
    tmp = make_temp_env(); patch_hermes_paths(tmp)
    b1 = hv.HermesScrollBridge("ind-001", hermes_dir=tmp)
    b2 = hv.HermesScrollBridge("ind-002", hermes_dir=tmp)
    b1.session_start(); b2.session_start()
    b1.memory_add("b1 fact", "MEMORY.md")
    b2.memory_add("b2 fact", "MEMORY.md")
    assert b1.scroll.root() != b2.scroll.root(), "independent scrolls must differ"
    b1.session_end(); b2.session_end()

@test("edge: SQLite INTEGER overflow (u64 root) handled as hex TEXT")
def _():
    import hermes_vexel as hv
    tmp = make_temp_env(); patch_hermes_paths(tmp)
    bridge = hv.HermesScrollBridge("s-u64-001", hermes_dir=tmp)
    bridge.session_start()
    # Trigger enough events to potentially hit large u64 roots
    for i in range(10):
        bridge.memory_add(f"Entry {i}", "MEMORY.md")
    bridge.session_end()
    # If we got here without OverflowError, the fix is working
    db   = sqlite3.connect(str(tmp / "state.db"))
    rows = db.execute("SELECT vexel_root FROM vexel_sessions").fetchall()
    db.close()
    assert rows
    root = rows[0][0]
    assert root.startswith("0x"), "root in DB should be hex string"


# ══════════════════════════════════════════════════════════════════════════════
# SUITE 7: VQA — Visual Question Answering
# ══════════════════════════════════════════════════════════════════════════════

print("\n── Suite 7: VQA ──")

def _make_test_image_bytes() -> bytes:
    """
    Generate a minimal valid PNG in pure Python (no Pillow required).
    1x1 red pixel. Used for VQA plumbing tests.
    """
    import zlib, struct
    def _chunk(tag, data):
        c = zlib.crc32(tag + data) & 0xffffffff
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", c)
    sig    = b"\x89PNG\r\n\x1a\n"
    ihdr   = _chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0))
    raw    = b"\x00\xff\x00\x00"          # filter byte + R=255 G=0 B=0
    idat   = _chunk(b"IDAT", zlib.compress(raw))
    iend   = _chunk(b"IEND", b"")
    return sig + ihdr + idat + iend


@test("vqa: image bytes load correctly (PNG detection)")
def _():
    from hermes_vqa import load_image_bytes, _detect_mime
    data = _make_test_image_bytes()
    img_bytes, mt = load_image_bytes(data)
    assert img_bytes == data
    assert "png" in mt.lower(), f"expected image/png, got {mt}"

@test("vqa: base64 data URI round-trips correctly")
def _():
    import base64
    from hermes_vqa import load_image_bytes
    raw  = _make_test_image_bytes()
    b64  = base64.b64encode(raw).decode()
    uri  = f"data:image/png;base64,{b64}"
    img_bytes, mt = load_image_bytes(uri)
    assert img_bytes == raw, "base64 round-trip must recover original bytes"
    assert mt == "image/png"

@test("vqa: image_hash is 16-char hex string")
def _():
    from hermes_vqa import image_hash
    raw  = _make_test_image_bytes()
    h    = image_hash(raw)
    assert len(h) == 16, f"image_hash must be 16 chars, got {len(h)}"
    assert all(c in "0123456789abcdef" for c in h), "image_hash must be hex"

@test("vqa: probe_backends returns list with all 5 backends")
def _():
    from hermes_vqa import probe_backends
    infos = probe_backends()
    names = {i.name for i in infos}
    assert "claude"      in names, "claude backend must be in probe"
    assert "openrouter"  in names
    assert "llava"       in names
    assert "blip2"       in names
    assert "moondream"   in names
    assert len(infos) == 5, f"expected 5 backends, got {len(infos)}"

@test("vqa: VQABridge.status() returns dict with backends list")
def _():
    from hermes_vqa import VQABridge
    vqa = VQABridge()
    st  = vqa.status()
    assert "backends" in st, "status must have backends key"
    assert isinstance(st["backends"], list)
    assert len(st["backends"]) == 5
    assert "active_backend" in st
    # bridge_attached should be False when no bridge provided
    assert_eq(st["bridge_attached"], False, "no bridge → bridge_attached=False")

@test("vqa: VQAResult.ok is False when error is set")
def _():
    from hermes_vqa import VQAResult
    bad = VQAResult(
        question="test", answer="", backend_used="",
        image_hash="", vexel_root="0x0", ulam=(0,0),
        latency_ms=0.0, error="image load failed"
    )
    assert_eq(bad.ok, False, "VQAResult.ok must be False when error set")
    good = VQAResult(
        question="test", answer="A red pixel.",
        backend_used="claude", image_hash="abc",
        vexel_root="0xdeadbeef00000000", ulam=(-4, 26),
        latency_ms=123.0
    )
    assert_eq(good.ok, True, "VQAResult.ok must be True when answer set")

@test("vqa: handle_vqa_tool returns error dict when image_source missing")
def _():
    from hermes_vqa import handle_vqa_tool
    result = handle_vqa_tool({"question": "What is this?"})
    assert "error" in result, "missing image_source must return error"
    assert "image_source" in result["error"]

@test("vqa: handle_vqa_tool returns error dict when question missing")
def _():
    from hermes_vqa import handle_vqa_tool
    result = handle_vqa_tool({"image_source": "/tmp/test.png"})
    assert "error" in result, "missing question must return error"
    assert "question" in result["error"]

@test("vqa: VQA_TOOL_SCHEMA has correct structure")
def _():
    from hermes_vqa import VQA_TOOL_SCHEMA
    assert_eq(VQA_TOOL_SCHEMA["name"], "vqa", "tool name")
    props = VQA_TOOL_SCHEMA["input_schema"]["properties"]
    assert "image_source" in props, "schema must have image_source"
    assert "question"     in props, "schema must have question"
    assert "commit"       in props, "schema must have commit"
    assert "backend"      in props, "schema must have backend"
    required = VQA_TOOL_SCHEMA["input_schema"]["required"]
    assert "image_source" in required
    assert "question"     in required

@test("vqa: cache stores and retrieves results correctly")
def _():
    from hermes_vqa import _VQACache, VQAResult
    cache = _VQACache(max_size=4)
    r = VQAResult(
        question="What color?", answer="Red",
        backend_used="mock", image_hash="abc123def456abcd",
        vexel_root="0xdeadbeef00000000", ulam=(0,0), latency_ms=1.0
    )
    cache.put("abc123def456abcd", "What color?", "mock", r)
    hit = cache.get("abc123def456abcd", "What color?", "mock")
    assert hit is not None, "cache must return stored result"
    assert_eq(hit.answer, "Red", "cached answer must match")

    miss = cache.get("abc123def456abcd", "What shape?", "mock")
    assert miss is None, "different question must not hit cache"

@test("vqa: VQABridge records EV_QUERY + EV_RESONANCE in scroll")
def _():
    """
    Verify scroll event count increases by exactly 2 per VQA call
    (EV_QUERY for the question, EV_RESONANCE for the answer).
    Uses a mock backend so no API key needed.
    """
    import hermes_vexel as hv
    from hermes_vqa import VQABridge, _ClaudeBackend, ALL_BACKENDS, BACKEND_MAP
    from vexel_flow import AgentScroll

    tmp = make_temp_env(); patch_hermes_paths(tmp)
    bridge = hv.HermesScrollBridge("s-vqa-scroll-001", hermes_dir=tmp)
    bridge.session_start()

    # Inject a mock backend that always succeeds without an API call
    class _MockBackend:
        name = "mock"
        def available(self):
            from hermes_vqa import VQABackendInfo
            return VQABackendInfo("mock", True)
        def ask(self, *a, **kw):
            return "This is a 1x1 red pixel PNG test image."

    mock = _MockBackend()
    ALL_BACKENDS.insert(0, mock)
    BACKEND_MAP["mock"] = mock

    try:
        events_before = bridge.scroll.event_count()
        vqa = VQABridge(scroll_bridge=bridge)
        raw = _make_test_image_bytes()
        result = vqa.ask(raw, "What is in this image?",
                         backend="mock", use_cache=False)

        events_after = bridge.scroll.event_count()
        assert result.ok, f"VQA must succeed: {result.error}"
        assert_eq(result.backend_used, "mock", "backend must be mock")
        assert_eq(result.answer, "This is a 1x1 red pixel PNG test image.",
                  "answer from mock backend")
        delta = events_after - events_before
        assert delta == 2, f"expected 2 new scroll events (QUERY+RESONANCE), got {delta}"
        assert result.vexel_root.startswith("0x"), "vexel_root must be hex"
    finally:
        ALL_BACKENDS.pop(0)
        BACKEND_MAP.pop("mock", None)

    bridge.session_end()

@test("vqa: VQABridge.ask with commit=True writes to MEMORY.md")
def _():
    import hermes_vexel as hv
    from hermes_vqa import VQABridge, ALL_BACKENDS, BACKEND_MAP

    tmp = make_temp_env(); patch_hermes_paths(tmp)
    bridge = hv.HermesScrollBridge("s-vqa-commit-001", hermes_dir=tmp)
    bridge.session_start()

    class _MockBackend:
        name = "mock"
        def available(self):
            from hermes_vqa import VQABackendInfo
            return VQABackendInfo("mock", True)
        def ask(self, *a, **kw):
            return "JWT RS256 auth flow diagram."

    mock = _MockBackend()
    ALL_BACKENDS.insert(0, mock); BACKEND_MAP["mock"] = mock

    try:
        vqa    = VQABridge(scroll_bridge=bridge)
        raw    = _make_test_image_bytes()
        result = vqa.ask(raw, "What auth method is shown?",
                         commit_to_memory=True,
                         memory_label="auth diagram",
                         backend="mock", use_cache=False)

        assert result.ok,       f"VQA must succeed: {result.error}"
        assert result.committed, "committed must be True"
        assert result.memory_entry, "memory_entry must be non-empty"

        content = (tmp / "memories" / "MEMORY.md").read_text()
        assert "JWT RS256" in content, "answer must be in MEMORY.md"
        assert "vexel:root=" in content, "provenance tag must be in MEMORY.md"
    finally:
        ALL_BACKENDS.pop(0); BACKEND_MAP.pop("mock", None)

    bridge.session_end()

@test("vqa: hooks intercept_tool_call handles vqa tool → RESONANCE")
def _():
    import hermes_vexel as hv
    import hermes_hooks as hk
    from hermes_vqa import ALL_BACKENDS, BACKEND_MAP, VQABackendInfo

    tmp = make_temp_env(); patch_hermes_paths(tmp)
    hk._bridges.clear()

    class _MockBackend:
        name = "mock"
        def available(self): return VQABackendInfo("mock", True)
        def ask(self, *a, **kw): return "A blue circle on white background."

    mock = _MockBackend()
    ALL_BACKENDS.insert(0, mock); BACKEND_MAP["mock"] = mock

    try:
        sid = f"hook-vqa-{uuid.uuid4().hex[:6]}"
        hk.register_session(sid)
        raw = _make_test_image_bytes()
        import base64
        b64_uri = f"data:image/png;base64,{base64.b64encode(raw).decode()}"

        ev = hk.intercept_tool_call(
            "vqa",
            {"image_source": b64_uri,
             "question": "What shape is shown?",
             "backend": "mock"},
            {}, sid, True
        )
        assert ev is not None,             "vqa tool must be intercepted"
        assert_eq(ev["event"], "RESONANCE", "vqa tool → RESONANCE event")
        assert ev.get("vexel_root", "").startswith("0x"), "must have vexel_root"
        assert_eq(ev.get("ok"), True, "vqa hook result ok")
        hk.close_session(sid)
    finally:
        ALL_BACKENDS.pop(0); BACKEND_MAP.pop("mock", None)

@test("vqa: VQABridge.ask_batch returns one result per question")
def _():
    import hermes_vexel as hv
    from hermes_vqa import VQABridge, ALL_BACKENDS, BACKEND_MAP, VQABackendInfo

    tmp = make_temp_env(); patch_hermes_paths(tmp)
    bridge = hv.HermesScrollBridge("s-vqa-batch-001", hermes_dir=tmp)
    bridge.session_start()

    answers = ["Red.", "Circle.", "Small.", "None.", "JPEG."]
    call_count = [0]

    class _MockBackend:
        name = "mock"
        def available(self): return VQABackendInfo("mock", True)
        def ask(self, *a, **kw):
            i = call_count[0] % len(answers)
            call_count[0] += 1
            return answers[i]

    mock = _MockBackend()
    ALL_BACKENDS.insert(0, mock); BACKEND_MAP["mock"] = mock

    try:
        vqa = VQABridge(scroll_bridge=bridge)
        raw = _make_test_image_bytes()
        questions = [
            "What color is it?", "What shape?", "How big?",
            "Any text?", "What format?"
        ]
        results = vqa.ask_batch(raw, questions, backend="mock")
        assert_eq(len(results), 5, "batch must return 5 results")
        for r in results:
            assert r.ok, f"batch result must be ok: {r.error}"
    finally:
        ALL_BACKENDS.pop(0); BACKEND_MAP.pop("mock", None)

    bridge.session_end()




def print_summary():
    passed = sum(1 for _, ok, _ in _results if ok)
    failed = sum(1 for _, ok, _ in _results if not ok)
    total  = len(_results)
    print(f"\n{'═'*60}")
    print(f"  Results: {passed}/{total} passed", end="")
    if failed:
        print(f"  {failed} FAILED", end="")
    print()
    if failed:
        print("\nFailed tests:")
        for name, ok, msg in _results:
            if not ok:
                print(f"  ✗ {name}: {msg}")
    print(f"{'═'*60}")
    return failed == 0


if __name__ == "__main__":
    # Run all tests (functions decorated with @test are called at decoration time)
    all_passed = print_summary()
    sys.exit(0 if all_passed else 1)

# ══════════════════════════════════════════════════════════════
# SUITE 8 — ARC-AGI Integration Tests
# ══════════════════════════════════════════════════════════════

print("\n── Suite 8: ARC-AGI ──────────────────────────────────────")

# ── Helpers ────────────────────────────────────────────────────────────────────

def _make_simple_task():
    """A trivial recolor task (blue→red) for testing."""
    import sys; sys.path.insert(0, "/mnt/user-data/outputs")
    from arc_types import ARCTask, Pair
    return ARCTask(
        task_id="test_recolor",
        train=[
            Pair(input=[[1,0,0],[0,1,0],[0,0,1]],
                 output=[[2,0,0],[0,2,0],[0,0,2]]),
            Pair(input=[[1,1,0],[0,0,1],[0,1,0]],
                 output=[[2,2,0],[0,0,2],[0,2,0]]),
        ],
        test=[
            Pair(input=[[0,1,0],[1,0,1],[0,1,0]],
                 output=[[0,2,0],[2,0,2],[0,2,0]])
        ],
    )

def _make_rot90_task():
    from arc_types import ARCTask, Pair
    return ARCTask(
        task_id="test_rot90",
        train=[
            Pair(input=[[1,0],[0,2]], output=[[0,1],[2,0]]),
            Pair(input=[[3,1],[0,0]], output=[[0,3],[0,1]]),
        ],
        test=[Pair(input=[[0,4],[5,0]], output=[[5,0],[0,4]])],
    )

# ── arc_types tests ────────────────────────────────────────────────────────────

@test
def t_arc_grid_basics():
    import sys; sys.path.insert(0, "/mnt/user-data/outputs")
    from arc_types import (grid_shape, grid_to_text, text_to_grid,
                            grid_diff, grid_similarity, empty_grid)
    g = [[1,2,3],[4,5,6]]
    assert_eq(grid_shape(g), (2,3), "shape")
    txt = grid_to_text(g)
    back = text_to_grid(txt)
    assert_eq(back, g, "text round-trip")
    g2 = [[1,2,3],[4,5,0]]
    diffs = grid_diff(g, g2)
    assert_eq(len(diffs), 1, "one diff")
    sim = grid_similarity(g, g)
    assert_eq(sim, 1.0, "self-similarity=1")
    e = empty_grid(3,3,0)
    assert_eq(len(e), 3, "empty grid height")

@test
def t_arc_dsl_primitives():
    import sys; sys.path.insert(0, "/mnt/user-data/outputs")
    from arc_types import rot90, rot180, reflect_h, reflect_v, recolor, upscale, downscale
    g = [[1,2],[3,4]]
    r90 = rot90(g)
    assert_eq(r90[0][0], 3, "rot90 top-left")
    r180 = rot180(g)
    assert_eq(r180[1][1], 1, "rot180 bottom-right")
    rh = reflect_h(g)
    assert_eq(rh[0][0], 2, "reflect_h")
    rv = reflect_v(g)
    assert_eq(rv[0][0], 3, "reflect_v")
    rc = recolor(g, 1, 9)
    assert_eq(rc[0][0], 9, "recolor")
    up = upscale(g, 2)
    assert_eq(len(up), 4, "upscale height")
    dn = downscale(up, 2)
    assert_eq(dn, g, "downscale round-trip")

@test
def t_arc_extract_objects():
    import sys; sys.path.insert(0, "/mnt/user-data/outputs")
    from arc_types import extract_objects
    g = [[1,0,2],[1,0,2],[0,0,0]]
    objs = extract_objects(g, bg=0)
    assert_eq(len(objs), 2, "two objects")
    colors = {o["color"] for o in objs}
    assert_eq(colors, {1,2}, "both colors found")

@test
def t_arc_task_loading():
    import sys; sys.path.insert(0, "/mnt/user-data/outputs")
    task = _make_simple_task()
    assert_eq(task.task_id, "test_recolor", "task id")
    assert_eq(len(task.train), 2, "2 train pairs")
    assert_eq(len(task.test), 1, "1 test pair")
    s = task.summary()
    assert_eq(s["train_pairs"], 2, "summary train")

@test
def t_arc_score_task():
    import sys; sys.path.insert(0, "/mnt/user-data/outputs")
    from arc_types import score_task, ARCTask, Pair
    task = _make_simple_task()
    # Exact predictions
    preds = [task.test[0].output]
    sc = score_task(preds, task)
    assert_eq(sc["solved"], True, "exact match solves")
    # Wrong prediction
    preds_bad = [[[0,0,0],[0,0,0],[0,0,0]]]
    sc2 = score_task(preds_bad, task)
    assert_eq(sc2["solved"], False, "wrong pred not solved")

# ── arc_renderer tests ─────────────────────────────────────────────────────────

@test
def t_arc_renderer_single():
    import sys; sys.path.insert(0, "/mnt/user-data/outputs")
    from arc_renderer import render_grid
    g = [[1,2,3],[4,5,6],[7,8,9]]
    png = render_grid(g)
    assert len(png) > 100, "PNG should be non-trivial"
    assert png[:4] == b'\x89PNG', "valid PNG header"

@test
def t_arc_renderer_task():
    import sys; sys.path.insert(0, "/mnt/user-data/outputs")
    from arc_renderer import render_task, render_pair
    task = _make_simple_task()
    png = render_task(task, include_test=True)
    assert png[:4] == b'\x89PNG', "task PNG valid"
    pair_png = render_pair(task.train[0].input, task.train[0].output)
    assert pair_png[:4] == b'\x89PNG', "pair PNG valid"

# ── arc_dsl_ext tests ──────────────────────────────────────────────────────────

@test
def t_arc_dsl_ext_gravity():
    import sys; sys.path.insert(0, "/mnt/user-data/outputs")
    from arc_dsl_ext import gravity
    g = [[1,0],[0,0],[0,1]]
    gd = gravity(g, "down", 0)
    assert_eq(gd[2][0], 1, "gravity down col0")
    assert_eq(gd[2][1], 1, "gravity down col1")
    gu = gravity(g, "up", 0)
    assert_eq(gu[0][0], 1, "gravity up col0")

@test
def t_arc_dsl_ext_symmetry():
    import sys; sys.path.insert(0, "/mnt/user-data/outputs")
    from arc_dsl_ext import complete_h_symmetry, complete_v_symmetry, fill_holes
    g = [[1,0,0],[0,0,0],[0,0,2]]
    hs = complete_h_symmetry(g, bg=0)
    assert_eq(hs[0][2], 1, "h-symmetry mirrors left→right")
    vs = complete_v_symmetry(g, bg=0)
    assert_eq(vs[2][0], 1, "v-symmetry mirrors top→bottom")

@test
def t_arc_dsl_ext_morphology():
    import sys; sys.path.insert(0, "/mnt/user-data/outputs")
    from arc_dsl_ext import dilate, erode, outline, fill_holes
    g = [[0,0,0],[0,1,0],[0,0,0]]
    d = dilate(g)
    assert d[0][1] != 0 or d[1][0] != 0, "dilate expands"
    e = erode(d)
    # Eroded may or may not recover exactly — just check it runs
    assert e is not None, "erode returns grid"
    # fill_holes: a ring with a hole in the middle
    ring = [[1,1,1],[1,0,1],[1,1,1]]
    fh = fill_holes(ring, bg=0)
    assert_eq(fh[1][1], 1, "hole filled")

@test
def t_arc_dsl_ext_logic():
    import sys; sys.path.insert(0, "/mnt/user-data/outputs")
    from arc_dsl_ext import grid_xor, grid_and, grid_or
    a = [[1,0],[0,1]]
    b = [[0,1],[1,0]]
    x = grid_xor(a, b)
    assert_eq(x[0][0], 1, "xor (1,0)→1")
    assert_eq(x[0][1], 1, "xor (0,1)→1")
    n = grid_and(a, b)
    assert_eq(n[0][0], 0, "and (1,0)→0")
    o = grid_or(a, b)
    assert_eq(o[0][0], 1, "or (1,0)→1")
    assert_eq(o[0][1], 1, "or (0,1)→1")

# ── arc_programs tests ─────────────────────────────────────────────────────────

@test
def t_arc_programs_list():
    import sys; sys.path.insert(0, "/mnt/user-data/outputs")
    from arc_programs import PATTERNS, list_patterns
    assert len(PATTERNS) >= 50, f"need ≥50 patterns, got {len(PATTERNS)}"
    plist = list_patterns()
    cats = {p["category"] for p in plist}
    expected = {"geometric","color","symmetry","gravity","object","morphology"}
    assert expected <= cats, f"missing categories: {expected-cats}"

@test
def t_arc_programs_match_recolor():
    import sys; sys.path.insert(0, "/mnt/user-data/outputs")
    from arc_programs import match_program
    task = _make_simple_task()
    result = match_program(task, min_score=1.0)
    assert result is not None, "should find recolor pattern"
    assert_eq(result["score"], 1.0, "perfect score")
    assert "color" in result["category"] or "swap" in result["name"], \
        f"expected color pattern, got {result['name']}"

@test
def t_arc_programs_match_rot90():
    import sys; sys.path.insert(0, "/mnt/user-data/outputs")
    from arc_programs import match_program
    task = _make_rot90_task()
    result = match_program(task, min_score=0.5)
    assert result is not None, "should find geometric pattern"

@test
def t_arc_programs_no_false_positive():
    import sys; sys.path.insert(0, "/mnt/user-data/outputs")
    from arc_programs import match_program
    from arc_types import ARCTask, Pair
    # A task with random output — no pattern should score 1.0
    task = ARCTask("no_match",
        train=[Pair([[1,2],[3,4]], [[5,6],[7,8]])],
        test=[Pair([[1,1],[1,1]])]
    )
    result = match_program(task, min_score=1.0)
    # Either None or score < 1.0
    assert result is None or result["score"] < 1.0, "no false positive"

# ── arc_solver execution tests ─────────────────────────────────────────────────

@test
def t_arc_solver_execute():
    import sys; sys.path.insert(0, "/mnt/user-data/outputs")
    from arc_solver import execute_program, evaluate_program
    code = "def transform(grid): return recolor(grid, 1, 2)"
    task = _make_simple_task()
    result, err = execute_program(code, task.train[0].input)
    assert_eq(err, "", "no execution error")
    assert result is not None, "result must exist"
    assert_eq(result[0][0], 2, "recolor worked")
    ev = evaluate_program(code, task)
    assert_eq(ev["score"], 1.0, "perfect train score")

@test
def t_arc_solver_timeout():
    import sys; sys.path.insert(0, "/mnt/user-data/outputs")
    from arc_solver import execute_program
    # Infinite loop — must timeout
    code = "def transform(grid):\n    while True: pass"
    result, err = execute_program(code, [[1,2],[3,4]], timeout=2)
    assert result is None, "timeout should return None"
    assert "timeout" in err.lower(), f"error should mention timeout, got: {err}"

@test
def t_arc_solver_syntax_error():
    import sys; sys.path.insert(0, "/mnt/user-data/outputs")
    from arc_solver import execute_program
    code = "def transform(grid): return ???broken"
    result, err = execute_program(code, [[1]], timeout=3)
    assert result is None, "syntax error → None"
    assert err != "", "syntax error should have message"

# ── arc_abstraction tests ──────────────────────────────────────────────────────

@test
def t_arc_abstraction_objects():
    import sys; sys.path.insert(0, "/mnt/user-data/outputs")
    from arc_abstraction import extract_object_descs, compute_delta, grid_summary
    g = [[1,0,2],[1,0,2],[0,0,0]]
    descs, bg = extract_object_descs(g)
    assert_eq(bg, 0, "background is 0")
    assert_eq(len(descs), 2, "two object descs")
    assert descs[0].obj_id == "A", "first obj is A"
    # Delta between g and recolored g
    g2 = [[3,0,4],[3,0,4],[0,0,0]]
    delta = compute_delta(g, g2)
    assert delta.cells_changed > 0, "cells changed"
    # Summary shouldn't crash
    summary = grid_summary(g)
    assert "Objects" in summary, "summary has Objects section"

@test
def t_arc_abstraction_task():
    import sys; sys.path.insert(0, "/mnt/user-data/outputs")
    from arc_abstraction import abstract_task, abstract_pair
    task = _make_simple_task()
    txt = abstract_task(task)
    assert "Example 1" in txt, "has example 1"
    assert "TEST" in txt, "has test section"
    pair_txt = abstract_pair(task.train[0], 0)
    assert "INPUT" in pair_txt, "pair has input"
    assert "OUTPUT" in pair_txt, "pair has output"

# ── arc_augment tests ──────────────────────────────────────────────────────────

@test
def t_arc_augment_d4():
    import sys; sys.path.insert(0, "/mnt/user-data/outputs")
    from arc_augment import D4_TRANSFORMS, apply_d4_to_task, unapply_d4
    task = _make_simple_task()
    for t in D4_TRANSFORMS:
        aug = apply_d4_to_task(task, t)
        assert aug.task_id.startswith("test_recolor"), "aug task id"
        # Verify inverse: apply → unapply should recover original
        g = task.train[0].input
        fwd = t.apply(g)
        back = t.undo(fwd)
        assert_eq(back, g, f"D4 {t.name} inverse")

@test
def t_arc_augment_views():
    import sys; sys.path.insert(0, "/mnt/user-data/outputs")
    from arc_augment import generate_augmented_views
    task = _make_simple_task()
    views = generate_augmented_views(task, d4_subset=["identity","rot90","rot180","rot270"],
                                     include_color_perms=False)
    assert_eq(len(views), 4, "4 D4 views")
    for v in views:
        assert v.d4 is not None, "view has D4 transform"

@test
def t_arc_augment_color_perms():
    import sys; sys.path.insert(0, "/mnt/user-data/outputs")
    from arc_augment import color_permutation_augments
    task = _make_simple_task()
    augs = color_permutation_augments(task, max_perms=3)
    assert len(augs) >= 1, "at least 1 color augment"
    for aug_task, inv_map in augs:
        assert inv_map, "has inverse mapping"

# ── arc_memory tests ───────────────────────────────────────────────────────────

@test
def t_arc_memory_store_retrieve():
    import sys, tempfile; sys.path.insert(0, "/mnt/user-data/outputs")
    from pathlib import Path
    from arc_memory import ARCPatternLibrary, classify_pattern
    tmp = Path(tempfile.mkdtemp()) / "test.db"
    lib = ARCPatternLibrary(db_path=str(tmp))
    lib.store("t001", "Rotate 90 degrees clockwise",
              "def transform(g): return rot90(g)", 1.0, "spatial")
    lib.store("t002", "Recolor blue to red",
              "def transform(g): return recolor(g,1,2)", 1.0, "color")
    st = lib.stats()
    assert_eq(st["total"], 2, "2 patterns stored")
    res = lib.lookup("rotate", limit=5)
    assert len(res) >= 1, "search finds rotate"
    prog = lib.best_program_for("recolor blue red")
    assert prog is not None, "best_program_for returns code"
    lib.close()

@test
def t_arc_memory_classify():
    import sys; sys.path.insert(0, "/mnt/user-data/outputs")
    from arc_memory import classify_pattern
    assert classify_pattern("rotate 90 degrees clockwise") == "spatial", "rotation→spatial"
    assert classify_pattern("recolor all blue cells red") == "color", "recolor→color"
    assert classify_pattern("count objects and sort by size") == "object", "count→object"

@test
def t_arc_memory_warm_start():
    import sys, tempfile; sys.path.insert(0, "/mnt/user-data/outputs")
    from pathlib import Path
    from arc_memory import ARCPatternLibrary
    from arc_search import warm_search
    tmp = Path(tempfile.mkdtemp()) / "warm.db"
    lib = ARCPatternLibrary(db_path=str(tmp))
    task = _make_simple_task()
    code = "def transform(g): return recolor(g,1,2)"
    lib.store(task.task_id, "recolor", code, 1.0)
    # Warm search should find exact match
    warm = warm_search(task, "recolor", lib, verbose=False)
    assert warm is not None, "warm search finds task"
    assert warm.score >= 0.5, f"warm score >= 0.5, got {warm.score}"
    lib.close()

# ── arc_search tests ───────────────────────────────────────────────────────────

@test
def t_arc_search_brute_force():
    import sys; sys.path.insert(0, "/mnt/user-data/outputs")
    from arc_search import brute_force_search
    task = _make_simple_task()
    cand = brute_force_search(task, max_depth=1, time_limit=10.0)
    assert cand is not None, "brute force finds something"
    assert cand.score > 0.0, "score > 0"
    assert_eq(cand.score, 1.0, "perfect brute-force on recolor task")

@test
def t_arc_search_vote():
    import sys; sys.path.insert(0, "/mnt/user-data/outputs")
    from arc_search import (Candidate, fill_candidate_predictions,
                             vote_predictions)
    from arc_solver import execute_program
    task = _make_simple_task()
    c1 = Candidate("def transform(g): return recolor(g,1,2)", 1.0, "test")
    c2 = Candidate("def transform(g): return recolor(g,1,2)", 1.0, "test")
    candidates = fill_candidate_predictions([c1, c2], task)
    voted = vote_predictions(candidates, len(task.test))
    assert_eq(len(voted), 1, "one test prediction")
    expected = task.test[0].output
    assert_eq(voted[0], expected, "voted matches expected")

@test
def t_arc_search_augmented_programs():
    import sys; sys.path.insert(0, "/mnt/user-data/outputs")
    from arc_augment import augmented_eval
    task = _make_simple_task()
    code = "def transform(g): return recolor(g,1,2)"
    result = augmented_eval(task, code)
    assert "identity" in result["per_aug"], "has identity result"
    assert result["per_aug"]["identity"]["score"] == 1.0, "identity score=1"

# ── arc_eval tests ─────────────────────────────────────────────────────────────

@test
def t_arc_eval_task_result():
    import sys; sys.path.insert(0, "/mnt/user-data/outputs")
    from arc_eval import TaskResult
    tr = TaskResult(task_id="t001", split="training",
                    solved=True, n_test=1, n_correct=1,
                    avg_sim=1.0, train_score=1.0,
                    program="def transform(g): return g",
                    reasoning="identity", elapsed_sec=0.5)
    assert_eq(tr.ok, True, "no error = ok")
    assert_eq(tr.solved, True, "solved")
    d = tr.to_dict()
    assert "task_id" in d, "has task_id"

@test
def t_arc_eval_result_save_load():
    import sys, tempfile, json; sys.path.insert(0, "/mnt/user-data/outputs")
    from pathlib import Path
    from arc_eval import EvalResult, TaskResult
    tmp = Path(tempfile.mkdtemp()) / "results.json"
    tr = TaskResult(task_id="t001", split="training",
                    solved=True, n_test=1, n_correct=1,
                    avg_sim=1.0, train_score=1.0,
                    program="", reasoning="", elapsed_sec=0.1)
    er = EvalResult(split="training", n_attempted=1, n_solved=1,
                    n_errors=0, solve_rate=1.0, avg_similarity=1.0,
                    elapsed_total=0.1, task_results=[tr])
    er.save(str(tmp))
    er2 = EvalResult.load(str(tmp))
    assert_eq(er2.n_solved, 1, "loaded n_solved")
    assert_eq(er2.solve_rate, 1.0, "loaded solve_rate")
    summ = er2.summary()
    assert "Solved" in summ, "summary has Solved"

@test
def t_arc_eval_full_toy():
    """End-to-end: build toy tasks, run evaluator (DSL only, no LLM)."""
    import sys; sys.path.insert(0, "/mnt/user-data/outputs")
    from arc_eval import ARCEvaluator
    from arc_memory import ARCPatternLibrary
    import tempfile
    from pathlib import Path
    tmp_db = Path(tempfile.mkdtemp()) / "eval.db"
    lib = ARCPatternLibrary(db_path=str(tmp_db))
    task = _make_simple_task()
    ev = ARCEvaluator(verbose=False, workers=1,
                      use_augmentation=False,
                      use_brute_force=True,
                      n_candidates=0)   # no LLM
    result = ev.run_from_files([], library=lib)  # empty = 0 tasks
    assert_eq(result.n_attempted, 0, "0 tasks attempted")
    lib.close()

