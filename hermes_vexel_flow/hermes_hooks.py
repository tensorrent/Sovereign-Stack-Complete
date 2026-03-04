"""
hermes_hooks.py — Hermes Tool Interception Layer
=================================================
Intercepts Hermes memory and skill tool calls, recording scroll events
for every memory write, read, remove, and skill lifecycle event.

Architecture
─────────────
Hermes uses a tool registry pattern (tools/registry.py → model_tools.py).
We inject ourselves at the model_tools layer via a PYTHONPATH-priority
wrapper: our model_tools.py shadows Hermes's model_tools.py and delegates
all non-memory calls unchanged.

Two integration modes:

  Mode A — Wrapper module (default, zero source modification):
    PYTHONPATH="/app/sovereign_sdk:..." means our model_tools.py is
    found before /app/hermes-agent/model_tools.py. We import the real
    one as _hermes_model_tools and proxy everything through.

  Mode B — Direct API (for programmatic use):
    SovereignHermesAgent wraps run_agent.AIAgent and intercepts
    tool responses via post-processing. Use when calling hermes
    programmatically rather than via CLI.

Intercepted tools → scroll events:
  memory(add)              → EV_RESONANCE score=2  (knowledge committed)
  memory(replace)          → EV_RESONANCE score=2  (knowledge updated)
  memory(remove)           → EV_MISS score=0        (knowledge dropped)
  memory(read)             → EV_QUERY score=1       (memory consulted)
  skill_manage(create)     → EV_RESONANCE score=3   (procedure crystallized)
  skill_manage(patch)      → EV_RESONANCE score=2   (procedure refined)
  skill_manage(delete)     → EV_MISS score=0        (procedure dropped)
  session_search           → EV_QUERY score=1       (history consulted)
  vqa(image, question)     → EV_QUERY score=1 + EV_RESONANCE score=3
  arc_solve(task)          → EV_QUERY + EV_RESONANCE/EV_MISS
  arc_pattern_search(q)    → EV_QUERY score=1
  arc_pattern_stats()      → EV_QUERY score=1
  arc_render(task)         → EV_QUERY score=1
  [all other tools]        → pass through, no scroll event

All other Hermes tools (web, terminal, browser, vision, etc.) are
completely unaffected — we only intercept memory-layer operations.
"""

import os
import sys
import json
import time
import uuid
import threading
from pathlib import Path
from typing import Any, Optional

# ── Resolve SDK path ──────────────────────────────────────────────────────────

SOVEREIGN_SDK = os.environ.get("SOVEREIGN_SDK", os.path.dirname(__file__))
if SOVEREIGN_SDK not in sys.path:
    sys.path.insert(0, SOVEREIGN_SDK)

from hermes_vexel import (
    HermesScrollBridge, HermesMemoryFile, HermesSkillFile,
    HERMES_DIR, MEMORIES_DIR, SKILLS_DIR, STATE_DB,
    MEMORY_CHAR_LIMIT, USER_CHAR_LIMIT,
)

# ── Session registry — one bridge per active session ─────────────────────────

_bridges: dict[str, HermesScrollBridge] = {}
_bridge_lock = threading.Lock()

def _get_bridge(session_id: str = None,
                agent_id: str = "hermes",
                swarm_id: str = None) -> HermesScrollBridge:
    """Get or create a bridge for the given session."""
    sid = session_id or _active_session_id() or "default-session"
    with _bridge_lock:
        if sid not in _bridges:
            _bridges[sid] = HermesScrollBridge(
                session_id=sid,
                agent_id=agent_id,
                swarm_id=swarm_id or os.environ.get(
                    "VEXEL_SWARM_ID", "hermes-swarm"),
                hermes_dir=HERMES_DIR,
            )
        return _bridges[sid]

def _active_session_id() -> Optional[str]:
    """
    Try to infer the active hermes session ID.
    Hermes stores sessions in state.db and logs in sessions/.
    We use the env var HERMES_SESSION_ID if set, else generate one.
    """
    return os.environ.get("HERMES_SESSION_ID")

def register_session(session_id: str,
                     agent_id: str = "hermes",
                     swarm_id: str = None) -> HermesScrollBridge:
    """Called at session start. Creates bridge and fires EV_SEED."""
    bridge = _get_bridge(session_id, agent_id, swarm_id)
    bridge.session_start()
    return bridge

def close_session(session_id: str) -> dict:
    """Called at session end. Fires EV_MIXDOWN, saves scroll."""
    with _bridge_lock:
        bridge = _bridges.get(session_id)
    if bridge:
        result = bridge.session_end()
        with _bridge_lock:
            _bridges.pop(session_id, None)
        return result
    return {"event": "MIXDOWN", "session_id": session_id, "note": "no bridge found"}


# ── Tool interception ─────────────────────────────────────────────────────────

# Memory tool action → (ev_type, score)
MEMORY_ACTION_MAP = {
    "add":     ("memory_add",     "MEMORY.md"),
    "replace": ("memory_replace", "MEMORY.md"),
    "remove":  ("memory_remove",  "MEMORY.md"),
    "read":    ("memory_read",    "MEMORY.md"),
}

SKILL_ACTION_MAP = {
    "create": "skill_create",
    "patch":  "skill_patch",
    "edit":   "skill_patch",   # treat edit as patch
    "delete": "skill_delete",
}


def intercept_tool_call(tool_name: str, tool_input: dict,
                        tool_result: Any,
                        session_id: str = None,
                        success: bool = True) -> Optional[dict]:
    """
    Called after a Hermes tool executes.
    Returns scroll event dict, or None if this tool is not intercepted.

    This is the single interception point for both Mode A (wrapper) and
    Mode B (SovereignHermesAgent subclass).
    """
    bridge = _get_bridge(session_id)

    # ── memory tool ───────────────────────────────────────────────────────
    if tool_name == "memory":
        action   = (tool_input.get("action") or "read").lower()
        content  = tool_input.get("content") or tool_input.get("entry") or ""
        old_text = tool_input.get("old_text") or tool_input.get("old") or ""
        file_ref = tool_input.get("file", "MEMORY.md")

        # Normalize file reference
        fname = os.path.basename(str(file_ref)).upper()
        if "USER" in fname:
            file_ref = "USER.md"
        else:
            file_ref = "MEMORY.md"

        if not success:
            # Tool failed — EV_MISS
            from vexel_flow import EV_MISS
            pin = bridge.scroll.record(f"memory:fail:{action}:{content[:32]}", EV_MISS)
            return {"event": "MISS", "tool": "memory", "action": action,
                    "vexel_root": f"0x{bridge.scroll.root():016x}"}

        if action == "add":
            return bridge.memory_add(content, file_ref)
        elif action == "replace":
            new_text = content or tool_input.get("new_text") or tool_input.get("new") or ""
            return bridge.memory_replace(old_text or content, new_text, file_ref)
        elif action == "remove":
            return bridge.memory_remove(content or old_text, file_ref)
        elif action in ("read", "get", "view"):
            return bridge.memory_read(file_ref)

    # ── skill_manage tool ──────────────────────────────────────────────────
    elif tool_name == "skill_manage":
        action      = (tool_input.get("action") or "read").lower()
        skill_name  = tool_input.get("name") or tool_input.get("skill_name") or "unnamed"
        content     = tool_input.get("content") or ""
        description = tool_input.get("description") or f"Skill: {skill_name}"

        if not success:
            from vexel_flow import EV_MISS
            pin = bridge.scroll.record(f"skill:fail:{action}:{skill_name}", EV_MISS)
            return {"event": "MISS", "tool": "skill_manage", "action": action}

        if action == "create":
            return bridge.skill_create(skill_name, description, content)
        elif action in ("patch", "edit"):
            old_str = tool_input.get("old_string") or tool_input.get("old") or ""
            new_str = tool_input.get("new_string") or tool_input.get("new") or content
            return bridge.skill_patch(skill_name, old_str, new_str)
        elif action == "delete":
            return bridge.skill_delete(skill_name)
        elif action in ("read", "load", "view"):
            return bridge.skill_load(skill_name)

    # ── session_search tool ────────────────────────────────────────────────
    elif tool_name == "session_search":
        query = tool_input.get("query") or tool_input.get("q") or ""
        return bridge.session_search(query)

    # ── vqa tool ──────────────────────────────────────────────────────────
    elif tool_name == "vqa":
        # Import lazily — VQA deps are optional
        try:
            from hermes_vqa import handle_vqa_tool
        except ImportError as e:
            return {"error": f"hermes_vqa not available: {e}",
                    "vexel_root": bridge.scroll.eigen()}

        if not success:
            from vexel_flow import EV_MISS
            bridge.scroll.record("vqa_fail:tool_error", EV_MISS, 0)
            return {"error": "vqa tool failed",
                    "vexel_root": bridge.scroll.eigen(),
                    "event": "MISS"}

        result = handle_vqa_tool(tool_input, scroll_bridge=bridge)
        # Normalise to hook-style event dict
        if "error" in result:
            return {"event": "MISS",  "vexel_root": result.get("vexel_root", "0x0"),
                    "error": result["error"]}
        return {"event": "RESONANCE", "vexel_root": result.get("vexel_root", "0x0"),
                "ok": True, **result}

    # ── ARC-AGI tools ─────────────────────────────────────────────────────
    elif tool_name.startswith("arc_"):
        try:
            from arc_hermes import handle_arc_tool
        except ImportError as e:
            return {"error": f"arc_hermes not available: {e}",
                    "vexel_root": bridge.scroll.eigen()}

        if not success:
            from vexel_flow import EV_MISS
            bridge.scroll.record(f"{tool_name}_fail", EV_MISS, 0)
            return {"error": f"{tool_name} failed",
                    "vexel_root": bridge.scroll.eigen(),
                    "event": "MISS"}

        result = handle_arc_tool(tool_name, tool_input, scroll_bridge=bridge)
        if result is None:
            return None  # Not an ARC tool we handle
        return result

    # ── Not intercepted ────────────────────────────────────────────────────
    return None


# ── Mode A: model_tools.py wrapper ───────────────────────────────────────────
#
# When PYTHONPATH="/app/sovereign_sdk:..." this file shadows Hermes's
# model_tools.py. We import the real one and proxy all calls.
#
# To activate Mode A: ensure SOVEREIGN_SDK comes before hermes-agent in PYTHONPATH.
# In the container this happens automatically from the ENV PYTHONPATH in Dockerfile.

def _load_real_model_tools():
    """Import Hermes's real model_tools without going through our shadow."""
    hermes_path = os.environ.get("HERMES_AGENT_PATH", "/app/hermes-agent")
    real_path = os.path.join(hermes_path, "model_tools.py")
    if not os.path.exists(real_path):
        return None
    import importlib.util
    spec = importlib.util.spec_from_file_location("_hermes_model_tools", real_path)
    mod  = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

# Lazy-load real model_tools on first call
_real_mt = None
_real_mt_lock = threading.Lock()

def _real_model_tools():
    global _real_mt
    if _real_mt is None:
        with _real_mt_lock:
            if _real_mt is None:
                _real_mt = _load_real_model_tools()
    return _real_mt


def handle_tool_call(tool_name: str, tool_input: dict,
                     session_id: str = None, **kwargs) -> Any:
    """
    Mode A entry point — called by Hermes as model_tools.handle_tool_call().
    Delegates to real implementation, then intercepts memory/skill results.
    """
    rmt = _real_model_tools()
    if rmt is None:
        raise RuntimeError(
            "hermes_hooks: cannot find Hermes model_tools.py — "
            "set HERMES_AGENT_PATH env var to hermes-agent root"
        )

    # Call the real tool
    success = True
    try:
        result = rmt.handle_tool_call(tool_name, tool_input,
                                      session_id=session_id, **kwargs)
    except Exception as e:
        result  = {"error": str(e)}
        success = False

    # Intercept — non-blocking, never raises
    try:
        scroll_event = intercept_tool_call(
            tool_name, tool_input, result, session_id, success)
        if scroll_event and os.environ.get("VEXEL_VERBOSE"):
            print(f"[vexel] {tool_name}:{tool_input.get('action','')} "
                  f"→ {scroll_event.get('event','')} "
                  f"root={scroll_event.get('vexel_root','?')}")
    except Exception as e:
        if os.environ.get("VEXEL_VERBOSE"):
            print(f"[vexel] intercept error: {e}")

    if not success:
        raise RuntimeError(result.get("error", "tool error"))
    return result


# ── Mode B: SovereignHermesAgent ─────────────────────────────────────────────

class SovereignHermesAgent:
    """
    Wraps Hermes's AIAgent to intercept memory and skill tool calls.

    Usage:
        agent = SovereignHermesAgent(
            model="anthropic/claude-sonnet-4",
            session_id="session-001",
        )
        agent.start_session()
        result = agent.run_conversation("Help me set up JWT auth")
        agent.end_session()
        print(result["final_response"])

    This is the preferred integration for programmatic use.
    For CLI use (hermes command), Mode A (wrapper module) is preferred.
    """

    def __init__(self, model: str = None,
                 enabled_toolsets: list = None,
                 session_id: str = None,
                 agent_id: str = "hermes",
                 swarm_id: str = None,
                 hermes_dir: Path = HERMES_DIR,
                 **kwargs):

        self.session_id = session_id or f"sovereign-{uuid.uuid4().hex[:8]}"
        self.agent_id   = agent_id
        self.swarm_id   = swarm_id or os.environ.get("VEXEL_SWARM_ID", "hermes-swarm")

        # Lazy-import AIAgent to avoid circular imports at module load time
        self._model            = model
        self._enabled_toolsets = enabled_toolsets
        self._kwargs           = kwargs
        self._ai_agent         = None
        self._bridge: Optional[HermesScrollBridge] = None

    def _ensure_agent(self):
        if self._ai_agent is None:
            hermes_path = os.environ.get("HERMES_AGENT_PATH", "/app/hermes-agent")
            if hermes_path not in sys.path:
                sys.path.insert(0, hermes_path)
            from run_agent import AIAgent
            opts = dict(self._kwargs)
            if self._model:
                opts["model"] = self._model
            if self._enabled_toolsets:
                opts["enabled_toolsets"] = self._enabled_toolsets
            self._ai_agent = AIAgent(**opts)

    def start_session(self) -> dict:
        """Initialize scroll bridge, fire EV_SEED."""
        self._bridge = HermesScrollBridge(
            session_id=self.session_id,
            agent_id=self.agent_id,
            swarm_id=self.swarm_id,
            hermes_dir=HERMES_DIR,
        )
        return self._bridge.session_start()

    def run_conversation(self, prompt: str, **kwargs) -> dict:
        """
        Run a hermes conversation with vexel interception active.
        Intercepts tool results via the tool_result_callback mechanism
        (if AIAgent supports it) or post-processes the transcript.
        """
        self._ensure_agent()
        if self._bridge is None:
            self.start_session()

        session_id = self.session_id
        bridge     = self._bridge

        # Inject our interception via environment (Mode A picks this up)
        old_sid = os.environ.get("HERMES_SESSION_ID")
        os.environ["HERMES_SESSION_ID"] = session_id

        try:
            result = self._ai_agent.run_conversation(prompt, **kwargs)
        finally:
            if old_sid:
                os.environ["HERMES_SESSION_ID"] = old_sid
            else:
                os.environ.pop("HERMES_SESSION_ID", None)

        # Post-process: scan tool calls in result for memory/skill events
        # (fallback for when Mode A wrapper is not active)
        tool_calls = result.get("tool_calls", []) or []
        for tc in tool_calls:
            tn = tc.get("name") or tc.get("tool_name", "")
            ti = tc.get("input") or tc.get("tool_input", {})
            tr = tc.get("result") or tc.get("tool_result", {})
            ok = not tc.get("error")
            try:
                intercept_tool_call(tn, ti, tr, session_id, ok)
            except Exception:
                pass

        return result

    def end_session(self) -> dict:
        """Fire EV_MIXDOWN, save scroll, close bridge."""
        if self._bridge:
            result = self._bridge.session_end()
            self._bridge = None
            return result
        return {"event": "MIXDOWN", "session_id": self.session_id, "note": "no bridge"}

    def memory_add(self, entry: str, file_ref: str = "MEMORY.md") -> dict:
        """Manually add a memory entry (e.g. from outside conversation)."""
        if self._bridge is None:
            self.start_session()
        return self._bridge.memory_add(entry, file_ref)

    def memory_read(self, file_ref: str = "MEMORY.md") -> str:
        if self._bridge is None:
            self.start_session()
        return self._bridge.memory_read(file_ref)["content"]

    def skill_create(self, name: str, description: str, content: str) -> dict:
        if self._bridge is None:
            self.start_session()
        return self._bridge.skill_create(name, description, content)

    def audit(self) -> dict:
        if self._bridge:
            return self._bridge.audit()
        return {}

    def stats(self) -> dict:
        if self._bridge:
            return self._bridge.stats()
        return {"session_id": self.session_id, "active": False}

    def __enter__(self):
        self.start_session()
        return self

    def __exit__(self, *_):
        self.end_session()


# ── Hermes gateway hook (for gateway mode) ────────────────────────────────────

class GatewayHookAdapter:
    """
    Bridges Hermes gateway session lifecycle to vexel scroll events.

    Hermes gateway creates sessions per messaging platform conversation.
    Each session gets its own scroll, keyed by platform:chat_id.

    Usage (in gateway adapters):
        adapter = GatewayHookAdapter()
        adapter.on_session_create("telegram", "123456789")
        adapter.on_message_processed("telegram", "123456789",
                                     tool_calls=[...])
        adapter.on_session_close("telegram", "123456789")
    """

    def __init__(self, swarm_id: str = None):
        self.swarm_id = swarm_id or os.environ.get("VEXEL_SWARM_ID", "hermes-swarm")
        self._sessions: dict[str, str] = {}  # platform:chat_id → session_id

    def _key(self, platform: str, chat_id: str) -> str:
        return f"{platform}:{chat_id}"

    def on_session_create(self, platform: str, chat_id: str,
                          model: str = "unknown") -> dict:
        key        = self._key(platform, chat_id)
        session_id = f"{platform}-{chat_id}-{int(time.time())}"
        self._sessions[key] = session_id
        bridge = _get_bridge(session_id, f"hermes-{platform}", self.swarm_id)
        st = bridge.session_start()
        st["platform"]  = platform
        st["chat_id"]   = chat_id
        return st

    def on_tool_executed(self, platform: str, chat_id: str,
                         tool_name: str, tool_input: dict,
                         tool_result: Any, success: bool = True) -> Optional[dict]:
        key        = self._key(platform, chat_id)
        session_id = self._sessions.get(key)
        if not session_id:
            return None
        return intercept_tool_call(tool_name, tool_input, tool_result,
                                   session_id, success)

    def on_session_close(self, platform: str, chat_id: str) -> dict:
        key        = self._key(platform, chat_id)
        session_id = self._sessions.pop(key, None)
        if session_id:
            return close_session(session_id)
        return {"event": "MIXDOWN", "platform": platform, "chat_id": chat_id,
                "note": "session not found"}

    def active_sessions(self) -> dict:
        return dict(self._sessions)


# ── CLI: batch intercept tool events from stdin ───────────────────────────────
#
# Used by hermes post-processing scripts or gateway hooks:
#   echo '{"tool":"memory","input":{"action":"add","content":"JWT preferred"},"session":"s1"}' \
#     | python3 hermes_hooks.py intercept

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Hermes vexel hook CLI")
    parser.add_argument("command", choices=["intercept", "start", "end",
                                             "audit", "demo"])
    parser.add_argument("--session", default=None)
    parser.add_argument("--agent",   default="hermes")
    parser.add_argument("--swarm",   default=None)
    args = parser.parse_args()

    if args.command == "start":
        bridge = register_session(
            args.session or f"session-{int(time.time())}",
            args.agent, args.swarm)
        print(json.dumps(bridge.stats()))

    elif args.command == "end":
        result = close_session(args.session or "default-session")
        print(json.dumps(result))

    elif args.command == "intercept":
        # Read JSON event from stdin
        raw  = sys.stdin.read().strip()
        data = json.loads(raw) if raw else {}
        tn   = data.get("tool") or data.get("tool_name", "")
        ti   = data.get("input") or data.get("tool_input", {})
        tr   = data.get("result") or data.get("tool_result", {})
        sid  = data.get("session") or args.session
        ok   = data.get("success", True)
        ev   = intercept_tool_call(tn, ti, tr, sid, ok)
        print(json.dumps(ev or {"event": "passthrough", "tool": tn}))

    elif args.command == "audit":
        bridge = _get_bridge(args.session or "audit", args.agent, args.swarm)
        print(json.dumps(bridge.audit(), indent=2))

    elif args.command == "demo":
        print(f"\n{'═'*60}")
        print(f"  HERMES HOOKS DEMO")
        print(f"{'═'*60}\n")

        import tempfile
        from hermes_vexel import (HERMES_DIR as _HD,
            MEMORIES_DIR as _MD, SKILLS_DIR as _SD, STATE_DB as _SDB)

        # Override paths for isolated demo
        import hermes_vexel as _hv
        tmp = Path(tempfile.mkdtemp())
        _hv.HERMES_DIR   = tmp
        _hv.MEMORIES_DIR = tmp / "memories"
        _hv.SKILLS_DIR   = tmp / "skills"
        _hv.STATE_DB     = tmp / "state.db"
        _hv.MEMORY_FILE  = tmp / "memories" / "MEMORY.md"
        _hv.USER_FILE    = tmp / "memories" / "USER.md"
        globals()['HERMES_DIR']   = tmp
        globals()['MEMORIES_DIR'] = tmp / "memories"
        globals()['SKILLS_DIR']   = tmp / "skills"
        globals()['STATE_DB']     = tmp / "state.db"

        # Simulate a hermes session via tool interception
        sid = "demo-hooks-001"
        bridge = register_session(sid, "hermes-demo", "demo-swarm")
        print(f"Session started: root={bridge.scroll.root():016x}")

        # Simulate: model calls memory(action=add, content=..., file=MEMORY.md)
        events = [
            ("memory", {"action": "add",
                         "content": "Project uses FastAPI + Postgres",
                         "file": "MEMORY.md"}),
            ("memory", {"action": "add",
                         "content": "User prefers minimal prose, code-first",
                         "file": "USER.md"}),
            ("memory", {"action": "add",
                         "content": "Docker backend configured at /var/hermes",
                         "file": "MEMORY.md"}),
            ("memory", {"action": "replace",
                         "old_text": "Project uses FastAPI + Postgres",
                         "content": "Project uses FastAPI + Postgres + Redis",
                         "file": "MEMORY.md"}),
            ("skill_manage", {"action": "create",
                               "name": "fastapi-setup",
                               "description": "FastAPI project setup",
                               "content": "# FastAPI Setup\n## Procedure\n1. uvicorn main:app --reload\n"}),
            ("session_search", {"query": "FastAPI"}),
            ("memory", {"action": "remove",
                         "content": "Docker backend configured at /var/hermes",
                         "file": "MEMORY.md"}),
        ]

        print("\nSimulated tool calls:")
        for tool_name, tool_input in events:
            ev = intercept_tool_call(tool_name, tool_input, {}, sid, True)
            if ev:
                action = tool_input.get("action", "")
                root   = ev.get("vexel_root", "?")
                event  = ev.get("event", "?")
                print(f"  {tool_name:<15} {action:<10} → {event:<12} root={root}")

        # End session
        result = close_session(sid)
        print(f"\nSession end:")
        print(f"  root   : {result.get('vexel_root', '?')}")
        print(f"  events : {result.get('events', '?')}")

        # Show MEMORY.md with provenance
        mem = (tmp / "memories" / "MEMORY.md").read_text()
        print(f"\nMEMORY.md:")
        for line in mem.strip().split("\n"):
            print(f"  {line}")

        print(f"\n{'─'*60}")
        print(f"  Tool interception complete. Scroll is sovereign.")
        print(f"{'─'*60}\n")

        # Restore
        _hv.HERMES_DIR = _HD; _hv.MEMORIES_DIR = _MD
        _hv.SKILLS_DIR = _SD; _hv.STATE_DB = _SDB
