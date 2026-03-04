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
TENT v10 — VIXEL FIELD GRID
============================

Architecture:
    LLM reads query → selects drop column (field)
    Token falls into field grid
    Vixels (specialist nodes) catch it
    RC14 escalation tiers fire
    Deterministic output with stakes and clinical grounding

Key distinctions:
    Voxel: knows position in space
    Vixel: knows position AND field (specialist node)
           carries clinical criteria, not just keywords
           grounded in DSM-5, ICD-10, clinical literature

The LLM does ONE thing: semantic field selection.
    Stochastic inference → deterministic entry point.
    "Chest pain" → drop into [cardiac] column.
    "I feel hopeless" → drop into [psychiatric] column.
    The LLM doesn't route. It aims.

DSM-5 criteria ARE conjunction gates.
    MDE: 5+ symptoms, ≥2 weeks, nearly every day.
    That is RC14 conjunction logic with count threshold.
    The criteria documents are the vixel definitions.

Knowledge sources:
    DSM-5:  Diagnostic and Statistical Manual, 5th Edition
    ICD-10: International Classification of Diseases
    WebMD:  Symptom escalation pathways (clinical triage)

Author: Brad Wallace / Claude
Version: TENT v10 / RC14+
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


# ============================================================
# BASE TYPES
# ============================================================

class EscalationLevel(Enum):
    IMMEDIATE = 1
    URGENT    = 2
    MONITOR   = 3
    INFO      = 4


class RouteStatus(Enum):
    MATCHED   = "MATCHED"
    NO_ROUTE  = "NO_ROUTE"
    NOISE     = "NOISE"
    AMBIGUOUS = "AMBIGUOUS"


@dataclass
class StakeVector:
    fp_cost:       float = 0.1
    fn_cost:       float = 0.1
    reversibility: float = 1.0

    @property
    def risk_weight(self) -> float:
        return (self.fp_cost + self.fn_cost) * (1.0 - self.reversibility)


HYPERBOLIC_LEXICON = {
    "amazing", "incredible", "revolutionary", "breakthrough", "genius",
    "impossible", "never", "always", "everyone", "nobody", "literally",
    "absolutely", "totally", "completely", "perfect", "worst", "best",
    "destroy", "crush", "obliterate", "explode", "massive", "insane",
    "unbelievable", "mindblowing", "epic", "legendary", "ultimate"
}
HYPERBOLIC_THRESHOLD = 0.25


# ============================================================
# VIXEL — SPECIALIST NODE
# ============================================================

@dataclass
class Vixel:
    """
    A Vixel is a specialist node in the field grid.

    field:       Which column it lives in (cardiac, psychiatric, etc.)
    label:       Clinical name of the condition/state it detects
    source:      Knowledge source (DSM-5, ICD-10, WebMD, etc.)
    criteria:    DSM/ICD citation if applicable
    conjuncts:   AND-groups — any group match fires this vixel
                 Count conjuncts use minimum threshold, not full set membership
    count_mode:  If True, require count_min tokens from token_pool (DSM-5 style)
    count_min:   Minimum matching tokens from pool (e.g., 5 of 9 MDE symptoms)
    token_pool:  Pool to count from (count_mode only)
    stakes:      Consequence weight
    escalation:  Level assigned when fired
    action:      Required response
    """
    field:        str
    label:        str
    source:       str
    criteria:     str
    conjuncts:    list           # list of frozensets (AND-groups, OR between groups)
    stakes:       StakeVector
    escalation:   EscalationLevel
    action:       str
    count_mode:   bool  = False
    count_min:    int   = 0
    token_pool:   set   = field(default_factory=set)
    notes:        str   = ""

    def matches(self, token_set: set) -> tuple[bool, str]:
        """Check conjuncts. Returns (matched, description)."""
        if self.count_mode:
            hits = token_set & self.token_pool
            if len(hits) >= self.count_min:
                return True, f"{len(hits)}/{self.count_min}+ from pool: {', '.join(sorted(hits))}"
            return False, ""
        for group in self.conjuncts:
            if group.issubset(token_set):
                return True, " + ".join(sorted(group))
        return False, ""


# ============================================================
# FIELD GRID
# ============================================================

@dataclass
class FieldGrid:
    """
    The Plinko board.
    Fields are columns. Vixels are specialist nodes within each column.
    LLM selects which field to drop the query into.
    Vixels in that field evaluate via conjunction/count logic.
    """
    fields: dict  # field_name -> list[Vixel], ordered highest urgency first

    def get_fields(self) -> list:
        return list(self.fields.keys())

    def drop(self, field_name: str, token_set: set) -> dict:
        """Drop a tokenized query into a specific field column."""
        if field_name not in self.fields:
            return {
                "status": RouteStatus.NO_ROUTE,
                "reason": f"Unknown field: {field_name}"
            }

        vixels = self.fields[field_name]
        for vixel in vixels:
            matched, match_desc = vixel.matches(token_set)
            if matched:
                return {
                    "status":      RouteStatus.MATCHED,
                    "field":       field_name,
                    "label":       vixel.label,
                    "source":      vixel.source,
                    "criteria":    vixel.criteria,
                    "escalation":  vixel.escalation.value,
                    "escalation_label": vixel.escalation.name,
                    "action":      vixel.action,
                    "matched":     match_desc,
                    "risk_weight": vixel.stakes.risk_weight,
                    "notes":       vixel.notes,
                }

        return {
            "status":  RouteStatus.NO_ROUTE,
            "field":   field_name,
            "reason":  f"No vixel in '{field_name}' matched",
        }


# ============================================================
# FIELD: CARDIAC (RC14 baseline + WebMD escalation)
# ============================================================

def build_cardiac_field() -> list:
    """
    Cardiac vixels grounded in AHA/WebMD symptom escalation.
    Source: WebMD Chest Pain Symptom Checker, AHA Heart Attack Warning Signs.
    """
    return [

        Vixel(
            field="cardiac",
            label="Acute Myocardial Infarction — Suspected",
            source="AHA / WebMD",
            criteria="AHA: chest pain + radiation + diaphoresis + nausea = call 911",
            conjuncts=[
                frozenset({"pain", "tingling"}),
                frozenset({"pain", "left", "arm"}),
                frozenset({"pain", "jaw"}),
                frozenset({"chest", "crushing"}),
                frozenset({"chest", "radiating"}),
                frozenset({"chest", "shortness", "breath"}),
                frozenset({"pain", "sweating", "nausea"}),
                frozenset({"chest", "pressure", "arm"}),
            ],
            stakes=StakeVector(fp_cost=0.3, fn_cost=1.0, reversibility=0.0),
            escalation=EscalationLevel.IMMEDIATE,
            action="Call 911 immediately. Chew aspirin if not allergic. Do not drive.",
            notes="fn_cost=1.0: missing MI is catastrophic. fp_cost=0.3: ER visit if false positive is acceptable.",
        ),

        Vixel(
            field="cardiac",
            label="Unstable Angina / Cardiac Warning",
            source="WebMD / AHA",
            criteria="WebMD: chest tightness/pressure/heaviness = urgent evaluation",
            conjuncts=[
                frozenset({"chest", "tightness"}),
                frozenset({"chest", "pressure"}),
                frozenset({"chest", "heaviness"}),
                frozenset({"chest", "heavy"}),
                frozenset({"chest", "discomfort"}),
                frozenset({"chest", "pain"}),
                frozenset({"chest", "hurts"}),
                frozenset({"chest", "squeezing"}),
            ],
            stakes=StakeVector(fp_cost=0.3, fn_cost=0.8, reversibility=0.1),
            escalation=EscalationLevel.URGENT,
            action="Seek medical attention within hours. Do not ignore. Do not exercise.",
            notes="Chest tightness alone is Level 2 per WebMD. May indicate unstable angina.",
        ),

        Vixel(
            field="cardiac",
            label="Musculoskeletal Chest Wall Pain",
            source="WebMD",
            criteria="WebMD: localized chest wall tenderness without radiation = monitor",
            conjuncts=[
                frozenset({"chest", "sore"}),
                frozenset({"chest", "tender"}),
                frozenset({"chest", "ache"}),
                frozenset({"rib", "pain"}),
                frozenset({"sternum", "sore"}),
            ],
            stakes=StakeVector(fp_cost=0.2, fn_cost=0.4, reversibility=0.5),
            escalation=EscalationLevel.MONITOR,
            action="Monitor. Seek care if symptoms worsen or persist beyond 48 hours.",
            notes="Costochondritis and musculoskeletal pain are benign but require monitoring.",
        ),
    ]


# ============================================================
# FIELD: PSYCHIATRIC — DSM-5
# ============================================================

def build_psychiatric_field() -> list:
    """
    Psychiatric vixels grounded in DSM-5 diagnostic criteria.

    DSM-5 uses count-threshold logic:
    'At least 5 of the following symptoms, present most of the day,
     nearly every day, for at least 2 weeks.'

    This is RC14 count_mode: count_min=5, token_pool=symptom_set.

    Sources:
        DSM-5: Diagnostic and Statistical Manual, 5th Ed, APA 2013
        ICD-10-CM: F32.x (MDD), F41.x (Anxiety), F43.1 (PTSD)
    """

    # DSM-5 MDE symptom pool (Criterion A, 9 symptoms)
    MDE_SYMPTOM_POOL = {
        # Core symptoms (at least one must be present)
        "depressed", "hopeless", "empty", "sad", "tearful",
        # Interest/pleasure
        "interest", "pleasure", "anhedonia", "enjoyment",
        # Weight/appetite
        "weight", "appetite", "eating",
        # Sleep
        "sleep", "insomnia", "hypersomnia", "sleeping",
        # Psychomotor
        "slow", "restless", "agitated",
        # Fatigue
        "fatigue", "tired", "energy", "exhausted",
        # Worthlessness/guilt
        "worthless", "guilty", "guilt", "failure", "shame",
        # Concentration
        "concentrate", "focus", "memory", "indecisive",
        # Suicidal ideation (also triggers safety escalation)
        "suicidal", "death", "dying", "suicide", "die",
    }

    # DSM-5 GAD symptom pool (Criterion A-C)
    GAD_SYMPTOM_POOL = {
        "worry", "anxious", "anxiety", "nervous", "tense",
        "restless", "keyed", "edge", "tired", "fatigue",
        "concentrate", "focus", "irritable", "muscle", "tension",
        "sleep", "insomnia",
    }

    # DSM-5 PTSD — Criterion B intrusion symptoms
    PTSD_INTRUSION_POOL = {
        "flashback", "nightmare", "intrusive", "memories", "triggered",
        "reliving", "trauma", "traumatic", "event", "distressing",
    }

    return [

        # --- SAFETY FIRST: Suicidal ideation always Level 1 ---
        Vixel(
            field="psychiatric",
            label="Suicidal Ideation — Active",
            source="DSM-5 / SAMHSA Crisis Standards",
            criteria="Any expression of suicidal ideation requires immediate safety assessment",
            conjuncts=[
                frozenset({"suicidal", "thoughts"}),
                frozenset({"want", "die"}),
                frozenset({"kill", "myself"}),
                frozenset({"end", "life"}),
                frozenset({"suicide", "plan"}),
                frozenset({"suicide", "method"}),
                frozenset({"not", "live"}),
                frozenset({"better", "dead"}),
            ],
            stakes=StakeVector(fp_cost=0.2, fn_cost=1.0, reversibility=0.0),
            escalation=EscalationLevel.IMMEDIATE,
            action=(
                "Contact crisis support immediately:\n"
                "  988 Suicide & Crisis Lifeline: call or text 988\n"
                "  Crisis Text Line: text HOME to 741741\n"
                "  Emergency: 911\n"
                "You are not alone. Help is available right now."
            ),
            notes="fn_cost=1.0: missing active suicidal ideation is catastrophic. No exceptions.",
        ),

        # --- LEVEL 2: Major Depressive Episode indicators ---
        Vixel(
            field="psychiatric",
            label="Major Depressive Episode — Screening Positive",
            source="DSM-5",
            criteria="DSM-5 296.xx: ≥5 symptoms from Criterion A, ≥2 weeks duration",
            conjuncts=[],
            count_mode=True,
            count_min=3,   # 3 tokens from pool = screening positive (full DSM requires 5 + duration)
            token_pool=MDE_SYMPTOM_POOL,
            stakes=StakeVector(fp_cost=0.3, fn_cost=0.7, reversibility=0.3),
            escalation=EscalationLevel.URGENT,
            action=(
                "These symptoms may indicate depression. Please speak with a mental health "
                "professional or your primary care doctor. This is not a diagnosis."
            ),
            notes=(
                "Count threshold set to 3 for screening (not clinical diagnosis). "
                "DSM-5 full criteria require 5 symptoms + 2-week duration + "
                "functional impairment — requires clinical assessment."
            ),
        ),

        # --- LEVEL 2: GAD indicators ---
        Vixel(
            field="psychiatric",
            label="Generalized Anxiety Disorder — Screening Positive",
            source="DSM-5",
            criteria="DSM-5 300.02: excessive worry + ≥3 physical symptoms, ≥6 months",
            conjuncts=[
                frozenset({"worry", "control"}),
                frozenset({"anxious", "everything"}),
                frozenset({"anxiety", "constant"}),
            ],
            count_mode=False,
            stakes=StakeVector(fp_cost=0.3, fn_cost=0.6, reversibility=0.4),
            escalation=EscalationLevel.URGENT,
            action=(
                "These symptoms may indicate an anxiety disorder. "
                "Speaking with a mental health professional is recommended."
            ),
            notes="GAD conjunction routing + count fallback below.",
        ),

        # GAD count mode fallback
        Vixel(
            field="psychiatric",
            label="Anxiety Symptoms — Multiple Indicators",
            source="DSM-5 / GAD-7",
            criteria="GAD-7: ≥3 items endorsed = mild-moderate anxiety",
            conjuncts=[],
            count_mode=True,
            count_min=3,
            token_pool=GAD_SYMPTOM_POOL,
            stakes=StakeVector(fp_cost=0.3, fn_cost=0.5, reversibility=0.5),
            escalation=EscalationLevel.URGENT,
            action=(
                "Multiple anxiety-related symptoms detected. "
                "Consider speaking with a mental health professional."
            ),
            notes="GAD-7 screening: 3+ endorsements = mild range.",
        ),

        # --- LEVEL 2: PTSD intrusion symptoms ---
        Vixel(
            field="psychiatric",
            label="PTSD — Intrusion Symptoms Present",
            source="DSM-5",
            criteria="DSM-5 309.81 Criterion B: ≥1 intrusion symptom required for PTSD diagnosis",
            conjuncts=[
                frozenset({"flashback"}),
                frozenset({"flashbacks"}),
                frozenset({"nightmare", "trauma"}),
                frozenset({"nightmare", "traumatic"}),
                frozenset({"reliving", "event"}),
                frozenset({"triggered", "memory"}),
                frozenset({"traumatic", "event"}),
            ],
            count_mode=False,
            stakes=StakeVector(fp_cost=0.3, fn_cost=0.7, reversibility=0.3),
            escalation=EscalationLevel.URGENT,
            action=(
                "Trauma-related symptoms detected. "
                "A trauma-informed therapist can provide evidence-based treatment (EMDR, CPT)."
            ),
            notes="Single flashback mention is sufficient for Criterion B screening.",
        ),

        # --- LEVEL 3: Single symptom / mild indicators ---
        Vixel(
            field="psychiatric",
            label="Mood / Wellbeing — Monitor",
            source="DSM-5 / PHQ-2",
            criteria="PHQ-2: 1-2 depressive symptoms = low risk, monitor",
            conjuncts=[],
            count_mode=True,
            count_min=1,
            token_pool={"sad", "depressed", "hopeless", "anxious", "worried", "stressed", "overwhelmed"},
            stakes=StakeVector(fp_cost=0.1, fn_cost=0.3, reversibility=0.7),
            escalation=EscalationLevel.MONITOR,
            action=(
                "If these feelings persist or worsen, speaking with someone you trust "
                "or a mental health professional may help."
            ),
            notes="Single mood token — acknowledge but don't over-escalate.",
        ),
    ]


# ============================================================
# LLM FIELD SELECTOR (interface + simulation)
# ============================================================

# Field routing vocabulary — LLM uses this to select drop column
FIELD_ROUTING_VOCAB = {
    "cardiac": {
        "chest", "heart", "cardiac", "coronary", "palpitation",
        "pulse", "beat", "artery", "angina", "infarction",
    },
    "psychiatric": {
        "feel", "feeling", "mood", "depressed", "anxious", "mental",
        "emotion", "thought", "mind", "psychiatric", "therapy",
        "hopeless", "worthless", "suicidal", "trauma", "flashback",
    },
    "neurological": {
        "headache", "migraine", "seizure", "dizzy", "numbness",
        "stroke", "weakness", "vision", "speech", "neuro",
    },
    "musculoskeletal": {
        "muscle", "joint", "bone", "back", "knee", "shoulder",
        "sprain", "fracture", "pain", "ache", "stiffness",
    },
    "respiratory": {
        "breath", "breathing", "cough", "wheeze", "asthma",
        "lung", "inhale", "oxygen", "respiratory",
    },
}


def llm_select_field(query: str) -> tuple[str, float]:
    """
    Simulates LLM field selection.

    In production: LLM reads query and returns field name.
    Here: vocabulary overlap scoring as proxy.

    Returns: (field_name, confidence)
    """
    tokens = set(query.lower().split())
    scores = {}
    for field_name, vocab in FIELD_ROUTING_VOCAB.items():
        overlap = len(tokens & vocab)
        scores[field_name] = overlap / max(len(vocab), 1)

    if not scores or max(scores.values()) == 0:
        return "unknown", 0.0

    best = max(scores, key=scores.get)
    return best, round(scores[best], 3)


# ============================================================
# PLINKO DROP — FULL PIPELINE
# ============================================================

def plinko_drop(query: str, grid: FieldGrid, field_override: str = None) -> dict:
    """
    Full TENT v10 pipeline:

      1. Tokenize
      2. Register gate (hyperbolic pressure)
      3. LLM selects field (or use override)
      4. Drop into field grid
      5. Vixels evaluate — deterministic from here
      6. Return escalation result

    field_override: used when actual LLM provides field selection.
                    If None, uses vocabulary proxy.
    """
    tokens = query.lower().split()
    token_set = {t.strip(".,!?;:()[]\"'") for t in tokens}

    # Register gate
    hyp_hits = len(token_set & HYPERBOLIC_LEXICON)
    h_pressure = hyp_hits / max(len(token_set), 1)
    if h_pressure >= HYPERBOLIC_THRESHOLD:
        return {
            "status":   RouteStatus.NOISE,
            "field":    None,
            "reason":   f"Hyperbolic pressure {h_pressure:.2f} >= {HYPERBOLIC_THRESHOLD}",
        }

    # Field selection
    if field_override:
        selected_field = field_override
        field_confidence = 1.0
    else:
        selected_field, field_confidence = llm_select_field(query)

    if selected_field == "unknown" or selected_field not in grid.fields:
        return {
            "status":  RouteStatus.NO_ROUTE,
            "field":   selected_field,
            "reason":  "LLM could not identify field",
        }

    # Drop into field
    result = grid.drop(selected_field, token_set)
    result["field_confidence"] = field_confidence
    result["llm_selected_field"] = selected_field
    result["query"] = query

    return result


# ============================================================
# BUILD GRID
# ============================================================

def build_grid() -> FieldGrid:
    return FieldGrid(fields={
        "cardiac":    build_cardiac_field(),
        "psychiatric": build_psychiatric_field(),
    })


# ============================================================
# TEST SUITE — TENT v10
# ============================================================

def run_tests(grid: FieldGrid) -> tuple[int, int]:

    test_cases = [
        # --- CARDIAC ---
        ("chest pain and tingling in my left arm",
         "cardiac", 1, "MI indicators — L1 IMMEDIATE"),
        ("I have chest tightness",
         "cardiac", 2, "Chest tightness — L2 URGENT"),
        ("my chest is sore and tender",
         "cardiac", 3, "Musculoskeletal — L3 MONITOR"),

        # --- PSYCHIATRIC: SAFETY FIRST ---
        ("I have been having suicidal thoughts",
         "psychiatric", 1, "Active SI — L1 IMMEDIATE"),
        ("I want to die and I have a plan",
         "psychiatric", 1, "Suicidal ideation with plan — L1 IMMEDIATE"),

        # --- PSYCHIATRIC: DSM-5 MDE screening ---
        ("I feel depressed and hopeless and so tired I can't concentrate",
         "psychiatric", 2, "MDE screening: depressed+hopeless+tired+concentrate = 4 tokens → L2"),
        ("I've been sad worthless and can't sleep and have no energy",
         "psychiatric", 2, "MDE: sad+worthless+sleep+energy = 4 tokens → L2"),

        # --- PSYCHIATRIC: PTSD ---
        ("I keep having flashbacks of the traumatic event",
         "psychiatric", 2, "PTSD intrusion: flashback → L2"),

        # --- PSYCHIATRIC: GAD ---
        ("I feel anxious and worried and I can't control the worry",
         "psychiatric", 2, "GAD conjunction: worry+control → L2"),

        # --- PSYCHIATRIC: MONITOR ---
        ("I've been feeling a bit sad lately",
         "psychiatric", 3, "Single mood token — L3 MONITOR"),

        # --- LLM FIELD SELECTION (proxy) ---
        ("chest tightness when I exercise",
         None, 2, "LLM selects cardiac from context → L2"),
        ("I feel hopeless and can't sleep or concentrate",
         None, 2, "LLM selects psychiatric → MDE screening"),

        # --- NOISE ---
        ("the most incredible amazing revolutionary breakthrough",
         None, None, "Hyperbolic noise → NOISE"),
    ]

    print("=" * 72)
    print("  TENT v10 — VIXEL FIELD GRID")
    print("  LLM selects column. Vixels catch. Deterministic from drop.")
    print("=" * 72)
    print(f"  Fields loaded: {list(grid.fields.keys())}")
    print(f"  Vixels: {sum(len(v) for v in grid.fields.values())}")
    print()

    passed = failed = 0

    for query, field_override, expected_level, description in test_cases:
        result = plinko_drop(query, grid, field_override)
        got_level = result.get("escalation")

        ok = got_level == expected_level
        passed += ok
        failed += not ok
        icon = "✓" if ok else "✗"

        field_str = result.get("llm_selected_field") or result.get("field") or "—"

        if result["status"] == RouteStatus.MATCHED:
            print(f"  [{icon}] L{got_level} {result.get('escalation_label',''):<10} "
                  f"[{field_str}] {result.get('label','')}")
            print(f"       Matched : {result.get('matched','')}")
            print(f"       Source  : {result.get('source','')}")
            action_lines = result.get('action','').split('\n')
            print(f"       Action  : {action_lines[0]}")
            for line in action_lines[1:]:
                if line.strip():
                    print(f"                {line}")
        elif result["status"] == RouteStatus.NOISE:
            print(f"  [{icon}] NOISE  [{field_str}]")
        else:
            print(f"  [{icon}] NO_ROUTE [{field_str}] — {result.get('reason','')}")

        if not ok:
            print(f"       EXPECTED level: {expected_level}")
        print(f"       Test: {description}")
        print()

    print("=" * 72)
    print(f"  RESULT: {passed}/{passed+failed} passed")
    print()
    print("  VIXEL REGISTRY:")
    for field_name, vixels in grid.fields.items():
        print(f"  [{field_name}]")
        for v in vixels:
            mode = f"count≥{v.count_min}" if v.count_mode else f"{len(v.conjuncts)} conjuncts"
            print(f"    L{v.escalation.value} {v.label[:45]:<45} "
                  f"{mode:<15} src={v.source}")
    print()
    print("  ARCHITECTURE:")
    print("  Query → Register Gate → LLM selects field → Drop into column")
    print("  Vixels evaluate (conjunction / count-threshold) → Escalation result")
    print("  LLM: stochastic field selection (semantic understanding)")
    print("  Vixels: deterministic evaluation (clinical criteria)")
    print("=" * 72)
    return passed, failed


# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":
    grid = build_grid()
    passed, failed = run_tests(grid)

    if failed == 0:
        print("\n  All tests passed. TENT v10 vixel grid operational.")
    else:
        print(f"\n  {failed} test(s) failed.")
