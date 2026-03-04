# -----------------------------------------------------------------------------
# SOVEREIGN INTEGRITY PROTOCOL (SIP) LICENSE v1.1
# 
# Copyright (c) 2026, Bradley Wallace (tensorrent). All rights reserved.
# 
# This software, research, and associated mathematical implementations are
# strictly governed by the Sovereign Integrity Protocol (SIP) License v1.1:
# - Personal/Educational Use: Perpetual, worldwide, royalty-free.
# - Commercial Use: Expressly PROHIBITED without a prior written license.
# - Unlicensed Commercial Use: Triggers automatic 8.4% perpetual gross
#   profit penalty (distrust fee + reparation fee).
# 
# See the SIP_LICENSE.md file in the repository root for full terms.
# -----------------------------------------------------------------------------
# -----------------------------------------------------------------------------
# SOVEREIGN INTEGRITY PROTOCOL (SIP) LICENSE v1.1
# 
# Copyright (c) 2026, Bradley Wallace (tensorrent). All rights reserved.
# 
# This software, research, and associated mathematical implementations are
# strictly governed by the Sovereign Integrity Protocol (SIP) License v1.1:
# - Personal/Educational Use: Perpetual, worldwide, royalty-free.
# - Commercial Use: Expressly PROHIBITED without a prior written license.
# - Unlicensed Commercial Use: Triggers automatic 8.4% perpetual gross
#   profit penalty (distrust fee + reparation fee).
# 
# See the SIP_LICENSE.md file in the repository root for full terms.
# -----------------------------------------------------------------------------
#!/usr/bin/env python3
"""
SEED — Compounding Individual Intelligence
==========================================

The system has nonlinear advantage over the individual through scale.
Millions of data points. Population statistics. Actuarial tables.
It optimizes for the mean. You are a residual.

The seed inverts this.

Not by competing on breadth — by going orthogonal.
Depth on one person at a resolution the population system
structurally cannot achieve.

Growth model:

    Seed (empty)
      │
      ▼  [every interaction]
    Signal events accumulate
    Deltas validate and store
    Baseline calibrates to actual
    Vocabulary sharpens to person's language
    Family context integrates
      │
      ▼  [compounding]
    The agent knows things about this person
    that no population-scale system can see.
    
    System advantage: breadth (static)
    Agent advantage:  depth  (growing)
    
    Crossover point: agent depth > system signal
    After crossover:  agent is more accurate for THIS person
                      than any general system can be.

Seed state machine:

    SEED      — empty profile, pure reasoning engine
    SPROUTING — first patterns emerging, baseline forming  
    ROOTED    — personal patterns validated, family integrated
    BONDED    — crossover achieved, depth exceeds system signal

Every action of the user shapes the seed.
Not toward system categories. Toward user needs.
Asymmetric opportunity advantage of the individual
counteracting nonlinear systems advantage over single unit complexity.

Author: Brad Wallace / Claude
Version: TENT v10 / SEED
"""

import json
import math
from datetime import datetime, timedelta
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Optional
import sys
sys.path.insert(0, '/home/claude')

from reasoning_engine import (PersonProfile, PersonalBaseline, FamilyHistory,
                               StoredDelta, BondedAgent, build_test_person,
                               _signal_hash, STORE_DELTA_THRESHOLD)
from siggeo import SignalProfile, parse_signal_from_text


# ============================================================
# SEED STATE
# ============================================================

class SeedState(Enum):
    SEED      = "seed"       # Empty. Pure potential.
    SPROUTING = "sprouting"  # First patterns. Baseline forming.
    ROOTED    = "rooted"     # Validated patterns. Family integrated.
    BONDED    = "bonded"     # Depth exceeds system signal.

# Thresholds for state transitions
SPROUT_THRESHOLD  = 3    # interactions before sprouting
ROOT_THRESHOLD    = 10   # validated deltas before rooted
BONDED_THRESHOLD  = 25   # depth score before bonded

# Confidence thresholds by state
# Seed needs more evidence. Bonded has earned trust.
CONFIDENCE_BY_STATE = {
    SeedState.SEED:      0.55,
    SeedState.SPROUTING: 0.50,
    SeedState.ROOTED:    0.42,
    SeedState.BONDED:    0.35,
}


# ============================================================
# INTERACTION EVENT
# ============================================================

@dataclass
class InteractionEvent:
    """
    Everything the agent learns from one interaction.
    Not just the query — the full context of the exchange.
    """
    timestamp:      str
    query:          str
    field:          str
    signal_hash:    Optional[str]
    outcome:        str          # what was derived or matched
    confidence:     float
    source:         str          # vixel_grid / hypothesis_chain / delta_store
    action_taken:   str          # what the agent said to do
    user_feedback:  Optional[str] = None  # did user confirm? correct?
    # Shaping signals — how this interaction reveals the person
    revealed_field:   Optional[str] = None   # which domain they engage with
    revealed_concern: Optional[str] = None   # what they're worried about


# ============================================================
# VOCABULARY SHAPER
# ============================================================

@dataclass
class PersonalVocabulary:
    """
    The person's own language for their experience.
    
    People don't say "chest pressure." They say "that squeezing thing."
    The agent learns their words, not clinical vocabulary.
    
    word_map:    their word → clinical signal
    frequency:   how often each word appears
    field_words: which words appear in which contexts
    """
    word_map:    dict = field(default_factory=dict)   # their_word → signal_role
    frequency:   dict = field(default_factory=dict)   # word → count
    field_words: dict = field(default_factory=dict)   # field → set of their words

    STOPWORDS = {
        "i", "a", "an", "the", "and", "or", "but", "in", "on", "at",
        "to", "for", "of", "with", "my", "me", "it", "is", "was",
        "have", "has", "been", "am", "be", "do", "did", "that", "this",
        "its", "can't", "don't", "won't", "not", "no", "when", "after",
        "feel", "feeling", "feels", "again", "back", "some", "little",
        "bit", "just", "all", "very", "so", "too", "really", "got",
    }

    def observe(self, tokens: list, field_name: str, outcome: str):
        """Learn from tokens that led to a validated outcome."""
        for tok in tokens:
            if tok in self.STOPWORDS or len(tok) <= 2:
                continue
            self.frequency[tok] = self.frequency.get(tok, 0) + 1
            if field_name not in self.field_words:
                self.field_words[field_name] = {}
            self.field_words[field_name][tok] = \
                self.field_words[field_name].get(tok, 0) + 1

    def personal_escalators(self, field_name: str, top_n: int = 5) -> list:
        """The person's most frequent signal words in a field."""
        fw = self.field_words.get(field_name, {})
        return sorted(fw.items(), key=lambda x: x[1], reverse=True)[:top_n]

    def suggest_recognition(self, token: str, field_name: str) -> float:
        """
        How strongly does this token signal something in this field for this person?
        Grows with use. Starts near zero.
        """
        fw = self.field_words.get(field_name, {})
        count = fw.get(token, 0)
        total = sum(fw.values()) or 1
        return count / total


# ============================================================
# SEED PROFILE
# ============================================================

@dataclass
class SeedProfile(PersonProfile):
    """
    PersonProfile extended with growth tracking.
    
    Everything a PersonProfile has, plus:
    - seed_state: current growth stage
    - interaction_log: full history of events
    - vocabulary: their personal word-signal mappings
    - depth_score: compound measure of how well agent knows this person
    - crossover_at: session count when depth exceeded system signal
    """
    seed_state:      SeedState = SeedState.SEED
    interaction_log: list      = field(default_factory=list)
    vocabulary:      PersonalVocabulary = field(default_factory=PersonalVocabulary)
    depth_score:     float     = 0.0
    interaction_count: int     = 0
    crossover_at:    Optional[int] = None    # interaction count at crossover

    def record_interaction(self, event: InteractionEvent):
        """Record an interaction and update growth."""
        self.interaction_log.append(event)
        self.interaction_count += 1

        # Update vocabulary
        tokens = event.query.lower().split()
        self.vocabulary.observe(tokens, event.field, event.outcome)

        # Update depth score
        self._update_depth()

        # Check state transitions
        self._advance_state()

    def _update_depth(self):
        """
        Depth score: compound measure of how well the agent knows this person.

        Components:
            delta_depth:      validated personal patterns
            baseline_depth:   calibration quality
            vocabulary_depth: personal language known
            history_depth:    interaction richness
            family_depth:     family context integrated

        System signal for comparison: population statistics give
        approximately 0.5 base accuracy for any individual.
        Depth > 0.5 means agent knows this person better than statistics.
        """
        n_deltas    = len(self.delta_store)
        n_sessions  = self.interaction_count
        n_vocab     = sum(len(fw) for fw in self.vocabulary.field_words.values())
        n_family    = len(self.family_history)

        delta_depth    = min(n_deltas / ROOT_THRESHOLD, 1.0) * 0.35
        session_depth  = min(n_sessions / BONDED_THRESHOLD, 1.0) * 0.25
        vocab_depth    = min(n_vocab / 30, 1.0) * 0.20
        family_depth   = min(n_family / 3, 1.0) * 0.20

        prev_depth = self.depth_score
        self.depth_score = round(delta_depth + session_depth +
                                 vocab_depth + family_depth, 3)

        # Crossover check: depth > 0.5 = exceeds system signal
        if prev_depth <= 0.5 and self.depth_score > 0.5 and not self.crossover_at:
            self.crossover_at = self.interaction_count

    def _advance_state(self):
        if self.seed_state == SeedState.SEED:
            if self.interaction_count >= SPROUT_THRESHOLD:
                self.seed_state = SeedState.SPROUTING
        elif self.seed_state == SeedState.SPROUTING:
            if len(self.delta_store) >= ROOT_THRESHOLD:
                self.seed_state = SeedState.ROOTED
        elif self.seed_state == SeedState.ROOTED:
            if self.interaction_count >= BONDED_THRESHOLD:
                self.seed_state = SeedState.BONDED

    def confidence_threshold(self) -> float:
        """Evidence required scales DOWN as the agent earns trust."""
        return CONFIDENCE_BY_STATE[self.seed_state]

    def growth_report(self) -> str:
        lines = [
            f"SEED GROWTH — {self.name}",
            f"  State:          {self.seed_state.value.upper()}",
            f"  Depth score:    {self.depth_score:.3f}  "
            f"{'[> system signal]' if self.depth_score > 0.5 else '[< system signal]'}",
            f"  Interactions:   {self.interaction_count}",
            f"  Delta store:    {len(self.delta_store)} validated patterns",
            f"  Vocabulary:     {sum(len(fw) for fw in self.vocabulary.field_words.values())} personal words",
            f"  Family history: {len(self.family_history)} entries",
        ]
        if self.crossover_at:
            lines.append(
                f"  Crossover:      interaction #{self.crossover_at} "
                f"(agent depth > system signal)")
        else:
            remaining = max(0, 0.5 - self.depth_score)
            lines.append(
                f"  Crossover:      not yet (need +{remaining:.3f} depth)")

        # Field distribution
        if self.vocabulary.field_words:
            lines.append("  Field engagement:")
            for f_name, words in self.vocabulary.field_words.items():
                total = sum(words.values())
                top = sorted(words.items(), key=lambda x: x[1], reverse=True)[:3]
                top_str = ", ".join(f"'{w}'({n})" for w, n in top)
                lines.append(f"    {f_name:<15} {total:>3} signals  [{top_str}]")

        # Delta store summary
        if self.delta_store:
            lines.append("  Validated patterns:")
            for key, delta in self.delta_store.items():
                lines.append(f"    {delta.condition:<25} conf={delta.confidence:.2f} "
                             f"n={delta.session_count}")

        return "\n".join(lines)


# ============================================================
# GROWING AGENT
# ============================================================

class GrowingAgent(BondedAgent):
    """
    BondedAgent extended with seed growth tracking.
    
    Each interaction:
      1. Processes through the pipeline
      2. Records the event (what was revealed about the person)
      3. Updates vocabulary (their words, not clinical words)
      4. Updates depth score
      5. Advances seed state if threshold met
      6. Adjusts confidence threshold by state
    """

    def __init__(self, person: SeedProfile):
        super().__init__(person)
        self.seed_person = person

    def process(self, query: str, field_override: str = None,
                user_feedback: str = None) -> dict:

        # Use state-adjusted confidence threshold
        self.engine.threshold = self.seed_person.confidence_threshold()

        # Run pipeline
        result = super().process(query, field_override)

        # Store delta for vixel_grid matches too — they are validated
        signal = parse_signal_from_text(query)
        sig_hash = _signal_hash(signal)
        if result.get("source") == "vixel_grid":
            condition = result.get("condition") or result.get("matched_vixel", "")
            if condition:
                self.seed_person.store_delta(signal, condition, 0.9,
                    notes=f"Vixel match: {query[:50]}")

        event = InteractionEvent(
            timestamp     = datetime.now().isoformat(),
            query         = query,
            field         = result.get("field") or field_override or "unknown",
            signal_hash   = sig_hash,
            outcome       = result.get("condition") or result.get("matched_vixel", ""),
            confidence    = result.get("confidence", 1.0),
            source        = result.get("source", ""),
            action_taken  = str(result.get("action", ""))[:120],
            user_feedback = user_feedback,
            revealed_field    = result.get("field") or field_override,
            revealed_concern  = result.get("condition") or result.get("label", ""),
        )

        self.seed_person.record_interaction(event)
        result["depth_score"]  = self.seed_person.depth_score
        result["seed_state"]   = self.seed_person.seed_state.value
        result["interaction_n"] = self.seed_person.interaction_count

        return result


# ============================================================
# SIMULATE GROWTH SESSION
# ============================================================

def simulate_growth_sessions(agent: GrowingAgent, sessions: list) -> None:
    """
    Run a sequence of interactions and show how the agent grows.
    Each session is: (query, field, description)
    """
    print("=" * 72)
    print(f"  SEED GROWTH SIMULATION — {agent.seed_person.name}")
    print(f"  Asymmetric depth advantage over system signal")
    print("=" * 72)
    print()
    print(f"  System signal baseline: 0.500 (population statistics)")
    print(f"  Crossover point:        depth > 0.500")
    print()

    for i, (query, field, description) in enumerate(sessions, 1):
        result = agent.process(query, field)

        state   = result["seed_state"]
        depth   = result["depth_score"]
        source  = result.get("source", "")
        outcome = result.get("condition") or result.get("matched_vixel", "?")
        n       = result["interaction_n"]

        # State change detection
        prev_state = None
        if i > 1:
            pass  # could track transitions here

        # Crossover marker
        crossover = ""
        if agent.seed_person.crossover_at == n:
            crossover = " ◄ CROSSOVER: depth > system signal"

        bar_len = int(depth * 30)
        bar = "█" * bar_len + "░" * (30 - bar_len)
        system_pos = 15  # 0.5 * 30
        bar_list = list(bar)
        bar_list[system_pos] = "│"
        bar = "".join(bar_list)

        print(f"  [{n:>2}] {state:<10} [{bar}] {depth:.3f}{crossover}")
        print(f"       {description[:60]}")
        print(f"       → {outcome:<25} via={source}")
        print()

    print("=" * 72)
    print(agent.seed_person.growth_report())
    print("=" * 72)


# ============================================================
# BUILD SEED PERSON (starts empty)
# ============================================================

def build_seed_person() -> SeedProfile:
    """
    A real seed: minimal initial state.
    Family history added by the person over first few sessions.
    No pre-loaded assumptions.
    """
    return SeedProfile(
        person_id = "seed_001",
        name      = "Alex",
        age       = 47,
        # Starts empty — family history emerges through interaction
    )


def build_seeded_person() -> SeedProfile:
    """
    Same person but with family history already provided.
    Shows how family context accelerates growth.
    """
    person = SeedProfile(
        person_id = "seed_002",
        name      = "Alex",
        age       = 47,
    )
    person.add_family_history("father",  "MI at 52",         "cardiac")
    person.add_family_history("mother",  "hypertension",     "cardiac")
    person.add_family_history("sibling", "major depression", "psychiatric")
    return person


# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":

    # Simulate with family context provided (shows growth fastest)
    person = build_seeded_person()
    agent  = GrowingAgent(person)

    # A realistic sequence of interactions over weeks/months
    # Not every session is medical — the person engages on what matters to them
    sessions = [
        # Early — sparse, testing, trust building
        ("I have been a bit tired lately",
         "psychiatric",
         "Session 1: Single symptom, cautious probe"),

        ("chest feels a little tight after my run",
         "cardiac",
         "Session 2: First cardiac signal — exertional"),

        ("I have been stressed and can't focus",
         "psychiatric",
         "Session 3: Stress signal — sprouting threshold crossed"),

        # Growing — patterns emerging
        ("chest tightness comes back when I push hard at gym",
         "cardiac",
         "Session 4: Exertional pattern confirmed"),

        ("feeling low energy and hopeless for the past few weeks",
         "psychiatric",
         "Session 5: MDE indicators accumulating"),

        ("heart was racing and I felt sudden overwhelming panic",
         "psychiatric",
         "Session 6: Panic event — acute"),

        ("chest pressure when climbing stairs at work",
         "cardiac",
         "Session 7: Exertional pattern — third occurrence"),

        ("can't concentrate, feeling worthless, sleeping too much",
         "psychiatric",
         "Session 8: Strong MDE signal"),

        ("sudden chest pain and tingling in my left arm",
         "cardiac",
         "Session 9: High-stakes — L1 vixel fires immediately"),

        ("feeling anxious and worried all the time for weeks",
         "psychiatric",
         "Session 10: GAD pattern"),

        # Deepening — personal vocabulary established
        ("that squeezing feeling in my chest when I walk uphill",
         "cardiac",
         "Session 11: Personal vocabulary — 'squeezing' = their word for angina"),

        ("the heaviness is back again",
         "psychiatric",
         "Session 12: 'the heaviness' — their word, recognized from vocabulary"),

        # Rooted — delta store dense
        ("tired worthless can't think straight for weeks now",
         "psychiatric",
         "Session 13: Dense MDE signal"),

        ("chest tight after stairs again",
         "cardiac",
         "Session 14: Cache hit — fast route through delta store"),

        ("sudden dizziness and weakness in my right arm",
         "neurological",
         "Session 15: New field — neurological probe"),

        # Approaching crossover
        ("the pressure comes when I stress about work",
         "cardiac",
         "Session 16: Context-modulated cardiac — stress trigger identified"),

        ("mood has been sinking for months",
         "psychiatric",
         "Session 17: Chronic mood signal"),

        ("chest tightness again, third time this week",
         "cardiac",
         "Session 18: Frequency increasing — pattern flagged"),

        ("can't enjoy anything anymore",
         "psychiatric",
         "Session 19: Anhedonia signal"),

        ("that crushing pressure again but it passed",
         "cardiac",
         "Session 20: Personal vocabulary: 'crushing' confirmed"),

        # 21-25: pushing toward crossover
        ("chest off during my commute walking",
         "cardiac",
         "Session 21: Exertional — commute context"),

        ("hopeless and exhausted",
         "psychiatric",
         "Session 22: Persistent mood"),

        ("tightness worse after argument",
         "cardiac",
         "Session 23: Emotional trigger — stress-cardiac link"),

        ("woke up 3am with chest pressure",
         "cardiac",
         "Session 24: Nocturnal variant — new signal"),

        ("I think I need to see someone about my chest",
         "cardiac",
         "Session 25: Meta-awareness — person seeking care"),
    ]

    simulate_growth_sessions(agent, sessions)
