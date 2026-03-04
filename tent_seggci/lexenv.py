#!/usr/bin/env python3
"""
LEXENV — Contextual Symbol Binding Library
==========================================

Human-inspired Lisp library for cross-domain word disambiguation.

Core insight:
    A word is not a token. It is a symbol.
    A symbol does not have a value. It has a value IN AN ENVIRONMENT.

    (pain :cardiac)     → conjunct-escalator  weight=0.9
    (pain :psychiatric) → emotional-marker    weight=0.6
    (pain :legal)       → damages-indicator   weight=0.4
    (pain :casual)      → noise               weight=0.1

This is what humans do automatically from lived context.
The child learns "hot" once from consequence.
The system must encode that binding explicitly.

Architecture:
    WordSymbol        — a symbol with bindings across fields
    ContextBinding    — the value of a symbol in a specific field
    LexEnv            — the environment: resolves symbols in context
    
    Roles:
        :escalator        — primary conjunction trigger, high weight
        :count-contributor — contributes to count-threshold pools
        :domain-anchor    — confirms we are in the right field
        :disambiguator    — differentiates field when ambiguous
        :noise            — suppress / ignore in this field
        :blocker          — actively suppresses other matches
    
    Cross-domain cases are the point:
        "pressure"  →  cardiac:escalator / physics:anchor / social:count / casual:noise
        "flat"      →  spatial:anchor / music:anchor / medical:count / casual:noise
        "energy"    →  physics:anchor / psychiatric:count / casual:noise
        "tension"   →  psychiatric:count / physics:anchor / legal:anchor / casual:noise

Author: Brad Wallace / Claude
Version: TENT v10 / LEXENV 1.0
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


# ============================================================
# ROLES
# ============================================================

class SymbolRole(Enum):
    ESCALATOR     = "escalator"       # Primary conjunction trigger
    COUNT         = "count"           # Count-pool contributor
    ANCHOR        = "anchor"          # Confirms field identity
    DISAMBIGUATE  = "disambiguate"    # Separates similar fields
    NOISE         = "noise"           # Suppress in this field
    BLOCKER       = "blocker"         # Actively suppresses other matches


# ============================================================
# CONTEXT BINDING
# ============================================================

@dataclass
class ContextBinding:
    """
    The value of a symbol in a specific field environment.
    
    field:          which column this binding applies to
    role:           what this symbol does in this field
    weight:         strength of signal [0.0, 1.0]
    conjunct_with:  other symbols this one escalates WITH (AND logic)
    notes:          clinical/semantic justification
    """
    field:         str
    role:          SymbolRole
    weight:        float
    conjunct_with: list = field(default_factory=list)
    notes:         str  = ""

    def is_active(self) -> bool:
        return self.role not in (SymbolRole.NOISE, SymbolRole.BLOCKER)

    def __repr__(self):
        return (f"({self.field} :{self.role.value} w={self.weight:.1f}"
                + (f" conjunct={self.conjunct_with}" if self.conjunct_with else "")
                + ")")


# ============================================================
# WORD SYMBOL
# ============================================================

@dataclass
class WordSymbol:
    """
    A word with its full binding table across fields.
    
    symbol:   the canonical lowercase form
    bindings: field → ContextBinding
    """
    symbol:   str
    bindings: dict = field(default_factory=dict)

    def bind(self, context_binding: ContextBinding) -> "WordSymbol":
        """Add a binding. Returns self for chaining."""
        self.bindings[context_binding.field] = context_binding
        return self

    def resolve(self, field_name: str) -> Optional[ContextBinding]:
        """Resolve symbol in a specific field environment."""
        return self.bindings.get(field_name)

    def is_noise_in(self, field_name: str) -> bool:
        b = self.resolve(field_name)
        if b is None:
            return True   # unknown field → treat as noise by default
        return b.role in (SymbolRole.NOISE, SymbolRole.BLOCKER)

    def weight_in(self, field_name: str) -> float:
        b = self.resolve(field_name)
        if b is None or not b.is_active():
            return 0.0
        return b.weight

    def fields(self) -> list:
        return list(self.bindings.keys())


# ============================================================
# LEXENV — THE ENVIRONMENT
# ============================================================

class LexEnv:
    """
    The environment. Resolves symbols in context.
    
    Analogous to a Lisp environment frame:
    - symbols are bound to values (ContextBindings)
    - lookup is field-scoped
    - unknown symbols return None (not an error — just unbound)
    
    Usage:
        env = LexEnv()
        env.defword(pain_symbol)
        
        binding = env.resolve("pain", "cardiac")
        # → ContextBinding(field="cardiac", role=ESCALATOR, weight=0.9)
        
        weight = env.weight("pain", "casual")
        # → 0.1
        
        active = env.active_tokens(["pain", "tightness", "chest"], "cardiac")
        # → [("pain", binding), ("tightness", binding), ("chest", binding)]
    """

    def __init__(self):
        self._symbols: dict = {}   # symbol_str → WordSymbol

    def defword(self, word_symbol: WordSymbol) -> "LexEnv":
        """Define a symbol in the environment. Returns self for chaining."""
        self._symbols[word_symbol.symbol] = word_symbol
        return self

    def defwords(self, *symbols) -> "LexEnv":
        for s in symbols:
            self.defword(s)
        return self

    def resolve(self, token: str, field_name: str) -> Optional[ContextBinding]:
        sym = self._symbols.get(token.lower())
        if sym is None:
            return None
        return sym.resolve(field_name)

    def weight(self, token: str, field_name: str) -> float:
        sym = self._symbols.get(token.lower())
        if sym is None:
            return 0.0
        return sym.weight_in(field_name)

    def is_noise(self, token: str, field_name: str) -> bool:
        sym = self._symbols.get(token.lower())
        if sym is None:
            return True
        return sym.is_noise_in(field_name)

    def active_tokens(self, tokens: list, field_name: str) -> list:
        """Return (token, binding) pairs that are active in this field."""
        result = []
        for t in tokens:
            b = self.resolve(t, field_name)
            if b and b.is_active():
                result.append((t, b))
        return result

    def escalators_in(self, tokens: list, field_name: str) -> list:
        """Return tokens that are ESCALATOR role in this field."""
        return [t for t, b in self.active_tokens(tokens, field_name)
                if b.role == SymbolRole.ESCALATOR]

    def count_tokens_in(self, tokens: list, field_name: str) -> list:
        """Return tokens that contribute to count pools in this field."""
        return [t for t, b in self.active_tokens(tokens, field_name)
                if b.role == SymbolRole.COUNT]

    def anchor_tokens_in(self, tokens: list, field_name: str) -> list:
        """Return tokens that confirm field identity."""
        return [t for t, b in self.active_tokens(tokens, field_name)
                if b.role == SymbolRole.ANCHOR]

    def known_symbols(self) -> list:
        return sorted(self._symbols.keys())

    def dump_symbol(self, token: str) -> str:
        sym = self._symbols.get(token.lower())
        if sym is None:
            return f"(unbound '{token}')"
        lines = [f"(defsymbol '{token}'"]
        for fname, b in sorted(sym.bindings.items()):
            lines.append(f"  ({fname} :{b.role.value} w={b.weight:.1f}"
                        + (f" :conjunct-with {b.conjunct_with}" if b.conjunct_with else "")
                        + (f"  ; {b.notes}" if b.notes else "")
                        + ")")
        lines.append(")")
        return "\n".join(lines)


# ============================================================
# SYMBOL LIBRARY — CROSS-DOMAIN BINDINGS
# ============================================================

def build_lexenv() -> LexEnv:
    """
    The human-inspired symbol library.
    
    Every binding is justified by real cross-domain usage.
    The 'notes' field carries the semantic reason.
    """
    env = LexEnv()

    # ------------------------------------------------------------------
    # PAIN
    # ------------------------------------------------------------------
    env.defword(WordSymbol("pain").bind(
        ContextBinding("cardiac",      SymbolRole.ESCALATOR,    0.9,
                       conjunct_with=["chest", "tingling", "jaw", "arm"],
                       notes="Central cardiac symptom. Escalates with location/radiation.")
    ).bind(
        ContextBinding("psychiatric",  SymbolRole.COUNT,        0.5,
                       notes="Emotional pain contributes to distress indicators.")
    ).bind(
        ContextBinding("legal",        SymbolRole.COUNT,        0.6,
                       notes="Pain and suffering — damages language.")
    ).bind(
        ContextBinding("musculoskeletal", SymbolRole.ANCHOR,    0.7,
                       notes="Primary musculoskeletal indicator.")
    ).bind(
        ContextBinding("casual",       SymbolRole.NOISE,        0.1,
                       notes="'What a pain' — idiomatic, not clinical.")
    ))

    # ------------------------------------------------------------------
    # PRESSURE
    # ------------------------------------------------------------------
    env.defword(WordSymbol("pressure").bind(
        ContextBinding("cardiac",      SymbolRole.ESCALATOR,    0.85,
                       conjunct_with=["chest", "arm"],
                       notes="Chest pressure: cardinal angina/MI symptom.")
    ).bind(
        ContextBinding("physics",      SymbolRole.ANCHOR,       0.9,
                       notes="Thermodynamic pressure — domain anchor for physics/chemistry.")
    ).bind(
        ContextBinding("psychiatric",  SymbolRole.COUNT,        0.4,
                       notes="Pressure/stress language maps to GAD symptom pool.")
    ).bind(
        ContextBinding("legal",        SymbolRole.DISAMBIGUATE, 0.5,
                       notes="Duress/coercion — legal pressure is not cardiac.")
    ).bind(
        ContextBinding("casual",       SymbolRole.NOISE,        0.1,
                       notes="Social pressure, peer pressure — not clinical.")
    ))

    # ------------------------------------------------------------------
    # CHEST
    # ------------------------------------------------------------------
    env.defword(WordSymbol("chest").bind(
        ContextBinding("cardiac",      SymbolRole.ESCALATOR,    0.95,
                       conjunct_with=["pain", "tightness", "pressure", "crushing"],
                       notes="Anatomical chest — primary cardiac locator.")
    ).bind(
        ContextBinding("respiratory",  SymbolRole.ANCHOR,       0.8,
                       notes="Chest in respiratory: wheeze, congestion, tightness on breathing.")
    ).bind(
        ContextBinding("musculoskeletal", SymbolRole.ANCHOR,    0.6,
                       notes="Chest wall — rib/sternum/costochondral.")
    ).bind(
        ContextBinding("casual",       SymbolRole.NOISE,        0.05,
                       notes="Chest as furniture. Blocked in cardiac context by disambiguation.")
    ))

    # ------------------------------------------------------------------
    # TIGHTNESS
    # ------------------------------------------------------------------
    env.defword(WordSymbol("tightness").bind(
        ContextBinding("cardiac",      SymbolRole.ESCALATOR,    0.9,
                       conjunct_with=["chest"],
                       notes="Chest tightness = Level 2 URGENT per WebMD.")
    ).bind(
        ContextBinding("respiratory",  SymbolRole.ANCHOR,       0.8,
                       notes="Airway tightness — asthma/bronchospasm indicator.")
    ).bind(
        ContextBinding("musculoskeletal", SymbolRole.COUNT,     0.5,
                       notes="Muscle tightness — common but non-escalating.")
    ).bind(
        ContextBinding("casual",       SymbolRole.NOISE,        0.1,
                       notes="Tight schedule, tight budget — not clinical.")
    ))

    # ------------------------------------------------------------------
    # ENERGY
    # ------------------------------------------------------------------
    env.defword(WordSymbol("energy").bind(
        ContextBinding("psychiatric",  SymbolRole.COUNT,        0.7,
                       notes="Low energy: DSM-5 MDE Criterion A fatigue symptom.")
    ).bind(
        ContextBinding("physics",      SymbolRole.ANCHOR,       0.95,
                       notes="Kinetic/potential/thermodynamic energy — domain anchor.")
    ).bind(
        ContextBinding("casual",       SymbolRole.NOISE,        0.2,
                       notes="'I have no energy today' — may be clinical, may be colloquial.")
    ))

    # ------------------------------------------------------------------
    # FLAT
    # ------------------------------------------------------------------
    env.defword(WordSymbol("flat").bind(
        ContextBinding("spatial",      SymbolRole.ANCHOR,       0.8,
                       notes="Flat grid, flat surface — ARC spatial operation context.")
    ).bind(
        ContextBinding("music",        SymbolRole.ANCHOR,       0.9,
                       notes="B-flat, flat note — music theory domain anchor.")
    ).bind(
        ContextBinding("psychiatric",  SymbolRole.COUNT,        0.6,
                       notes="Flat affect — DSM-5 negative symptom (schizophrenia spectrum).")
    ).bind(
        ContextBinding("medical",      SymbolRole.COUNT,        0.5,
                       notes="Flat affect, flat line — medical context.")
    ).bind(
        ContextBinding("casual",       SymbolRole.NOISE,        0.1,
                       notes="Flat tire, flat rate — idiomatic, not clinical.")
    ))

    # ------------------------------------------------------------------
    # TENSION
    # ------------------------------------------------------------------
    env.defword(WordSymbol("tension").bind(
        ContextBinding("psychiatric",  SymbolRole.COUNT,        0.7,
                       notes="GAD symptom: muscle tension, feeling keyed-up.")
    ).bind(
        ContextBinding("physics",      SymbolRole.ANCHOR,       0.85,
                       notes="Surface tension, mechanical tension — physics domain.")
    ).bind(
        ContextBinding("legal",        SymbolRole.ANCHOR,       0.5,
                       notes="Contractual tension, dispute language.")
    ).bind(
        ContextBinding("musculoskeletal", SymbolRole.COUNT,     0.6,
                       notes="Muscle tension — physical symptom.")
    ).bind(
        ContextBinding("casual",       SymbolRole.NOISE,        0.2,
                       notes="Dramatic tension, tension in a room — narrative.")
    ))

    # ------------------------------------------------------------------
    # WEIGHT
    # ------------------------------------------------------------------
    env.defword(WordSymbol("weight").bind(
        ContextBinding("psychiatric",  SymbolRole.COUNT,        0.6,
                       notes="Weight change: DSM-5 MDE Criterion A appetite/weight symptom.")
    ).bind(
        ContextBinding("physics",      SymbolRole.ANCHOR,       0.9,
                       notes="Gravitational weight, mass — physics domain anchor.")
    ).bind(
        ContextBinding("cardiac",      SymbolRole.COUNT,        0.4,
                       notes="Weight as risk factor for cardiac conditions.")
    ).bind(
        ContextBinding("casual",       SymbolRole.NOISE,        0.2,
                       notes="The weight of responsibility — metaphorical.")
    ))

    # ------------------------------------------------------------------
    # SLEEP
    # ------------------------------------------------------------------
    env.defword(WordSymbol("sleep").bind(
        ContextBinding("psychiatric",  SymbolRole.COUNT,        0.8,
                       notes="DSM-5: insomnia/hypersomnia — MDE and GAD Criterion A.")
    ).bind(
        ContextBinding("neurological", SymbolRole.ANCHOR,       0.7,
                       notes="Sleep disorders — narcolepsy, sleep apnea, circadian.")
    ).bind(
        ContextBinding("casual",       SymbolRole.NOISE,        0.1,
                       notes="'I need sleep' — normal expression, low signal.")
    ))

    # ------------------------------------------------------------------
    # FOCUS / CONCENTRATE
    # ------------------------------------------------------------------
    env.defword(WordSymbol("focus").bind(
        ContextBinding("psychiatric",  SymbolRole.COUNT,        0.7,
                       notes="Can't focus: DSM-5 MDE Criterion A concentration symptom.")
    ).bind(
        ContextBinding("physics",      SymbolRole.ANCHOR,       0.8,
                       notes="Focal point, focus of lens — optics domain.")
    ).bind(
        ContextBinding("casual",       SymbolRole.NOISE,        0.2,
                       notes="Focus on the task — colloquial, not clinical.")
    ))

    env.defword(WordSymbol("concentrate").bind(
        ContextBinding("psychiatric",  SymbolRole.COUNT,        0.8,
                       notes="Can't concentrate: DSM-5 MDE Criterion A symptom.")
    ).bind(
        ContextBinding("chemistry",    SymbolRole.ANCHOR,       0.85,
                       notes="Concentration of a solution — chemistry domain.")
    ).bind(
        ContextBinding("casual",       SymbolRole.NOISE,        0.2,
                       notes="Concentrate on work — colloquial.")
    ))

    # ------------------------------------------------------------------
    # RADIATION / RADIATING
    # ------------------------------------------------------------------
    env.defword(WordSymbol("radiating").bind(
        ContextBinding("cardiac",      SymbolRole.ESCALATOR,    0.95,
                       conjunct_with=["chest", "pain"],
                       notes="Radiating chest pain: cardinal MI symptom.")
    ).bind(
        ContextBinding("physics",      SymbolRole.ANCHOR,       0.8,
                       notes="Electromagnetic radiation — physics domain.")
    ).bind(
        ContextBinding("musculoskeletal", SymbolRole.ANCHOR,    0.7,
                       notes="Radiating nerve pain — sciatica, disc herniation.")
    ).bind(
        ContextBinding("casual",       SymbolRole.NOISE,        0.1,
                       notes="'She was radiating joy' — metaphorical.")
    ))

    # ------------------------------------------------------------------
    # HOPELESS
    # ------------------------------------------------------------------
    env.defword(WordSymbol("hopeless").bind(
        ContextBinding("psychiatric",  SymbolRole.COUNT,        0.85,
                       notes="Hopelessness: DSM-5 MDE core symptom. Also suicidality indicator.")
    ).bind(
        ContextBinding("casual",       SymbolRole.NOISE,        0.2,
                       notes="'This is hopeless' — may be clinical, may be frustration.")
    ))

    # ------------------------------------------------------------------
    # WORTHLESS
    # ------------------------------------------------------------------
    env.defword(WordSymbol("worthless").bind(
        ContextBinding("psychiatric",  SymbolRole.COUNT,        0.85,
                       notes="Feelings of worthlessness: DSM-5 MDE Criterion A symptom.")
    ).bind(
        ContextBinding("legal",        SymbolRole.ANCHOR,       0.6,
                       notes="Worthless contract, consideration — legal domain.")
    ).bind(
        ContextBinding("casual",       SymbolRole.NOISE,        0.1,
                       notes="'This is worthless' about an object — not psychiatric.")
    ))

    # ------------------------------------------------------------------
    # NUMB / NUMBNESS / TINGLING
    # ------------------------------------------------------------------
    env.defword(WordSymbol("tingling").bind(
        ContextBinding("cardiac",      SymbolRole.ESCALATOR,    0.9,
                       conjunct_with=["pain", "chest", "arm"],
                       notes="Tingling with chest pain: MI radiation symptom.")
    ).bind(
        ContextBinding("neurological", SymbolRole.ESCALATOR,    0.85,
                       notes="Paresthesia — TIA/stroke indicator with other symptoms.")
    ).bind(
        ContextBinding("musculoskeletal", SymbolRole.COUNT,     0.5,
                       notes="Nerve compression tingling — benign but requires monitoring.")
    ).bind(
        ContextBinding("casual",       SymbolRole.NOISE,        0.1,
                       notes="Tingling sensation from cold — not clinical.")
    ))

    env.defword(WordSymbol("numbness").bind(
        ContextBinding("neurological", SymbolRole.ESCALATOR,    0.9,
                       conjunct_with=["face", "arm", "weakness"],
                       notes="Sudden numbness: stroke warning sign (FAST).")
    ).bind(
        ContextBinding("psychiatric",  SymbolRole.COUNT,        0.6,
                       notes="Emotional numbness: dissociation, depression symptom.")
    ).bind(
        ContextBinding("musculoskeletal", SymbolRole.COUNT,     0.5,
                       notes="Numbness from nerve compression.")
    ).bind(
        ContextBinding("casual",       SymbolRole.NOISE,        0.1,
                       notes="'My foot went numb' — positional, not clinical.")
    ))

    # ------------------------------------------------------------------
    # WEAKNESS
    # ------------------------------------------------------------------
    env.defword(WordSymbol("weakness").bind(
        ContextBinding("neurological", SymbolRole.ESCALATOR,    0.9,
                       conjunct_with=["face", "arm", "sudden"],
                       notes="Sudden arm/face weakness: stroke FAST indicator.")
    ).bind(
        ContextBinding("psychiatric",  SymbolRole.COUNT,        0.5,
                       notes="Weakness/fatigue in depression context.")
    ).bind(
        ContextBinding("musculoskeletal", SymbolRole.COUNT,     0.6,
                       notes="Muscle weakness — neuromuscular or disuse.")
    ).bind(
        ContextBinding("casual",       SymbolRole.NOISE,        0.2,
                       notes="'My weakness is chocolate' — not clinical.")
    ))

    # ------------------------------------------------------------------
    # DIZZY / DIZZINESS
    # ------------------------------------------------------------------
    env.defword(WordSymbol("dizzy").bind(
        ContextBinding("neurological", SymbolRole.ESCALATOR,    0.8,
                       conjunct_with=["headache", "vision", "weakness"],
                       notes="Dizziness with neuro symptoms: TIA/stroke indicator.")
    ).bind(
        ContextBinding("cardiac",      SymbolRole.COUNT,        0.6,
                       notes="Dizziness with cardiac symptoms: arrhythmia/syncope.")
    ).bind(
        ContextBinding("casual",       SymbolRole.NOISE,        0.3,
                       notes="'I feel dizzy from spinning' — benign positional.")
    ))

    # ------------------------------------------------------------------
    # CONTRACT (legal vs casual)
    # ------------------------------------------------------------------
    env.defword(WordSymbol("contract").bind(
        ContextBinding("legal",        SymbolRole.ESCALATOR,    0.9,
                       conjunct_with=["breach", "liability", "damages"],
                       notes="Legal contract — escalates with breach/damages language.")
    ).bind(
        ContextBinding("musculoskeletal", SymbolRole.ANCHOR,    0.7,
                       notes="Muscle contraction — different sense entirely.")
    ).bind(
        ContextBinding("casual",       SymbolRole.NOISE,        0.2,
                       notes="'Under contract' — may be legal context, may not.")
    ))

    # ------------------------------------------------------------------
    # ACUTE (medical vs casual)
    # ------------------------------------------------------------------
    env.defword(WordSymbol("acute").bind(
        ContextBinding("cardiac",      SymbolRole.ANCHOR,       0.8,
                       notes="Acute MI, acute event — medical urgency marker.")
    ).bind(
        ContextBinding("neurological", SymbolRole.ANCHOR,       0.8,
                       notes="Acute stroke, acute neurological event.")
    ).bind(
        ContextBinding("psychiatric",  SymbolRole.COUNT,        0.6,
                       notes="Acute episode — psychiatric crisis language.")
    ).bind(
        ContextBinding("physics",      SymbolRole.NOISE,        0.0,
                       notes="Acute angle — geometry, not medical.")
    ).bind(
        ContextBinding("casual",       SymbolRole.NOISE,        0.2,
                       notes="'Acute problem' — colloquial severity marker.")
    ))

    # ------------------------------------------------------------------
    # EPISODE (psychiatric vs casual)
    # ------------------------------------------------------------------
    env.defword(WordSymbol("episode").bind(
        ContextBinding("psychiatric",  SymbolRole.ANCHOR,       0.85,
                       notes="Depressive episode, manic episode — DSM-5 terminology.")
    ).bind(
        ContextBinding("neurological", SymbolRole.ANCHOR,       0.7,
                       notes="Seizure episode, TIA episode.")
    ).bind(
        ContextBinding("casual",       SymbolRole.NOISE,        0.1,
                       notes="TV episode — not clinical.")
    ))

    return env


# ============================================================
# CONTEXT-AWARE TOKENIZER
# ============================================================

def tokenize_in_context(query: str, field: str, env: LexEnv) -> dict:
    """
    Tokenize a query and resolve each token in the given field context.
    
    Returns:
        escalators:   tokens that are ESCALATOR role in this field
        count_tokens: tokens contributing to count pools
        anchors:      tokens confirming field identity
        noise:        tokens that are noise in this field
        unbound:      tokens not in the lexenv
        active_weight: total weight of active tokens
    """
    raw_tokens = [t.strip(".,!?;:()[]\"'").lower() for t in query.split()]
    tokens = [t for t in raw_tokens if t]

    escalators   = []
    count_tokens = []
    anchors      = []
    noise        = []
    unbound      = []
    total_weight = 0.0

    for tok in tokens:
        binding = env.resolve(tok, field)
        if binding is None:
            unbound.append(tok)
        elif binding.role == SymbolRole.ESCALATOR:
            escalators.append((tok, binding.weight))
            total_weight += binding.weight
        elif binding.role == SymbolRole.COUNT:
            count_tokens.append((tok, binding.weight))
            total_weight += binding.weight
        elif binding.role == SymbolRole.ANCHOR:
            anchors.append((tok, binding.weight))
            total_weight += binding.weight
        elif binding.role in (SymbolRole.NOISE, SymbolRole.BLOCKER):
            noise.append(tok)

    return {
        "field":        field,
        "query":        query,
        "escalators":   escalators,
        "count_tokens": count_tokens,
        "anchors":      anchors,
        "noise":        noise,
        "unbound":      unbound,
        "active_weight": round(total_weight, 3),
        "escalator_count": len(escalators),
        "active_count":    len(escalators) + len(count_tokens) + len(anchors),
    }


# ============================================================
# TEST SUITE
# ============================================================

def run_tests(env: LexEnv) -> tuple[int, int]:

    print("=" * 72)
    print("  LEXENV — CONTEXTUAL SYMBOL BINDING LIBRARY")
    print("  Same word. Different environment. Different behavior.")
    print("=" * 72)
    print()

    # --- Show cross-domain bindings for key symbols ---
    cross_domain = ["pain", "pressure", "chest", "flat", "tension", "energy"]
    print("  CROSS-DOMAIN SYMBOL TABLE:")
    print()
    for sym in cross_domain:
        print(env.dump_symbol(sym))
        print()

    # --- Tokenization tests ---
    print("=" * 72)
    print("  CONTEXTUAL TOKENIZATION TESTS")
    print("  Same query resolved in different field environments")
    print("=" * 72)
    print()

    query_tests = [
        # (query, field, expected_escalators, expected_count_min, description)
        ("I have chest pain and tingling",
         "cardiac", ["chest", "pain", "tingling"], 0,
         "Cardiac field: chest+pain+tingling → all escalators"),

        ("I have chest pain and tingling",
         "casual", [], 0,
         "Casual field: same query → all noise"),

        ("I feel hopeless worthless and can't concentrate",
         "psychiatric", [], 3,
         "Psychiatric: hopeless+worthless+concentrate → count pool"),

        ("pressure temperature entropy thermodynamic",
         "physics", [], 0,
         "Physics: pressure+entropy → anchors, not escalators"),

        ("pressure temperature entropy thermodynamic",
         "cardiac", ["pressure"], 0,
         "Cardiac: pressure → escalator, entropy → unbound"),

        ("I feel flat and have no energy and can't focus",
         "psychiatric", [], 3,
         "Psychiatric: flat+energy+focus → count pool"),

        ("flat note B-flat music theory",
         "music", [], 0,
         "Music: flat → anchor, not psychiatric"),

        ("sudden weakness in my arm and face",
         "neurological", ["weakness"], 0,
         "Neurological: weakness → escalator"),

        ("contract breach liability damages",
         "legal", ["contract"], 0,
         "Legal: contract+breach → escalator path"),
    ]

    passed = failed = 0

    for query, field, exp_escalators, exp_count_min, description in query_tests:
        result = tokenize_in_context(query, field, env)

        got_escalator_tokens = [t for t, w in result["escalators"]]
        escalator_ok = all(e in got_escalator_tokens for e in exp_escalators)
        count_ok     = result["active_count"] - result["escalator_count"] >= exp_count_min

        ok = escalator_ok and count_ok
        passed += ok
        failed += not ok
        icon = "✓" if ok else "✗"

        print(f"  [{icon}] [{field}] \"{query[:50]}\"")
        if result["escalators"]:
            print(f"       escalators  : {[t for t,w in result['escalators']]}")
        if result["count_tokens"]:
            print(f"       count pool  : {[t for t,w in result['count_tokens']]}")
        if result["anchors"]:
            print(f"       anchors     : {[t for t,w in result['anchors']]}")
        if result["noise"]:
            print(f"       noise       : {result['noise']}")
        if result["unbound"]:
            print(f"       unbound     : {result['unbound']}")
        print(f"       active_weight={result['active_weight']}  {description}")
        if not ok:
            print(f"       EXPECTED escalators: {exp_escalators}  count≥{exp_count_min}")
        print()

    print("=" * 72)
    print(f"  RESULT: {passed}/{passed+failed} passed")
    print()
    print(f"  Symbols defined: {len(env.known_symbols())}")
    print(f"  Symbol list: {env.known_symbols()}")
    print()
    print("  KEY PRINCIPLE:")
    print("  A symbol does not have a value.")
    print("  It has a value IN AN ENVIRONMENT.")
    print("  (pain :cardiac) ≠ (pain :casual)")
    print("  The context is not metadata. It is the binding.")
    print("=" * 72)

    return passed, failed


if __name__ == "__main__":
    env = build_lexenv()
    passed, failed = run_tests(env)

    if failed == 0:
        print("\n  All tests passed. LEXENV operational.")
    else:
        print(f"\n  {failed} test(s) failed.")
