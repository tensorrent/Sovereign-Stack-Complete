"""
flow_agent.py — SovereignAgent
================================
A Claude Flow agent that carries a sovereign vexel identity through
its entire lifecycle: spawn → work → coordinate → handoff → dissolve.

This is the application layer that ties VexelFlow to actual claude-flow
agent behavior. Use it as the base class for custom specialized agents,
or directly to mirror what claude-flow's swarm orchestrator does.

Philosophy:
  The agent is bonded to the swarm, not bound.
  It forms bonds with other agents by choice.
  On completion, it prepares a handoff packet — scroll intact.
  Its successor receives the lineage, not a blank slate.

Example:
    swarm = VexelFlow("research-swarm-001")

    researcher = SovereignAgent("r-001", "researcher", swarm)
    coder      = SovereignAgent("c-001", "coder", swarm)

    researcher.assign_task("Survey existing auth libraries")
    researcher.store_memory("auth_survey", "JWT + PASETO are best options")
    researcher.coordinate(coder, "Here is my survey: JWT for now")
    researcher.complete_task("Survey existing auth libraries")

    # Researcher hands off to coder
    researcher.handoff_to(coder, reason="ResearchComplete")

    coder.assign_task("Implement JWT auth endpoint")
    coder.complete_task("Implement JWT auth endpoint")
    coder.end_session()
"""

import os
import sys
import time
import json
import uuid
from typing import Optional

from vexel_flow import VexelFlow, AgentScroll, EV_QUERY, EV_RESONANCE, EV_MISS


# ── Agent roles (mirrors claude-flow agent types) ─────────────────────────────

ROLES = {
    "researcher":   "Gathers information, surveys options, synthesizes findings",
    "coder":        "Implements features, writes tests, refactors code",
    "analyst":      "Analyzes data, identifies patterns, optimizes performance",
    "tester":       "Validates behavior, runs tests, files bugs",
    "coordinator":  "Orchestrates work, manages dependencies, tracks progress",
    "reviewer":     "Reviews code, enforces quality, provides feedback",
    "architect":    "Designs systems, defines interfaces, makes tradeoffs",
}


class SovereignAgent:
    """
    A Claude Flow agent with a sovereign vexel identity.

    Every action the agent takes is recorded in its scroll:
      - Task assignments  → EV_QUERY
      - Memory writes     → EV_RESONANCE
      - Consensus events  → EV_RESONANCE or EV_QUERY
      - Idle/waiting      → EV_MISS
      - Session end       → EV_MIXDOWN

    The scroll is the agent's unforgeable history. On handoff,
    the lineage_depth increments and the successor inherits the chain.
    """

    def __init__(self, agent_id: str, role: str, flow: VexelFlow):
        if role not in ROLES:
            raise ValueError(f"Unknown role '{role}'. Valid: {list(ROLES)}")
        self.agent_id  = agent_id
        self.role      = role
        self.flow      = flow
        self._scroll: AgentScroll = flow.on_agent_spawn(agent_id, role)
        self._tasks_assigned   = 0
        self._tasks_completed  = 0
        self._tasks_failed     = 0
        self._bonds: set[str]  = set()   # agent_ids we have coordinated with
        self._active           = True

    # ── Task lifecycle ─────────────────────────────────────────────────────

    def assign_task(self, task: str) -> int:
        """Receive a task from the coordinator. Returns prime_pin."""
        self._require_active()
        self._tasks_assigned += 1
        return self.flow.on_task_assign(self._scroll, task)

    def complete_task(self, task: str, success: bool = True) -> int:
        """Mark a task complete (or failed). Returns prime_pin."""
        self._require_active()
        if success:
            self._tasks_completed += 1
        else:
            self._tasks_failed += 1
        return self.flow.on_task_complete(self._scroll, task, success)

    def fail_task(self, task: str) -> int:
        """Mark a task as failed."""
        return self.complete_task(task, success=False)

    # ── Memory ────────────────────────────────────────────────────────────

    def store_memory(self, key: str, value: str) -> int:
        """
        Write to claude-flow shared_state AND record in vexel scroll.
        This is the key integration point: memory writes are scroll events.
        Returns prime_pin.
        """
        self._require_active()
        return self.flow.on_memory_write(self._scroll, key, value)

    # ── Coordination ──────────────────────────────────────────────────────

    def coordinate(self, other: "SovereignAgent", message: str) -> int:
        """
        Send a coordination message to another agent.
        Records on BOTH scrolls: sender gets EV_QUERY (sent), 
        receiver gets EV_QUERY (received).
        Returns sender's prime_pin.
        """
        self._require_active()
        self._bonds.add(other.agent_id)
        other._bonds.add(self.agent_id)
        # Record on sender
        pin = self.flow.on_coordination_msg(
            self._scroll, other.agent_id, f"→{other.agent_id}: {message}")
        # Record on receiver
        self.flow.on_coordination_msg(
            other._scroll, self.agent_id, f"←{self.agent_id}: {message}")
        return pin

    def propose_consensus(self, topic: str) -> int:
        """Propose a consensus value. Records as EV_QUERY (pending)."""
        self._require_active()
        return self.flow.on_consensus(self._scroll, topic, reached=False)

    def accept_consensus(self, topic: str) -> int:
        """Mark consensus as reached. Records as EV_RESONANCE."""
        self._require_active()
        return self.flow.on_consensus(self._scroll, topic, reached=True)

    def idle(self, reason: str = "waiting") -> int:
        """Agent is waiting on dependencies. Records as EV_MISS."""
        self._require_active()
        return self.flow.on_idle(self._scroll, reason)

    # ── Handoff — sovereignty in motion ──────────────────────────────────

    def handoff_to(self, successor: "SovereignAgent",
                   reason: str = "WorkComplete") -> AgentScroll:
        """
        Transfer work to a successor agent.
        This agent's scroll is saved. The successor's scroll is seeded
        with the lineage — it knows it continues from this agent.

        The agent is bonded to the swarm, not bound.
        It leaves voluntarily, scroll intact.

        Returns the successor's new AgentScroll.
        """
        self._require_active()
        new_scroll = self.flow.on_handoff(
            self._scroll, successor.agent_id, successor.role, reason
        )
        # Null out old scroll ptr BEFORE replacing it — prevents double-free
        # in __del__ since on_handoff already freed it via the flow registry
        old = successor._scroll
        old._ptr = 0   # __del__ checks this before calling vexel_free
        successor._scroll = new_scroll
        self._active = False
        return new_scroll

    def end_session(self) -> dict:
        """
        Session complete. Mixdown, save scroll, dissolve.
        Returns final stats.
        """
        self._require_active()
        self._active = False
        st = self.flow.on_session_end(self._scroll)
        st.update({
            "tasks_assigned":  self._tasks_assigned,
            "tasks_completed": self._tasks_completed,
            "tasks_failed":    self._tasks_failed,
            "bonds":           list(self._bonds),
        })
        return st

    # ── Introspection ──────────────────────────────────────────────────────

    def root(self) -> str:
        return f"0x{self._scroll.root():016x}"

    def ulam(self) -> tuple:
        return self._scroll.ulam()

    def stats(self) -> dict:
        s = self._scroll.stats()
        s.update({
            "tasks_assigned":  self._tasks_assigned,
            "tasks_completed": self._tasks_completed,
            "tasks_failed":    self._tasks_failed,
            "bonds":           list(self._bonds),
            "active":          self._active,
            "role_description": ROLES.get(self.role, ""),
        })
        return s

    def _require_active(self):
        if not self._active:
            raise RuntimeError(
                f"Agent {self.agent_id} is dissolved. "
                "Create a new agent or use the handoff successor."
            )

    def __repr__(self) -> str:
        x, y = self.ulam()
        return (f"SovereignAgent(id={self.agent_id}, role={self.role}, "
                f"root={self.root()}, ulam=({x},{y}), "
                f"active={self._active})")


# ── SwarmSession — convenience orchestrator ───────────────────────────────────

class SwarmSession:
    """
    Manage a full claude-flow swarm session with vexel identities.

    Mirrors what claude-flow's swarm_init + agent_spawn does,
    but every agent gets a sovereign scroll.

    Example:
        with SwarmSession("my-swarm", topology="hierarchical") as s:
            researcher = s.spawn("r-001", "researcher")
            coder      = s.spawn("c-001", "coder")
            tester     = s.spawn("t-001", "tester")

            researcher.assign_task("survey auth options")
            researcher.store_memory("auth_choice", "JWT")
            researcher.coordinate(coder, "use JWT, see memory key auth_choice")
            researcher.complete_task("survey auth options")

            coder.assign_task("implement JWT middleware")
            coder.complete_task("implement JWT middleware")
            researcher.handoff_to(tester, reason="QANeeded")

            tester.assign_task("test JWT middleware")
            tester.complete_task("test JWT middleware")

        # On exit: all sessions ended, all scrolls saved
    """

    def __init__(self, swarm_id: str = None, topology: str = "mesh",
                 db_path: str = None):
        self.swarm_id  = swarm_id or f"swarm-{uuid.uuid4().hex[:8]}"
        self.topology  = topology
        self._db_path  = db_path or os.environ.get("SWARM_DB", ".swarm/memory.db")
        self._flow     = VexelFlow(self.swarm_id, self._db_path)
        self._agents:  dict[str, SovereignAgent] = {}

    def spawn(self, agent_id: str = None, role: str = "coder") -> SovereignAgent:
        """Spawn a new agent with a vexel identity."""
        if role not in ROLES:
            raise ValueError(f"Unknown role '{role}'. Valid: {list(ROLES)}")
        aid    = agent_id or f"{role}-{uuid.uuid4().hex[:6]}"
        agent  = SovereignAgent(aid, role, self._flow)
        self._agents[aid] = agent
        return agent

    def status(self) -> dict:
        return self._flow.swarm_status()

    def agent(self, agent_id: str) -> Optional[SovereignAgent]:
        return self._agents.get(agent_id)

    def close(self):
        """End all active agent sessions."""
        for agent in list(self._agents.values()):
            if agent._active:
                try:
                    agent.end_session()
                except Exception:
                    pass
        self._flow.close()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()


# ── Demo ──────────────────────────────────────────────────────────────────────

def demo():
    """
    Simulate a complete claude-flow swarm with vexel identity tracking.
    Shows: spawn → work → coordinate → handoff → consensus → mixdown.
    """
    swarm_id = f"demo-{int(time.time())}"
    db_path  = f"/tmp/vexel_flow_demo_{swarm_id}.db"

    print(f"\n{'═'*60}")
    print(f"  SOVEREIGN SWARM DEMO")
    print(f"  swarm_id : {swarm_id}")
    print(f"  topology : hierarchical")
    print(f"{'═'*60}\n")

    with SwarmSession(swarm_id, topology="hierarchical",
                      db_path=db_path) as session:

        # ── Spawn agents ───────────────────────────────────────────────
        coordinator = session.spawn("coord-001", "coordinator")
        researcher  = session.spawn("res-001",   "researcher")
        coder       = session.spawn("cod-001",   "coder")
        tester      = session.spawn("test-001",  "tester")

        print("Agents spawned:")
        for a in [coordinator, researcher, coder, tester]:
            x, y = a.ulam()
            print(f"  {a.role:<14} id={a.agent_id}  "
                  f"root={a.root()}  ulam=({x},{y})")

        print()

        # ── Phase 1: Research ──────────────────────────────────────────
        print("── Phase 1: Research ──")
        coordinator.assign_task("coordinate auth system implementation")
        researcher.assign_task("survey JWT vs PASETO auth libraries")
        researcher.idle("awaiting search results")

        researcher.store_memory("auth_survey",
            "JWT: widely supported, RS256 recommended. PASETO: modern, "
            "type-safe, smaller ecosystem.")
        researcher.store_memory("auth_recommendation", "JWT with RS256")
        researcher.complete_task("survey JWT vs PASETO auth libraries")

        # Researcher coordinates with coder
        researcher.coordinate(coder,
            "recommendation: JWT RS256, see memory key auth_recommendation")
        print(f"  researcher root : {researcher.root()}")
        print(f"  coder root      : {coder.root()}")
        print()

        # ── Phase 2: Implementation ────────────────────────────────────
        print("── Phase 2: Implementation ──")
        coder.assign_task("implement JWT RS256 middleware")
        coder.store_memory("jwt_impl_status", "in_progress")

        # Consensus: everyone agrees on JWT
        researcher.propose_consensus("auth_approach_jwt")
        coder.accept_consensus("auth_approach_jwt")
        coordinator.accept_consensus("auth_approach_jwt")
        print(f"  consensus reached: auth_approach_jwt")

        coder.store_memory("jwt_impl_status", "complete")
        coder.complete_task("implement JWT RS256 middleware")
        print(f"  coder root      : {coder.root()}")
        print()

        # ── Phase 3: Handoff to tester ─────────────────────────────────
        print("── Phase 3: Handoff ──")
        lineage_root_before = coder.root()
        coder.handoff_to(tester, reason="QAReady")
        print(f"  coder dissolved, scroll saved")
        print(f"  tester inherits lineage from: {lineage_root_before}")

        # ── Phase 4: Testing ───────────────────────────────────────────
        print("\n── Phase 4: Testing ──")
        tester.assign_task("test JWT middleware — happy path")
        tester.complete_task("test JWT middleware — happy path")
        tester.assign_task("test JWT middleware — expiry edge case")
        tester.complete_task("test JWT middleware — expiry edge case")
        tester.store_memory("test_result", "all_pass")
        print(f"  tester root     : {tester.root()}")
        print()

        # ── Final status ───────────────────────────────────────────────
        print("── Swarm Status ──")
        st = session.status()
        print(f"  active agents   : {st['agents_active']}")
        print(f"  total events    : {st['total_events']}")
        print(f"  event breakdown : {st['event_breakdown']}")
        print()
        for a in st["agents"]:
            x, y = a["ulam"]
            print(f"  {a['role']:<14} root={a['root']}  "
                  f"events={a['events']}  ulam=({x},{y})")

    print(f"\n{'─'*60}")
    print(f"  Session complete. All scrolls saved to mixdowns/.")
    print(f"  Lineage is unbroken. The scroll travels with the intelligence.")
    print(f"{'─'*60}\n")


if __name__ == "__main__":
    demo()
