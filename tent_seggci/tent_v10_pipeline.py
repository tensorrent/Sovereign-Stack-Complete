#!/usr/bin/env python3
"""
TENT v10 — UNIFIED PIPELINE
============================

Three engines. One pass. Deterministic from field selection onward.

    Query
      │
      ▼
    [REGISTER GATE]
    Hyperbolic pressure check — noise rejection
      │
      ▼
    [LLM FIELD SELECTOR]
    Stochastic semantic understanding → field name
    This is the only stochastic step.
      │
      ▼
    [LEXENV]
    Symbols resolved in field context
    potential → alignment
    (pain :cardiac) ≠ (pain :casual)
      │
      ▼
    [SIGGEO]
    Natural language → SignalProfile (delta curve shape)
    Weighted Euclidean → nearest condition archetype
    The derivative is the signal. Not the value.
      │
      ▼
    [RC14 VIXEL GRID]
    Conjunction / count-threshold matching
    Escalation tier fires
    Stakes-weighted confidence check
      │
      ▼
    [OUTPUT]
    Escalation level + action + clinical source
    Or: NO_ROUTE with reason (abstain is correct)

The LLM aims. The geometry catches. The vixels escalate.
Nothing after field selection is stochastic.

Author: Brad Wallace / Claude
Version: TENT v10 unified
"""

import sys
sys.path.insert(0, '/home/claude')

from lexenv     import LexEnv, build_lexenv, tokenize_in_context
from siggeo     import (SignalGeometry, SignalProfile, CONDITION_ARCHETYPES,
                        parse_signal_from_text)
from tent_v10_vixel import (FieldGrid, build_grid, RouteStatus,
                             llm_select_field, HYPERBOLIC_LEXICON,
                             HYPERBOLIC_THRESHOLD)


# ============================================================
# PIPELINE RESULT
# ============================================================

class PipelineResult:
    """
    Full result from a single query pass through the pipeline.
    Every stage recorded — transparency, debuggability.
    """
    def __init__(self, query: str):
        self.query           = query
        self.status          = RouteStatus.NO_ROUTE
        # Stage 1: Register gate
        self.h_pressure      = 0.0
        self.gate_open       = True
        # Stage 2: Field selection
        self.field           = None
        self.field_confidence = 0.0
        # Stage 3: LEXENV
        self.escalators      = []
        self.count_tokens    = []
        self.anchors         = []
        self.noise_tokens    = []
        self.active_weight   = 0.0
        # Stage 4: SIGGEO
        self.signal_profile  = None
        self.nearest_condition = None
        self.condition_sim   = 0.0
        # Stage 5: Vixel
        self.escalation_level = None
        self.escalation_label = None
        self.action          = None
        self.matched_vixel   = None
        self.clinical_source = None
        self.matched_group   = None
        # Meta
        self.abstained       = False
        self.reason          = None

    def summary(self) -> str:
        lines = [f"Query: \"{self.query}\""]
        lines.append(f"Gate:  {'OPEN' if self.gate_open else 'CLOSED'} (h_pressure={self.h_pressure:.2f})")
        if self.gate_open:
            lines.append(f"Field: {self.field} (confidence={self.field_confidence:.3f})")
            if self.escalators:
                lines.append(f"Lexenv escalators: {[t for t,_ in self.escalators]}")
            if self.count_tokens:
                lines.append(f"Lexenv count pool: {[t for t,_ in self.count_tokens]}")
            if self.signal_profile:
                p = self.signal_profile
                lines.append(f"Signal: onset={p.onset.value} traj={p.trajectory.value} "
                            f"sat={p.saturation:.2f} dur={p.duration.value}")
            if self.nearest_condition:
                lines.append(f"Archetype: {self.nearest_condition} ({self.condition_sim:.1f}% sim)")
            lines.append(f"Status: {self.status.value}")
            if self.status == RouteStatus.MATCHED:
                lines.append(f"Level:  L{self.escalation_level} — {self.escalation_label}")
                lines.append(f"Source: {self.clinical_source}")
                lines.append(f"Matched: {self.matched_group}")
                for line in self.action.split('\n'):
                    lines.append(f"Action: {line}")
            elif self.abstained:
                lines.append(f"Abstained: {self.reason}")
        return '\n'.join(lines)


# ============================================================
# UNIFIED PIPELINE
# ============================================================

class TENTPipeline:
    """
    TENT v10 unified pipeline.
    
    Instantiate once, call .process(query) for each input.
    field_override: bypass LLM selector (for testing or when
                    the calling LLM passes its own field selection).
    """

    def __init__(self):
        # Build all three engines
        self.lexenv = build_lexenv()
        self.geo    = SignalGeometry()
        for name, profile in CONDITION_ARCHETYPES.items():
            self.geo.add_condition(name, profile)
        self.geo.build()
        self.grid   = build_grid()

    def process(self, query: str, field_override: str = None) -> PipelineResult:
        result = PipelineResult(query)
        tokens_raw = query.lower().split()
        token_set  = {t.strip(".,!?;:()[]\"'") for t in tokens_raw}

        # --------------------------------------------------------
        # STAGE 1: REGISTER GATE
        # --------------------------------------------------------
        hyp_hits = len(token_set & HYPERBOLIC_LEXICON)
        result.h_pressure = hyp_hits / max(len(token_set), 1)
        if result.h_pressure >= HYPERBOLIC_THRESHOLD:
            result.gate_open = False
            result.status    = RouteStatus.NOISE
            result.reason    = f"Hyperbolic pressure {result.h_pressure:.2f}"
            return result

        # --------------------------------------------------------
        # STAGE 2: FIELD SELECTION
        # --------------------------------------------------------
        if field_override:
            result.field = field_override
            result.field_confidence = 1.0
        else:
            result.field, result.field_confidence = llm_select_field(query)

        if result.field == "unknown" or result.field not in self.grid.fields:
            result.status = RouteStatus.NO_ROUTE
            result.reason = f"No field matched (got '{result.field}')"
            return result

        # --------------------------------------------------------
        # STAGE 3: LEXENV — resolve symbols in field context
        # --------------------------------------------------------
        lex = tokenize_in_context(query, result.field, self.lexenv)
        result.escalators   = lex["escalators"]
        result.count_tokens = lex["count_tokens"]
        result.anchors      = lex["anchors"]
        result.noise_tokens = lex["noise"]
        result.active_weight = lex["active_weight"]

        # --------------------------------------------------------
        # STAGE 4: SIGGEO — extract signal shape
        # --------------------------------------------------------
        result.signal_profile = parse_signal_from_text(query)
        nearest = self.geo.nearest_conditions(result.signal_profile, top_k=1)
        if nearest:
            result.nearest_condition = nearest[0][0]
            result.condition_sim     = nearest[0][2]

        # --------------------------------------------------------
        # STAGE 5: RC14 VIXEL — conjunction matching + escalation
        # --------------------------------------------------------
        vixel_result = self.grid.drop(result.field, token_set)

        if vixel_result["status"] == RouteStatus.MATCHED:
            result.status           = RouteStatus.MATCHED
            result.escalation_level = vixel_result["escalation"]
            result.escalation_label = vixel_result["escalation_label"]
            result.action           = vixel_result["action"]
            result.matched_vixel    = vixel_result["label"]
            result.clinical_source  = vixel_result["source"]
            result.matched_group    = vixel_result["matched"]

            # Signal geometry confirms or warns
            # If SIGGEO nearest archetype is in a different field, flag it
            if result.nearest_condition:
                arch_field = _archetype_field(result.nearest_condition)
                if arch_field and arch_field != result.field:
                    result.reason = (
                        f"NOTE: Signal shape closest to '{result.nearest_condition}' "
                        f"({arch_field} field, {result.condition_sim:.0f}% sim). "
                        f"Vixel matched {result.field}. Review if unexpected."
                    )
        else:
            result.status    = RouteStatus.NO_ROUTE
            result.abstained = True
            result.reason    = vixel_result.get("reason", "No vixel matched")

        return result


def _archetype_field(condition_name: str) -> str:
    """Map archetype names back to fields."""
    CARDIAC       = {"MI_suspected", "unstable_angina", "stable_angina", "musculoskeletal"}
    PSYCHIATRIC   = {"MDE", "panic_disorder", "GAD"}
    NEUROLOGICAL  = {"stroke_TIA", "migraine", "tension_headache"}
    RESPIRATORY   = {"asthma_attack"}
    if condition_name in CARDIAC:     return "cardiac"
    if condition_name in PSYCHIATRIC: return "psychiatric"
    if condition_name in NEUROLOGICAL: return "neurological"
    if condition_name in RESPIRATORY: return "respiratory"
    return None


# ============================================================
# TEST SUITE — FULL PIPELINE
# ============================================================

def run_pipeline_tests(pipe: TENTPipeline) -> tuple[int, int]:

    test_cases = [
        # (query, field_override, expected_status, expected_level, description)

        # --- CARDIAC ---
        ("sudden crushing chest pain that wont go away",
         "cardiac", RouteStatus.MATCHED, 1,
         "MI: sudden+saturating → L1"),

        ("I have chest tightness when I exercise",
         "cardiac", RouteStatus.MATCHED, 2,
         "Angina: exertional chest tightness → L2"),

        ("my chest is sore and tender",
         "cardiac", RouteStatus.MATCHED, 3,
         "MSK: chest sore → L3"),

        ("my chest hurts",
         "cardiac", RouteStatus.MATCHED, 2,
         "Minimal: chest+pain → L2 (correct — vixel catches this)"),

        # --- PSYCHIATRIC ---
        ("I have been having suicidal thoughts",
         "psychiatric", RouteStatus.MATCHED, 1,
         "Suicidal ideation → L1 IMMEDIATE"),

        ("I feel hopeless worthless tired and cant concentrate for weeks",
         "psychiatric", RouteStatus.MATCHED, 2,
         "MDE: 4 count tokens → L2"),

        ("I keep having flashbacks of the traumatic event",
         "psychiatric", RouteStatus.MATCHED, 2,
         "PTSD intrusion: flashbacks+traumatic+event → L2"),

        ("I feel a bit sad lately",
         "psychiatric", RouteStatus.MATCHED, 3,
         "Single mood token → L3 MONITOR"),

        # --- CROSS-DOMAIN: signal shape disambiguation ---
        ("sudden pain that tingling in my arm",
         "cardiac", RouteStatus.MATCHED, 1,
         "Cardiac: pain+tingling → L1, SIGGEO confirms"),

        # --- NO ROUTE ---
        ("I feel tired",
         "psychiatric", RouteStatus.NO_ROUTE, None,
         "Single unspecific token — abstain"),

        # --- NOISE ---
        ("this is the most incredible amazing revolutionary discovery",
         None, RouteStatus.NOISE, None,
         "Hyperbolic noise → gate closed"),

        # --- SIGNAL GEOMETRY CROSS-CHECK ---
        ("sudden chest pain radiating to my jaw",
         "cardiac", RouteStatus.MATCHED, 1,
         "Radiating jaw pain → L1, SIGGEO should confirm MI archetype"),
    ]

    print("=" * 72)
    print("  TENT v10 — UNIFIED PIPELINE")
    print("  LEXENV + SIGGEO + RC14 Vixel Grid")
    print("=" * 72)
    print()

    passed = failed = 0

    for query, field_override, exp_status, exp_level, description in test_cases:
        result = pipe.process(query, field_override)

        status_ok = result.status == exp_status
        level_ok  = result.escalation_level == exp_level
        ok        = status_ok and level_ok
        passed   += ok
        failed   += not ok
        icon      = "✓" if ok else "✗"

        print(f"  [{icon}] {result.status.value:<10} ", end="")
        if result.status == RouteStatus.MATCHED:
            print(f"L{result.escalation_level} [{result.field}] {result.matched_vixel or ''}")
        elif result.status == RouteStatus.NOISE:
            print("NOISE")
        else:
            print(f"NO_ROUTE — {result.reason[:55] if result.reason else ''}")

        # Show pipeline trace for matched results
        if result.status == RouteStatus.MATCHED:
            if result.escalators:
                print(f"       lexenv  : escalators={[t for t,_ in result.escalators]}")
            if result.count_tokens:
                print(f"       lexenv  : count={[t for t,_ in result.count_tokens]}")
            if result.signal_profile:
                p = result.signal_profile
                print(f"       signal  : {p.onset.value}|{p.trajectory.value}|"
                      f"sat={p.saturation:.2f}|{p.duration.value}")
            if result.nearest_condition:
                print(f"       archetype: {result.nearest_condition} ({result.condition_sim:.0f}%)")
            print(f"       matched : {result.matched_group}")
            print(f"       source  : {result.clinical_source}")
            if result.reason:
                print(f"       note    : {result.reason[:65]}")

        if not ok:
            print(f"       EXPECTED: {exp_status.value} L{exp_level}")

        print(f"       {description}")
        print()

    print("=" * 72)
    print(f"  RESULT: {passed}/{passed+failed} passed")
    print()
    print("  PIPELINE STAGES:")
    print("  1. Register gate    — hyperbolic pressure (RC12)")
    print("  2. Field selection  — LLM semantic aim (stochastic, one step)")
    print("  3. LEXENV           — symbol binding in field context")
    print("                        potential → value only through alignment")
    print("  4. SIGGEO           — delta curve → condition archetype")
    print("                        the derivative is the signal")
    print("  5. RC14 Vixel       — conjunction/count → escalation tier")
    print("                        deterministic from field selection onward")
    print("=" * 72)

    return passed, failed


# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":
    pipe = TENTPipeline()
    passed, failed = run_pipeline_tests(pipe)

    if failed == 0:
        print("\n  All tests passed. TENT v10 unified pipeline operational.")
    else:
        print(f"\n  {failed} test(s) failed.")

    # Interactive demo
    print()
    print("  INTERACTIVE DEMO:")
    print("  Enter queries to route. Field auto-detected. Ctrl-C to exit.")
    print()
    try:
        while True:
            query = input("  > ").strip()
            if not query:
                continue
            result = pipe.process(query)
            print()
            print(result.summary())
            print()
    except (KeyboardInterrupt, EOFError):
        print()
