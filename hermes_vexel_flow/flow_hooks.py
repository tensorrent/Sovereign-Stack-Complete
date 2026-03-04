"""
flow_hooks.py — Claude Flow Hook Integration
=============================================
These are the hook handlers that claude-flow calls at key lifecycle
points. Claude-flow hooks fire as stdin JSON, return JSON on stdout.

Hook events and their vexel mappings:
  SessionStart  → vexel EV_SEED   (agent wakes, gets identity)
  PreToolUse    → vexel EV_QUERY  (agent about to act)
  PostToolUse   → vexel EV_RESONANCE/EV_MISS (action completed/failed)
  SessionEnd    → vexel EV_MIXDOWN (scroll committed, root stored)

Install in .claude/settings.json:
{
  "hooks": {
    "SessionStart": [
      {"type": "command",
       "command": "python3 /app/sovereign_sdk/flow_hooks.py session_start"}
    ],
    "PreToolUse": [
      {"type": "command",
       "command": "python3 /app/sovereign_sdk/flow_hooks.py pre_tool"}
    ],
    "PostToolUse": [
      {"type": "command",
       "command": "python3 /app/sovereign_sdk/flow_hooks.py post_tool"}
    ],
    "SessionEnd": [
      {"type": "command",
       "command": "python3 /app/sovereign_sdk/flow_hooks.py session_end"}
    ]
  }
}

Hook payload format (JSON on stdin):
  session_start: {"session_id": "...", "model": "..."}
  pre_tool:      {"session_id": "...", "tool_name": "...", "tool_input": {...}}
  post_tool:     {"session_id": "...", "tool_name": "...",
                  "tool_response": {...}, "success": true}
  session_end:   {"session_id": "...", "total_cost": 0.0}

Return JSON on stdout with at minimum {"status": "ok"}.
"""

import os
import sys
import json
import time
import hashlib

# ── Environment ───────────────────────────────────────────────────────────────
SOVEREIGN_SDK = os.environ.get("SOVEREIGN_SDK", os.path.dirname(__file__))
SWARM_DB      = os.environ.get("SWARM_DB",      ".swarm/memory.db")
TRINITY_LIB   = os.environ.get("TRINITY_LIB",  "/app/libtrinity.so")

sys.path.insert(0, SOVEREIGN_SDK)

from vexel_flow import VexelFlow, AgentScroll, SwarmDB, trinity
import ctypes

# ── Session → Swarm mapping ───────────────────────────────────────────────────
# Claude-flow sessions map to swarm agents. We treat each session as one agent.
# For multi-agent swarms, agent_id is set via env VEXEL_AGENT_ID.

def _session_to_agent(session_id: str) -> tuple[str, str, str]:
    """
    Map a claude-flow session to (swarm_id, agent_id, role).
    Override with env vars for explicit assignment.
    """
    swarm_id = os.environ.get("VEXEL_SWARM_ID",
                              f"swarm-{session_id[:8]}")
    agent_id = os.environ.get("VEXEL_AGENT_ID",
                              f"agent-{session_id[:12]}")
    role     = os.environ.get("VEXEL_AGENT_ROLE", "coder")
    return swarm_id, agent_id, role


def _make_scroll(swarm_id: str, agent_id: str, role: str) -> AgentScroll:
    """Create a transient scroll for a hook call (stateless)."""
    return AgentScroll(
        agent_id=agent_id, role=role, swarm_id=swarm_id
    )


def _charge(text: str) -> int:
    """Compute BRA eigen charge for arbitrary text."""
    lib = trinity()
    b   = text.encode() if text else b"_"
    h   = ctypes.c_uint64(0)
    tr  = ctypes.c_int64(0)
    dt  = ctypes.c_int64(0)
    lib.bra_eigen_charge(b, len(b),
        ctypes.byref(h), ctypes.byref(tr), ctypes.byref(dt))
    return h.value


# ── Tool classification ───────────────────────────────────────────────────────

# Claude-flow MCP tools that represent strong knowledge events → EV_RESONANCE
RESONANCE_TOOLS = {
    "mcp__claude-flow__memory_usage",     # memory written
    "mcp__claude-flow__neural_train",     # pattern learned
    "mcp__claude-flow__task_orchestrate", # task planned
    "Write", "Edit", "MultiEdit",         # code produced
    "Bash",                               # command executed
}

# Tools that represent coordination signals → EV_QUERY
QUERY_TOOLS = {
    "mcp__claude-flow__swarm_init",
    "mcp__claude-flow__agent_spawn",
    "mcp__claude-flow__swarm_status",
    "mcp__claude-flow__agent_list",
    "mcp__claude-flow__task_status",
    "Read", "Glob", "Grep",              # information gathered
    "TodoWrite", "TodoRead",
}

def _classify_tool(tool_name: str, success: bool) -> tuple[int, int]:
    """Returns (ev_type, score) for a tool call."""
    if not success:
        return 3, 0   # EV_MISS
    if tool_name in RESONANCE_TOOLS:
        return 1, 2   # EV_RESONANCE
    if tool_name in QUERY_TOOLS:
        return 2, 1   # EV_QUERY
    return 2, 1       # default: EV_QUERY


# ── Hook handlers ─────────────────────────────────────────────────────────────

def handle_session_start(payload: dict) -> dict:
    """
    Agent wakes. Give it a vexel identity.
    Records EV_SEED in scroll and registers in .swarm/memory.db.
    """
    session_id = payload.get("session_id", "unknown")
    model      = payload.get("model", "unknown")
    swarm_id, agent_id, role = _session_to_agent(session_id)

    try:
        flow   = VexelFlow(swarm_id, SWARM_DB)
        scroll = flow.on_agent_spawn(agent_id, role)
        root   = f"0x{scroll.root():016x}"
        x, y   = scroll.ulam()
        result = {
            "status":    "ok",
            "event":     "SEED",
            "swarm_id":  swarm_id,
            "agent_id":  agent_id,
            "role":      role,
            "vexel_root": root,
            "ulam":      [x, y],
            "model":     model,
        }
    except Exception as e:
        result = {"status": "warn", "error": str(e),
                  "message": "vexel session_start failed — continuing without vexel"}

    return result


def handle_pre_tool(payload: dict) -> dict:
    """
    Agent about to use a tool. Record EV_QUERY into scroll.
    Hook can optionally block the tool call (return {"action":"block"}).
    We never block — we just record.
    """
    session_id = payload.get("session_id", "unknown")
    tool_name  = payload.get("tool_name", "unknown")
    tool_input = payload.get("tool_input", {})
    swarm_id, agent_id, role = _session_to_agent(session_id)

    try:
        db   = SwarmDB(SWARM_DB)
        info = db.get_agent(agent_id)
        db.close()

        if info and not info.get("dissolved"):
            scroll = _make_scroll(swarm_id, agent_id, role)
            label  = f"pre:{tool_name}:{json.dumps(tool_input)[:64]}"
            pin    = scroll.record(label, 2, 1)   # EV_QUERY
            root   = f"0x{scroll.root():016x}"
        else:
            root = "not_registered"
            pin  = 0

        result = {
            "status":     "ok",
            "event":      "QUERY",
            "tool_name":  tool_name,
            "vexel_root": root,
            "prime_pin":  f"0x{pin:016x}",
        }
    except Exception as e:
        result = {"status": "warn", "error": str(e)}

    return result


def handle_post_tool(payload: dict) -> dict:
    """
    Agent completed a tool call. Record EV_RESONANCE or EV_MISS.
    """
    session_id   = payload.get("session_id", "unknown")
    tool_name    = payload.get("tool_name", "unknown")
    tool_response = payload.get("tool_response", {})
    success      = payload.get("success", True)
    swarm_id, agent_id, role = _session_to_agent(session_id)

    ev_type, score = _classify_tool(tool_name, success)
    ev_label = {1: "RESONANCE", 2: "QUERY", 3: "MISS"}[ev_type]

    try:
        db   = SwarmDB(SWARM_DB)
        info = db.get_agent(agent_id)
        db.close()

        if info and not info.get("dissolved"):
            scroll  = _make_scroll(swarm_id, agent_id, role)
            status  = "ok" if success else "fail"
            label   = f"post:{tool_name}:{status}"
            pin     = scroll.record(label, ev_type, score)

            # For memory writes: extract key/value and write to DB
            if (tool_name == "mcp__claude-flow__memory_usage"
                    and success and isinstance(tool_response, dict)):
                key = tool_response.get("key", "")
                val = tool_response.get("value", "")
                if key:
                    flow = VexelFlow(swarm_id, SWARM_DB)
                    flow.on_memory_write(scroll, key, str(val)[:256])

            root = f"0x{scroll.root():016x}"
        else:
            root = "not_registered"
            pin  = 0

        result = {
            "status":     "ok",
            "event":      ev_label,
            "tool_name":  tool_name,
            "success":    success,
            "vexel_root": root,
            "prime_pin":  f"0x{pin:016x}",
        }
    except Exception as e:
        result = {"status": "warn", "error": str(e)}

    return result


def handle_session_end(payload: dict) -> dict:
    """
    Session ending. EV_MIXDOWN, save scroll, record root in DB.
    """
    session_id  = payload.get("session_id", "unknown")
    total_cost  = payload.get("total_cost", 0.0)
    swarm_id, agent_id, role = _session_to_agent(session_id)

    try:
        db   = SwarmDB(SWARM_DB)
        info = db.get_agent(agent_id)
        db.close()

        if info and not info.get("dissolved"):
            flow   = VexelFlow(swarm_id, SWARM_DB)
            scroll = _make_scroll(swarm_id, agent_id, role)
            st     = flow.on_session_end(scroll)
            result = {
                "status":      "ok",
                "event":       "MIXDOWN",
                "agent_id":    agent_id,
                "vexel_root":  st.get("root", "unknown"),
                "events":      st.get("events", 0),
                "scroll_path": st.get("scroll_path", ""),
                "total_cost":  total_cost,
            }
        else:
            result = {
                "status": "ok",
                "event":  "MIXDOWN",
                "note":   "agent not in vexel registry, skipped",
            }
    except Exception as e:
        result = {"status": "warn", "error": str(e)}

    return result


# ── Dispatcher ────────────────────────────────────────────────────────────────

HANDLERS = {
    "session_start": handle_session_start,
    "pre_tool":      handle_pre_tool,
    "post_tool":     handle_post_tool,
    "session_end":   handle_session_end,
}


def main():
    if len(sys.argv) < 2:
        print(json.dumps({"status": "error",
                          "message": "Usage: flow_hooks.py <hook_type>"}))
        sys.exit(1)

    hook_type = sys.argv[1]

    # Read JSON payload from stdin
    try:
        raw = sys.stdin.read()
        payload = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError:
        payload = {}

    handler = HANDLERS.get(hook_type)
    if not handler:
        print(json.dumps({"status": "error",
                          "message": f"Unknown hook type: {hook_type}"}))
        sys.exit(1)

    result = handler(payload)
    print(json.dumps(result))


if __name__ == "__main__":
    main()
