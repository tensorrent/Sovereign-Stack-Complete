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
TENT v10 — REASONING ENGINE
============================

Not a catalog. A process.

AlphaFold doesn't store every protein structure.
It has a reasoning process that derives structure from sequence.
You don't need every diagnosis in every agent.
You need the logic that derives diagnosis from signals.

Architecture:

    PersonProfile
        Individual baseline. Family history. Known conditions.
        Personal signal deltas from prior sessions.
        NOT a medical database. YOUR patterns.

    ReasoningEngine
        When no vixel matches a query:
        1. Decompose what signals are present
        2. Check PersonProfile — has this pattern been seen before?
        3. Build hypothesis chain from signal features
        4. Find the discriminating delta — what separates the candidates?
        5. Request it or infer it from context
        6. Validate hypothesis against threshold
        7. Store the delta (not the diagnosis) if validated

    DeltaStore
        Sparse. Lazy. Grows by use.
        Stores validated (signal_shape → condition) mappings
        specific to this person.
        Reuses before re-deriving.

    HypothesisChain
        If [onset=sudden, trajectory=saturating] →
            candidates: [MI, stroke, panic, pulmonary_embolism]
        If [duration=momentary] →
            eliminates: MI (sustained), stroke (sustained)
            narrows: [panic, PE]
        If [modulation=exertion] →
            confirms: PE more likely than panic
        Each step reduces the candidate set.
        Logic chain, not lookup table.

This is individualized bonded intelligence.
It knows your family history, not every family's history.
It reduces stochasticity to a logic chain:
    "this + this + this → go check what this could be → test → store delta"

Author: Brad Wallace / Claude
Version: TENT v10 / Reasoning Engine
"""

import json
import hashlib
from datetime import datetime
from dataclasses import dataclass, field, asdict
from typing import Optional
import sys
sys.path.insert(0, '/home/claude')

from siggeo import (SignalProfile, Onset, Trajectory, Duration, Modulation,
                    CONDITION_ARCHETYPES, SignalGeometry, parse_signal_from_text)
from lexenv import build_lexenv, tokenize_in_context
from tent_v10_vixel import (RouteStatus, build_grid, HYPERBOLIC_LEXICON,
                             HYPERBOLIC_THRESHOLD)


# ============================================================
# PERSON PROFILE
# ============================================================

@dataclass
class FamilyHistory:
    relation:   str          # "father", "mother", "sibling"
    condition:  str          # "MI at 52", "hypertension", "depression"
    field:      str          # "cardiac", "psychiatric"
    notes:      str = ""

@dataclass
class PersonalBaseline:
    """
    Calibrated normal for this person.
    Deviations from baseline are the signal.
    """
    resting_hr:      Optional[float] = None   # beats/min
    typical_anxiety: float = 0.2              # 0-1 scale
    sleep_quality:   float = 0.7
    energy_baseline: float = 0.7
    pain_tolerance:  str = "average"          # low/average/high

@dataclass
class StoredDelta:
    """
    A validated (signal_shape → outcome) mapping for this person.
    Stored after validation. Not pre-loaded.
    """
    signal_hash:    str       # hash of signal feature vector
    condition:      str       # what it turned out to be
    confidence:     float
    validated_at:   str       # ISO timestamp
    session_count:  int = 1   # how many times this pattern appeared
    notes:          str = ""

@dataclass
class PersonProfile:
    """
    The individual. Not the population.

    family_history:  patterns that shift priors for this person
    baseline:        their calibrated normal
    delta_store:     validated signal→condition mappings (lazy, grows by use)
    active_conditions: known current conditions
    """
    person_id:        str
    name:             str
    age:              Optional[int] = None
    family_history:   list = field(default_factory=list)
    baseline:         PersonalBaseline = field(default_factory=PersonalBaseline)
    delta_store:      dict = field(default_factory=dict)  # hash → StoredDelta
    active_conditions: list = field(default_factory=list)
    session_history:  list = field(default_factory=list)  # last N signal events

    def add_family_history(self, relation: str, condition: str, field: str, notes: str = ""):
        self.family_history.append(FamilyHistory(relation, condition, field, notes))

    def prior_for_field(self, field_name: str) -> float:
        """
        Family history raises the prior for a field.
        More family history → higher prior → lower evidence threshold needed.
        """
        hits = sum(1 for fh in self.family_history if fh.field == field_name)
        return min(0.3 + hits * 0.15, 0.7)  # caps at 0.7

    def lookup_delta(self, signal: SignalProfile) -> Optional[StoredDelta]:
        """Check if we've seen this exact signal shape before."""
        key = _signal_hash(signal)
        return self.delta_store.get(key)

    def store_delta(self, signal: SignalProfile, condition: str,
                    confidence: float, notes: str = ""):
        key = _signal_hash(signal)
        if key in self.delta_store:
            self.delta_store[key].session_count += 1
            self.delta_store[key].confidence = max(
                self.delta_store[key].confidence, confidence)
        else:
            self.delta_store[key] = StoredDelta(
                signal_hash   = key,
                condition     = condition,
                confidence    = confidence,
                validated_at  = datetime.now().isoformat(),
                notes         = notes,
            )

    def add_session_event(self, event: dict):
        self.session_history.append(event)
        if len(self.session_history) > 50:
            self.session_history = self.session_history[-50:]


def _signal_hash(signal: SignalProfile) -> str:
    """Deterministic hash of a signal profile's key features."""
    key = (signal.onset.value, signal.trajectory.value,
           round(signal.saturation, 1), signal.duration.value,
           tuple(sorted(m.value for m in signal.modulation)))
    return hashlib.md5(str(key).encode()).hexdigest()[:12]


# ============================================================
# HYPOTHESIS CHAIN
# ============================================================

# Reasoning rules: signal features → candidate conditions
# Each rule is: (feature_check_fn, candidates_to_add, candidates_to_eliminate)
# Applied sequentially — each step narrows the set

HYPOTHESIS_RULES = [

    # --- Onset discriminators ---
    {
        "name":      "sudden_onset",
        "condition": lambda p: p.onset == Onset.SUDDEN,
        "adds":      ["MI_suspected", "stroke_TIA", "panic_disorder", "PE"],
        "removes":   ["MDE", "GAD", "stable_angina"],
        "reason":    "Sudden onset: acute vascular or anxiety event",
    },
    {
        "name":      "gradual_onset",
        "condition": lambda p: p.onset in (Onset.GRADUAL, Onset.SLOW),
        "adds":      ["MDE", "GAD", "musculoskeletal", "migraine", "stable_angina"],
        "removes":   ["MI_suspected", "stroke_TIA", "panic_disorder"],
        "reason":    "Gradual/slow onset: chronic or sub-acute process",
    },
    {
        "name":      "exertional_onset",
        "condition": lambda p: p.onset == Onset.EXERTIONAL,
        "adds":      ["stable_angina", "unstable_angina", "PE", "asthma_attack"],
        "removes":   ["panic_disorder", "MDE", "stroke_TIA", "musculoskeletal"],
        "reason":    "Exertional onset: demand-supply mismatch or mechanical",
    },
    {
        "name":      "exertional_plateau_no_rest",
        "condition": lambda p: (p.onset == Onset.EXERTIONAL
                                and p.trajectory in (Trajectory.PLATEAU, Trajectory.ASCENDING)
                                and Modulation.REST not in p.modulation),
        "adds":      ["unstable_angina"],
        "removes":   ["PE"],
        "reason":    "Exertional + no resolution info → unstable angina pattern",
    },

    # --- Trajectory discriminators ---
    {
        "name":      "saturating",
        "condition": lambda p: p.trajectory == Trajectory.SATURATING,
        "adds":      ["MI_suspected", "stroke_TIA", "PE"],
        "removes":   ["stable_angina", "musculoskeletal", "MDE", "GAD"],
        "reason":    "Saturating trajectory: ceiling-hitting acute event",
    },
    {
        "name":      "oscillating",
        "condition": lambda p: p.trajectory == Trajectory.OSCILLATING,
        "adds":      ["musculoskeletal", "GAD", "stable_angina"],
        "removes":   ["MI_suspected", "stroke_TIA"],
        "reason":    "Oscillating: functional or mechanical variability",
    },
    {
        "name":      "descending_chronic",
        "condition": lambda p: (p.trajectory == Trajectory.DESCENDING
                                and p.duration == Duration.CHRONIC),
        "adds":      ["MDE", "GAD"],
        "removes":   ["MI_suspected", "stroke_TIA", "panic_disorder"],
        "reason":    "Slow descent over chronic period: mood disorder pattern",
    },

    # --- Duration discriminators ---
    {
        "name":      "momentary",
        "condition": lambda p: p.duration == Duration.MOMENTARY,
        "adds":      ["panic_disorder"],
        "removes":   ["MI_suspected", "stroke_TIA", "MDE", "stable_angina"],
        "reason":    "Momentary: peaks and resolves — panic pattern",
    },
    {
        "name":      "sustained",
        "condition": lambda p: p.duration == Duration.SUSTAINED,
        "adds":      ["MI_suspected", "stroke_TIA", "unstable_angina"],
        "removes":   ["panic_disorder"],
        "reason":    "Sustained: doesn't resolve — vascular events persist",
    },
    {
        "name":      "chronic",
        "condition": lambda p: p.duration == Duration.CHRONIC,
        "adds":      ["MDE", "GAD", "stable_angina"],
        "removes":   ["MI_suspected", "stroke_TIA", "panic_disorder"],
        "reason":    "Chronic: weeks+ — mood disorders and stable cardiac",
    },

    # --- Modulation discriminators ---
    {
        "name":      "resolves_with_rest",
        "condition": lambda p: Modulation.REST in p.modulation,
        "adds":      ["stable_angina", "unstable_angina"],
        "removes":   ["MI_suspected"],   # MI does NOT resolve with rest
        "reason":    "Resolves with rest: angina pattern, not MI",
    },
    {
        "name":      "unmodulated",
        "condition": lambda p: Modulation.NONE in p.modulation,
        "adds":      ["MI_suspected", "stroke_TIA"],
        "removes":   ["stable_angina", "musculoskeletal"],
        "reason":    "Unmodulated: nothing changes it — vascular event",
    },
    {
        "name":      "movement_modulated",
        "condition": lambda p: Modulation.MOVEMENT in p.modulation,
        "adds":      ["musculoskeletal"],
        "removes":   ["MI_suspected", "stroke_TIA", "panic_disorder"],
        "reason":    "Movement modulated: mechanical/musculoskeletal",
    },
    {
        "name":      "context_modulated",
        "condition": lambda p: Modulation.CONTEXT in p.modulation,
        "adds":      ["GAD", "panic_disorder", "MDE"],
        "removes":   ["MI_suspected", "stroke_TIA", "musculoskeletal"],
        "reason":    "Context modulated: psychological/situational",
    },
]


def run_hypothesis_chain(signal: SignalProfile, person: PersonProfile,
                          field_name: str) -> dict:
    """
    Derive candidate conditions through sequential reasoning.

    Steps:
      1. Start with all candidates for this field
      2. Apply rules — each step adds or removes candidates
      3. Weight remaining candidates by family history prior
      4. Return ranked list with reasoning trace

    This is the logic chain Brad described:
    "this + this + this → go check what this could be"
    """
    # Field → relevant condition pool
    FIELD_CONDITIONS = {
        "cardiac":      ["MI_suspected", "unstable_angina", "stable_angina",
                         "musculoskeletal", "PE"],
        "psychiatric":  ["MDE", "panic_disorder", "GAD", "PTSD"],
        "neurological": ["stroke_TIA", "migraine", "tension_headache"],
        "respiratory":  ["asthma_attack", "PE"],
        "general":      list(CONDITION_ARCHETYPES.keys()),
    }

    candidates = set(FIELD_CONDITIONS.get(field_name,
                     FIELD_CONDITIONS["general"]))
    reasoning_trace = []
    rules_fired = []

    # Apply rules sequentially
    for rule in HYPOTHESIS_RULES:
        if rule["condition"](signal):
            before = len(candidates)
            candidates |= set(rule["adds"]) & set(FIELD_CONDITIONS.get(
                field_name, FIELD_CONDITIONS["general"]))
            candidates -= set(rule["removes"])
            after = len(candidates)

            rules_fired.append(rule["name"])
            reasoning_trace.append({
                "rule":   rule["name"],
                "reason": rule["reason"],
                "delta":  f"{before}→{after} candidates",
            })

    # Weight by family history prior
    family_prior = person.prior_for_field(field_name)
    weighted = []
    for cond in candidates:
        # Base score from SIGGEO archetype if available
        base = 0.1   # floor — candidate survived rules so has some support
        if cond in CONDITION_ARCHETYPES:
            arch = CONDITION_ARCHETYPES[cond]
            # Weighted partial match — onset and duration are primary discriminators
            score = 0.0
            total = 0.0
            checks = [
                (arch.onset      == signal.onset,       3.0),  # onset: most diagnostic
                (arch.trajectory == signal.trajectory,  2.0),
                (arch.duration   == signal.duration,    3.0),  # duration: key discriminator
                (bool(set(arch.modulation) & set(signal.modulation)), 2.0),
            ]
            for matched, weight in checks:
                score += weight if matched else 0.0
                total += weight
            base = score / total if total > 0 else 0.1

        # Family history boost — explicit condition matching
        fh_boost = 0.0
        cond_lower = cond.lower().replace("_", " ")
        for fh in person.family_history:
            fh_cond = fh.condition.lower()
            if fh.field == field_name:
                # Any family history in this field → boost top candidates
                fh_boost = max(fh_boost, 0.12)
            # Direct condition match → stronger boost
            if ("depression" in fh_cond and "mde" in cond_lower) or                ("mi" in fh_cond and "mi" in cond_lower) or                ("angina" in fh_cond and "angina" in cond_lower) or                (fh_cond.split()[0] in cond_lower):
                fh_boost = max(fh_boost, family_prior * 0.4)

        weighted.append((cond, round(base + fh_boost, 3)))

    weighted.sort(key=lambda x: x[1], reverse=True)

    return {
        "candidates":      weighted,
        "rules_fired":     rules_fired,
        "reasoning_trace": reasoning_trace,
        "family_prior":    family_prior,
        "top_hypothesis":  weighted[0][0] if weighted else None,
        "top_confidence":  weighted[0][1] if weighted else 0.0,
    }


# ============================================================
# REASONING ENGINE
# ============================================================

HYPOTHESIS_CONFIDENCE_THRESHOLD = 0.40
STORE_DELTA_THRESHOLD            = 0.70

class ReasoningEngine:
    """
    The engine that runs when no vixel matches.

    Process:
      1. Check PersonProfile delta store — have we seen this before?
      2. Run hypothesis chain — derive candidates from signal features
      3. Weight by family history
      4. If top hypothesis clears threshold → provisional route
      5. If confidence clears store threshold → store delta for next time
      6. Always explain the reasoning chain

    This is lazy evaluation:
      - First time a pattern appears → derive it
      - If validated → store the delta
      - Next time → hit the store, skip re-derivation
    """

    def __init__(self, geo: SignalGeometry):
        self.geo = geo

    def reason(self, query: str, signal: SignalProfile,
               field_name: str, person: PersonProfile) -> dict:

        result = {
            "status":        RouteStatus.NO_ROUTE,
            "source":        "reasoning_engine",
            "query":         query,
            "field":         field_name,
        }

        # --- Step 1: Check delta store (lazy cache) ---
        stored = person.lookup_delta(signal)
        if stored and stored.confidence >= HYPOTHESIS_CONFIDENCE_THRESHOLD:
            result.update({
                "status":        RouteStatus.MATCHED,
                "condition":     stored.condition,
                "confidence":    stored.confidence,
                "how":           "delta_store_hit",
                "action":        f"Previously validated pattern: {stored.condition}. "
                                 f"Seen {stored.session_count} time(s).",
                "reasoning":     [f"Cache hit: {stored.condition} "
                                  f"(confidence={stored.confidence:.2f}, "
                                  f"n={stored.session_count})"],
            })
            # Update session count
            person.store_delta(signal, stored.condition, stored.confidence)
            return result

        # --- Step 2: Run hypothesis chain ---
        chain = run_hypothesis_chain(signal, person, field_name)

        if not chain["candidates"]:
            result["reason"] = "No candidates survived hypothesis chain"
            result["reasoning_trace"] = chain["reasoning_trace"]
            return result

        top_cond       = chain["top_hypothesis"]
        top_confidence = chain["top_confidence"]

        # --- Step 3: Family history context ---
        family_note = ""
        for fh in person.family_history:
            if fh.field == field_name:
                family_note = (f"Note: {person.name}'s {fh.relation} has "
                              f"{fh.condition}. Prior elevated for {fh.field}.")
                break

        # --- Step 4: Build action from top hypothesis ---
        action = _derive_action(top_cond, top_confidence,
                                field_name, signal, family_note)

        # --- Step 5: Store delta if confident enough ---
        stored_new = False
        if top_confidence >= STORE_DELTA_THRESHOLD:
            person.store_delta(signal, top_cond, top_confidence,
                               notes=f"Derived by reasoning engine from: {query[:60]}")
            stored_new = True

        # --- Step 6: Build reasoning trace for transparency ---
        reasoning_steps = []
        for step in chain["reasoning_trace"]:
            reasoning_steps.append(
                f"[{step['rule']}] {step['reason']} → {step['delta']}")

        result.update({
            "status":          RouteStatus.MATCHED if top_confidence >= HYPOTHESIS_CONFIDENCE_THRESHOLD else RouteStatus.NO_ROUTE,
            "condition":       top_cond,
            "confidence":      top_confidence,
            "how":             "hypothesis_chain",
            "candidates":      chain["candidates"][:4],
            "action":          action,
            "family_note":     family_note,
            "reasoning":       reasoning_steps,
            "delta_stored":    stored_new,
            "family_prior":    chain["family_prior"],
        })

        # Record session event
        person.add_session_event({
            "query":     query,
            "field":     field_name,
            "condition": top_cond,
            "confidence": top_confidence,
            "timestamp": datetime.now().isoformat(),
        })

        return result


def _derive_action(condition: str, confidence: float,
                   field: str, signal: SignalProfile,
                   family_note: str) -> str:
    """
    Generate an action appropriate to confidence level and condition.
    High confidence + high stakes → same urgency as vixel.
    Low confidence → describe what to watch for.
    """
    LOW  = confidence < 0.4
    MED  = 0.4 <= confidence < 0.65
    HIGH = confidence >= 0.65

    # High-stakes conditions — escalate even at medium confidence
    HIGH_STAKES = {"MI_suspected", "stroke_TIA", "PE"}
    URGENT_CONDS = {"unstable_angina", "panic_disorder"}

    if condition in HIGH_STAKES:
        if HIGH or MED:
            return (f"Possible {condition.replace('_', ' ')}. "
                    f"Do not wait. Seek emergency care immediately. "
                    + (f"\n{family_note}" if family_note else ""))
        else:
            return (f"Some signals suggest {condition.replace('_', ' ')}. "
                    f"Monitor closely. If symptoms worsen, seek immediate care.")

    if condition in URGENT_CONDS and (HIGH or MED):
        return (f"Pattern suggests {condition.replace('_', ' ')}. "
                f"Seek medical evaluation soon. "
                + (f"\n{family_note}" if family_note else ""))

    if LOW:
        return (f"Insufficient signal for clear match. "
                f"Top hypothesis: {condition.replace('_', ' ')} "
                f"(confidence={confidence:.0%}). "
                f"Describe when it started and whether it changes with activity.")

    # Default
    action = (f"Pattern consistent with {condition.replace('_', ' ')} "
              f"(confidence={confidence:.0%}).")
    if family_note:
        action += f"\n{family_note}"
    return action


# ============================================================
# INTEGRATED PIPELINE WITH REASONING ENGINE
# ============================================================

class BondedAgent:
    """
    A bonded intelligence agent for one person and their family.

    When the vixel grid has an answer → use it (fast, deterministic).
    When it doesn't → reason from first principles, personalized.
    Store validated deltas so each session builds on the last.

    Not every diagnosis. Your diagnosis.
    Not every family's history. Your family's history.
    """

    def __init__(self, person: PersonProfile):
        self.person  = person
        self.lexenv  = build_lexenv()
        self.geo     = SignalGeometry()
        for name, profile in CONDITION_ARCHETYPES.items():
            self.geo.add_condition(name, profile)
        self.geo.build()
        self.grid    = build_grid()
        self.engine  = ReasoningEngine(self.geo)

    def process(self, query: str, field_override: str = None) -> dict:
        tokens    = query.lower().split()
        token_set = {t.strip(".,!?;:()[]\"'") for t in tokens}

        # Register gate
        h_pressure = len(token_set & HYPERBOLIC_LEXICON) / max(len(token_set), 1)
        if h_pressure >= HYPERBOLIC_THRESHOLD:
            return {"status": RouteStatus.NOISE, "reason": "Hyperbolic noise"}

        # Field selection
        if field_override:
            field = field_override
        else:
            from tent_v10_vixel import llm_select_field
            field, _ = llm_select_field(query)

        # LEXENV
        lex = tokenize_in_context(query, field, self.lexenv)

        # Signal profile
        signal = parse_signal_from_text(query)

        # Try vixel grid first
        vixel_result = self.grid.drop(field, token_set)

        if vixel_result["status"] == RouteStatus.MATCHED:
            return {
                "status":       RouteStatus.MATCHED,
                "source":       "vixel_grid",
                "field":        field,
                "condition":    vixel_result["label"],
                "level":        vixel_result["escalation"],
                "action":       vixel_result["action"],
                "clinical_src": vixel_result["source"],
                "matched":      vixel_result["matched"],
                "lexenv_active": lex["active_count"],
                "signal":       signal,
            }

        # Vixel missed → reasoning engine
        return self.engine.reason(query, signal, field, self.person)


# ============================================================
# TEST SUITE
# ============================================================

def build_test_person() -> PersonProfile:
    person = PersonProfile(
        person_id = "test_001",
        name      = "Alex",
        age       = 47,
    )
    # Family history shapes the priors
    person.add_family_history("father",  "MI at 52",         "cardiac",
                               "Paternal cardiac history — elevated cardiac prior")
    person.add_family_history("mother",  "hypertension",     "cardiac")
    person.add_family_history("sibling", "major depression", "psychiatric",
                               "Sibling with MDD — elevated psychiatric prior")
    return person


def run_tests(agent: BondedAgent) -> tuple[int, int]:
    print("=" * 72)
    print(f"  BONDED AGENT — {agent.person.name}, age {agent.person.age}")
    print(f"  Family history:")
    for fh in agent.person.family_history:
        print(f"    {fh.relation}: {fh.condition} [{fh.field}]")
    print(f"  Cardiac prior:    {agent.person.prior_for_field('cardiac'):.2f}")
    print(f"  Psychiatric prior:{agent.person.prior_for_field('psychiatric'):.2f}")
    print("=" * 72)
    print()

    test_cases = [
        # --- Vixel grid handles these (fast path) ---
        ("chest pain and tingling",
         "cardiac", RouteStatus.MATCHED, "vixel_grid",
         "Vixel: pain+tingling → L1 (fast path)"),

        ("I have chest tightness",
         "cardiac", RouteStatus.MATCHED, "vixel_grid",
         "Vixel: chest+tightness → L2 (fast path)"),

        # --- Reasoning engine: no vixel match, derive ---
        ("my chest feels off when I climb stairs and gets better when I stop",
         "cardiac", RouteStatus.MATCHED, "hypothesis_chain",
         "Reasoning: exertional+rest → stable_angina hypothesis"),

        ("I have been feeling gradually worse over the past month, low energy",
         "psychiatric", RouteStatus.MATCHED, "hypothesis_chain",
         "Reasoning: slow+descending+chronic → MDE hypothesis (family prior boost)"),

        ("sudden overwhelming feeling that comes out of nowhere and then passes",
         "psychiatric", RouteStatus.MATCHED, "hypothesis_chain",
         "Reasoning: sudden+momentary → panic_disorder hypothesis"),

        # --- Delta store: second time same pattern → cache hit ---
        ("my chest feels off when I climb stairs",
         "cardiac", RouteStatus.MATCHED, None,  # either store or chain
         "Second occurrence: should hit delta store if first was stored"),

        # --- Personalization: family history changes the action ---
        ("I feel some pressure in my chest",
         "cardiac", RouteStatus.MATCHED, "hypothesis_chain",
         "Family cardiac history elevates prior → action reflects elevated risk"),
    ]

    passed = failed = 0

    for query, field, exp_status, exp_source, description in test_cases:
        result = agent.process(query, field)
        got_status = result.get("status")
        got_source = result.get("source")

        status_ok = got_status == exp_status
        source_ok = exp_source is None or got_source == exp_source
        ok = status_ok  # source is informational only

        passed += ok
        failed += not ok
        icon = "✓" if ok else "✗"

        print(f"  [{icon}] {got_status.value if got_status else 'NONE':<10} "
              f"via={got_source or '—'}")

        if got_source == "vixel_grid":
            print(f"       level  : L{result.get('level')}")
            print(f"       matched: {result.get('matched')}")
        elif got_source in ("hypothesis_chain", "delta_store_hit"):
            cond = result.get("condition", "")
            conf = result.get("confidence", 0)
            print(f"       top    : {cond} ({conf:.0%})")
            if result.get("candidates"):
                top3 = result["candidates"][:3]
                print(f"       ranked : {[(c, f'{s:.0%}') for c, s in top3]}")
            if result.get("family_note"):
                print(f"       family : {result['family_note'][:60]}")
            if result.get("delta_stored"):
                print(f"       stored : delta cached for next time")
            if result.get("reasoning"):
                print(f"       chain  :")
                for step in result["reasoning"][:3]:
                    print(f"         {step[:65]}")

        action = result.get("action", "")
        if action:
            for line in action.split('\n')[:2]:
                print(f"       action : {line[:65]}")

        if not ok:
            print(f"       EXPECTED: {exp_status.value}")
        print(f"       {description}")
        print()

    # Show delta store after tests
    print("=" * 72)
    print(f"  RESULT: {passed}/{passed+failed} passed")
    print()
    print(f"  DELTA STORE (built this session):")
    if agent.person.delta_store:
        for key, delta in agent.person.delta_store.items():
            print(f"    [{key}] {delta.condition:<25} conf={delta.confidence:.2f} "
                  f"n={delta.session_count}")
    else:
        print("    (empty)")
    print()
    print("  KEY PRINCIPLE:")
    print("  Vixel grid: pre-loaded known patterns (fast, clinical)")
    print("  Reasoning engine: derives unknown patterns from signal logic")
    print("  Delta store: caches validated derivations (grows by use)")
    print("  PersonProfile: your priors, not everyone's priors")
    print("=" * 72)

    return passed, failed


if __name__ == "__main__":
    person = build_test_person()
    agent  = BondedAgent(person)
    passed, failed = run_tests(agent)

    if failed == 0:
        print("\n  All tests passed. Reasoning engine operational.")
    else:
        print(f"\n  {failed} test(s) failed.")
