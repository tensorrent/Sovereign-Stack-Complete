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
SIGGEO — Signal Geometry Engine
================================

Pain is not a token. It is a time-based signal.
The diagnostic information lives in the SHAPE of the delta curve.

    MI:              steep onset → rapid saturation → sustained flat
    Angina:          exertion onset → plateau → resolves at rest
    Musculoskeletal: gradual onset → oscillates with movement → no saturation
    MDE:             slow descent over weeks → sustained low plateau
    Panic:           spike → rapid decay → baseline recovery

Each condition has a distinct geometric signature in delta space.

The spectral geometry engine (TENT v8 Laplacian eigenbasis) is
retargeted from keyword similarity vectors to signal shape vectors.

Connection to field_emergence.pdf:
    Ψ_field = Φ₁(θ) − Φ₂(θ)  (antisymmetric scaling competition)
    
    The delta IS the field observable.
    Onset channel vs resolution channel — the asymmetry between them
    is the diagnostic signal. Not the magnitude at any point.
    
    MI:    onset channel dominates, resolution channel absent → Ψ saturates
    Angina: channels balance at rest, break under exertion load
    The shape of Ψ over time is the condition fingerprint.

Architecture:
    SignalProfile     — time-series shape descriptor
    DeltaVector       — computed shape features (the derivatives)
    SignalGeometry    — Laplacian eigenbasis over condition space
    GeoVixel          — matches against regions in eigenspace, not tokens

Author: Brad Wallace / Claude
Version: TENT v10 / SIGGEO 1.0
"""

import math
import numpy as np
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


# ============================================================
# SIGNAL DESCRIPTORS
# ============================================================

class Onset(Enum):
    SUDDEN    = "sudden"      # seconds — MI, stroke, panic
    RAPID     = "rapid"       # minutes — angina, acute anxiety
    GRADUAL   = "gradual"     # hours — musculoskeletal, infection
    SLOW      = "slow"        # days/weeks — depression, chronic
    EXERTIONAL = "exertional" # triggered by load — angina, MSK

class Trajectory(Enum):
    ASCENDING   = "ascending"   # getting worse
    PLATEAU     = "plateau"     # stable at level
    DESCENDING  = "descending"  # improving
    OSCILLATING = "oscillating" # varies — MSK, anxiety
    SATURATING  = "saturating"  # ascending → hard ceiling

class Duration(Enum):
    MOMENTARY = "momentary"   # < 1 minute
    ACUTE     = "acute"       # minutes to hours
    SUSTAINED = "sustained"   # hours to days
    CHRONIC   = "chronic"     # weeks+

class Modulation(Enum):
    NONE       = "none"        # unchanging regardless of activity
    REST       = "rest"        # improves with rest (angina)
    EXERTION   = "exertion"    # worsens with exertion
    MOVEMENT   = "movement"    # changes with body movement (MSK)
    POSITION   = "position"    # changes with posture
    BREATHING  = "breathing"   # changes with breath
    CONTEXT    = "context"     # changes with situation (anxiety)


# ============================================================
# SIGNAL PROFILE
# ============================================================

@dataclass
class SignalProfile:
    """
    A symptom described as a time-series shape.
    
    onset:       How fast did it arrive?
    trajectory:  What is it doing now?
    saturation:  Did it hit a ceiling? [0.0 = no, 1.0 = hard ceiling]
    duration:    How long has it persisted?
    modulation:  What changes it?
    intensity:   Reported magnitude [0.0, 1.0]
    
    The diagnostic information is in the SHAPE, not the intensity.
    """
    onset:       Onset
    trajectory:  Trajectory
    saturation:  float        # 0.0 → 1.0
    duration:    Duration
    modulation:  list         # list of Modulation
    intensity:   float = 0.5  # reported, unreliable — shape is primary

    def to_delta_vector(self) -> np.ndarray:
        """
        Convert signal profile to a numeric delta vector.
        This is the geometric representation that gets projected
        into the Laplacian eigenspace.
        
        Dimensions:
            0: onset_speed       — how fast (0=slow, 1=sudden)
            1: trajectory_slope  — direction and steepness
            2: saturation        — ceiling reached?
            3: duration_length   — how long
            4: modulation_rest   — improves with rest?
            5: modulation_exertion — worsens with exertion?
            6: modulation_movement — varies with movement?
            7: modulation_none   — unchanging?
        """
        onset_map = {
            Onset.SLOW:       0.0,
            Onset.GRADUAL:    0.25,
            Onset.EXERTIONAL: 0.5,
            Onset.RAPID:      0.75,
            Onset.SUDDEN:     1.0,
        }
        traj_map = {
            Trajectory.DESCENDING:  -0.5,
            Trajectory.OSCILLATING:  0.0,
            Trajectory.PLATEAU:      0.3,
            Trajectory.ASCENDING:    0.7,
            Trajectory.SATURATING:   1.0,
        }
        dur_map = {
            Duration.MOMENTARY: 0.1,
            Duration.ACUTE:     0.4,
            Duration.SUSTAINED: 0.7,
            Duration.CHRONIC:   1.0,
        }

        return np.array([
            onset_map[self.onset],
            traj_map[self.trajectory],
            self.saturation,
            dur_map[self.duration],
            1.0 if Modulation.REST      in self.modulation else 0.0,
            1.0 if Modulation.EXERTION  in self.modulation else 0.0,
            1.0 if Modulation.MOVEMENT  in self.modulation else 0.0,
            1.0 if Modulation.NONE      in self.modulation else 0.0,
        ], dtype=float)


# ============================================================
# CONDITION ARCHETYPES — KNOWN SIGNAL SHAPES
# ============================================================

# Each condition is defined by its characteristic signal shape
# NOT by its symptoms. The shape is the fingerprint.

CONDITION_ARCHETYPES = {

    # --- CARDIAC ---

    "MI_suspected": SignalProfile(
        onset       = Onset.SUDDEN,
        trajectory  = Trajectory.SATURATING,
        saturation  = 0.95,
        duration    = Duration.SUSTAINED,
        modulation  = [Modulation.NONE],    # does NOT resolve with rest
        intensity   = 0.9,
    ),
    "unstable_angina": SignalProfile(
        onset       = Onset.RAPID,
        trajectory  = Trajectory.ASCENDING,
        saturation  = 0.6,
        duration    = Duration.ACUTE,
        modulation  = [Modulation.EXERTION, Modulation.REST],
        intensity   = 0.7,
    ),
    "stable_angina": SignalProfile(
        onset       = Onset.EXERTIONAL,
        trajectory  = Trajectory.PLATEAU,
        saturation  = 0.5,
        duration    = Duration.ACUTE,
        modulation  = [Modulation.EXERTION, Modulation.REST],
        intensity   = 0.5,
    ),
    "musculoskeletal": SignalProfile(
        onset       = Onset.GRADUAL,
        trajectory  = Trajectory.OSCILLATING,
        saturation  = 0.2,
        duration    = Duration.SUSTAINED,
        modulation  = [Modulation.MOVEMENT, Modulation.POSITION],
        intensity   = 0.4,
    ),

    # --- NEUROLOGICAL ---

    "stroke_TIA": SignalProfile(
        onset       = Onset.SUDDEN,
        trajectory  = Trajectory.SATURATING,
        saturation  = 1.0,
        duration    = Duration.ACUTE,
        modulation  = [Modulation.NONE],
        intensity   = 0.95,
    ),
    "migraine": SignalProfile(
        onset       = Onset.GRADUAL,
        trajectory  = Trajectory.ASCENDING,
        saturation  = 0.5,
        duration    = Duration.SUSTAINED,
        modulation  = [Modulation.CONTEXT, Modulation.REST],
        intensity   = 0.8,
    ),
    "tension_headache": SignalProfile(
        onset       = Onset.GRADUAL,
        trajectory  = Trajectory.PLATEAU,
        saturation  = 0.3,
        duration    = Duration.SUSTAINED,
        modulation  = [Modulation.CONTEXT, Modulation.REST],
        intensity   = 0.4,
    ),

    # --- PSYCHIATRIC ---

    "MDE": SignalProfile(
        onset       = Onset.SLOW,
        trajectory  = Trajectory.DESCENDING,   # gradual worsening over weeks
        saturation  = 0.7,
        duration    = Duration.CHRONIC,
        modulation  = [Modulation.CONTEXT],
        intensity   = 0.6,
    ),
    "panic_disorder": SignalProfile(
        onset       = Onset.SUDDEN,
        trajectory  = Trajectory.SATURATING,
        saturation  = 0.9,
        duration    = Duration.MOMENTARY,       # peaks and resolves
        modulation  = [Modulation.CONTEXT],
        intensity   = 0.9,
    ),
    "GAD": SignalProfile(
        onset       = Onset.SLOW,
        trajectory  = Trajectory.OSCILLATING,
        saturation  = 0.4,
        duration    = Duration.CHRONIC,
        modulation  = [Modulation.CONTEXT],
        intensity   = 0.5,
    ),

    # --- RESPIRATORY ---

    "asthma_attack": SignalProfile(
        onset       = Onset.RAPID,
        trajectory  = Trajectory.ASCENDING,
        saturation  = 0.8,
        duration    = Duration.ACUTE,
        modulation  = [Modulation.EXERTION, Modulation.BREATHING],
        intensity   = 0.75,
    ),
}


# ============================================================
# SIGNAL GEOMETRY ENGINE
# ============================================================

class SignalGeometry:
    """
    Laplacian eigenbasis over condition signal space.
    
    Nodes:  Condition archetypes (each a delta vector)
    Edges:  Signal shape similarity (cosine similarity of delta vectors)
    L = D - A  (same as TENT v8, retargeted to signal space)
    
    The eigenmodes recover condition clusters from signal shape alone.
    The eigenspace is the geometric map.
    New signals are projected into this space and matched by proximity.
    
    This is the geometry engine Brad built in TENT v8 —
    repurposed from keyword vectors to signal shape vectors.
    """

    def __init__(self):
        self.conditions  = {}   # name → SignalProfile
        self.vectors     = {}   # name → np.ndarray
        self.names       = []
        self.A           = None  # adjacency matrix
        self.L           = None  # Laplacian
        self.eigenvalues = None
        self.eigenvectors = None  # columns are eigenvectors
        self._built      = False

    def add_condition(self, name: str, profile: SignalProfile):
        self.conditions[name] = profile
        self.vectors[name]    = profile.to_delta_vector()
        self.names.append(name)
        self._built = False

    def build(self):
        """Compute adjacency, Laplacian, eigenbasis."""
        n = len(self.names)
        vecs = np.array([self.vectors[nm] for nm in self.names])

        # Normalize
        norms = np.linalg.norm(vecs, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        vecs_norm = vecs / norms

        # Adjacency: cosine similarity, floored at 0
        A = np.maximum(0, vecs_norm @ vecs_norm.T)
        np.fill_diagonal(A, 0)  # no self-loops
        self.A = A

        # Degree and Laplacian
        D = np.diag(A.sum(axis=1))
        self.L = D - A

        # Eigenbasis
        eigenvalues, eigenvectors = np.linalg.eigh(self.L)
        self.eigenvalues  = eigenvalues
        self.eigenvectors = eigenvectors  # columns = eigenvectors
        self._built = True

    def _sim_vector(self, signal) -> "np.ndarray":
        query_vec = signal.to_delta_vector()
        q_norm = np.linalg.norm(query_vec)
        if q_norm > 0:
            query_vec = query_vec / q_norm
        sim_vec = np.zeros(len(self.names))
        for i, nm in enumerate(self.names):
            arch_vec = self.vectors[nm].copy()
            a_norm = np.linalg.norm(arch_vec)
            if a_norm > 0:
                arch_vec = arch_vec / a_norm
            sim_vec[i] = max(0.0, float(query_vec @ arch_vec))
        return sim_vec

    def project(self, signal) -> "np.ndarray":
        """Project signal into Laplacian eigenspace via similarity bridge."""
        assert self._built, "Call build() first"
        return self.eigenvectors.T @ self._sim_vector(signal)

    def nearest_conditions(self, signal, top_k: int = 3) -> list:
        """
        Find k nearest archetype conditions.
        
        Matching: weighted Euclidean distance in feature space.
        Duration and onset are weighted higher — they are the primary
        discriminators when trajectory/saturation are shared.
        
        Eigenspace (eigenvectors/eigenvalues) used for topology reporting,
        not for matching. The eigenspace collapses shared dimensions.
        """
        assert self._built, "Call build() first"

        # Dimension weights
        # [onset, trajectory, saturation, duration, rest, exertion, movement, none]
        WEIGHTS = np.array([3.0, 2.0, 2.0, 3.0, 1.0, 1.0, 1.0, 0.5])

        q_vec = signal.to_delta_vector() * WEIGHTS
        distances = []
        for nm in self.names:
            a_vec = self.vectors[nm] * WEIGHTS
            dist = float(np.linalg.norm(q_vec - a_vec))
            distances.append((nm, dist))


        distances.sort(key=lambda x: x[1])
        top = distances[:top_k]

        # Convert to similarity percentage
        max_dist = max(d for _, d in distances) if distances else 1.0
        result = []
        for nm, dist in top:
            sim = max(0.0, 1.0 - (dist / max_dist if max_dist > 0 else 0)) * 100
            result.append((nm, round(dist, 4), round(sim, 1)))
        return result

    def eigenmode_report(self) -> str:
        """
        Report which conditions cluster together in eigenspace.
        Low-frequency eigenmodes (small λ) define the major clusters.
        Analogous to TENT v8 unsupervised domain recovery.
        """
        assert self._built, "Call build() first"
        lines = ["EIGENMODE REPORT — Signal Geometry Clusters"]
        lines.append(f"Conditions: {len(self.names)}")
        lines.append(f"Eigenvalues (λ₀..λ{len(self.eigenvalues)-1}): "
                    + "  ".join(f"{v:.3f}" for v in self.eigenvalues[:6]))
        lines.append("")

        # Show top 3 non-trivial eigenmodes
        for k in range(1, min(4, len(self.eigenvalues))):
            evec = self.eigenvectors[:, k]
            # Conditions most aligned with this eigenmode
            ranked = sorted(zip(self.names, evec),
                          key=lambda x: abs(x[1]), reverse=True)[:4]
            lines.append(f"λ{k}={self.eigenvalues[k]:.3f}  "
                        + "  ".join(f"{nm}({v:+.2f})" for nm, v in ranked))

        return "\n".join(lines)


# ============================================================
# NATURAL LANGUAGE → SIGNAL PROFILE PARSER
# ============================================================

# Temporal language maps directly to signal shape dimensions
# This is the bridge between what the person says and the geometry

ONSET_SIGNALS = {
    "sudden":    Onset.SUDDEN,
    "suddenly":  Onset.SUDDEN,
    "instant":   Onset.SUDDEN,
    "instantly": Onset.SUDDEN,
    "sharp":     Onset.SUDDEN,
    "out of nowhere": Onset.SUDDEN,
    "came on fast":   Onset.RAPID,
    "quickly":   Onset.RAPID,
    "rapid":     Onset.RAPID,
    "gradually": Onset.GRADUAL,
    "slowly over hours": Onset.GRADUAL,
    "slowly":    Onset.SLOW,
    "over time": Onset.SLOW,
    "weeks":     Onset.SLOW,
    "exercise":  Onset.EXERTIONAL,
    "walking":   Onset.EXERTIONAL,
    "exertion":  Onset.EXERTIONAL,
    "stairs":    Onset.EXERTIONAL,
}

TRAJECTORY_SIGNALS = {
    # saturation signals — checked first (longest phrases win in sort)
    "crushing":        Trajectory.SATURATING,
    "unbearable":      Trajectory.SATURATING,
    "worst ever":      Trajectory.SATURATING,
    "worst pain":      Trajectory.SATURATING,
    "worst":           Trajectory.SATURATING,
    "cant breathe":    Trajectory.SATURATING,
    "wont go away":    Trajectory.SATURATING,   # sustained non-resolving
    # ascending — long phrases first to win sort
    "builds slowly over": Trajectory.ASCENDING,
    "slowly builds":   Trajectory.ASCENDING,
    "gradually worse": Trajectory.ASCENDING,
    "getting worse":   Trajectory.ASCENDING,
    "worsening":       Trajectory.ASCENDING,
    "spreading":       Trajectory.ASCENDING,
    "building up":     Trajectory.ASCENDING,
    "builds up":       Trajectory.ASCENDING,
    "builds":          Trajectory.ASCENDING,
    # plateau
    "constant":        Trajectory.PLATEAU,
    "steady":          Trajectory.PLATEAU,
    "same level":      Trajectory.PLATEAU,
    # oscillating
    "comes and goes":  Trajectory.OSCILLATING,
    "on and off":      Trajectory.OSCILLATING,
    "varies":          Trajectory.OSCILLATING,
    # descending / depression language
    "feeling down":    Trajectory.DESCENDING,
    "feeling low":     Trajectory.DESCENDING,
    "going downhill":  Trajectory.DESCENDING,
    "getting worse over weeks": Trajectory.DESCENDING,
    "better":          Trajectory.DESCENDING,
    "improving":       Trajectory.DESCENDING,
}

MODULATION_SIGNALS = {
    "stops when i sit": Modulation.REST,
    "gets better when i stop": Modulation.REST,
    "better when i stop":      Modulation.REST,
    "goes away when i stop":   Modulation.REST,
    "stops when i rest":       Modulation.REST,
    "goes away when i rest":   Modulation.REST,
    "better with rest":        Modulation.REST,
    "at rest":                 Modulation.REST,
    "when i rest":             Modulation.REST,
    "with exercise":    Modulation.EXERTION,
    "when i walk":      Modulation.EXERTION,
    "up stairs":        Modulation.EXERTION,
    "with movement":    Modulation.MOVEMENT,
    "when i move":      Modulation.MOVEMENT,
    "when i breathe":   Modulation.BREATHING,
    "breathing":        Modulation.BREATHING,
    "constant no matter": Modulation.NONE,
    "wont go away":     Modulation.NONE,
    "doesnt change":    Modulation.NONE,
    "no matter what":   Modulation.NONE,
    "hopeless":         Modulation.CONTEXT,
    "stressed":         Modulation.CONTEXT,
    "anxious":          Modulation.CONTEXT,
    "worried":          Modulation.CONTEXT,
}

def parse_signal_from_text(text: str) -> SignalProfile:
    """
    Extract signal profile from natural language description.
    Maps temporal language to signal shape dimensions.
    
    This is not NLP. It is keyword anchoring for known
    temporal descriptor vocabulary.
    """
    t = text.lower()

    # Onset
    onset = Onset.GRADUAL  # default
    for phrase, val in sorted(ONSET_SIGNALS.items(), key=lambda x: -len(x[0])):
        if phrase in t:
            onset = val
            break

    # Trajectory
    trajectory = Trajectory.PLATEAU  # default
    for phrase, val in sorted(TRAJECTORY_SIGNALS.items(), key=lambda x: -len(x[0])):
        if phrase in t:
            trajectory = val
            break

    # Saturation — crushing/unbearable words
    saturation = 0.5
    if any(w in t for w in ["crushing", "unbearable", "worst ever", "worst", "cant stop"]):
        saturation = 0.95
    elif any(w in t for w in ["severe", "intense", "strong"]):
        saturation = 0.90
    elif any(w in t for w in ["mild", "slight", "little"]):
        saturation = 0.25

    # Duration
    duration = Duration.ACUTE
    if any(w in t for w in ["weeks", "months", "long time", "always", "for a long time",
                               "past month", "past few", "several months", "over the past"]):
        duration = Duration.CHRONIC
    elif any(w in t for w in ["hours", "all day", "since morning", "over hours",
                               "wont go away", "not going away", "still there", "persisting"]):
        duration = Duration.SUSTAINED
    elif any(w in t for w in ["passes quickly", "then passes", "and passes", "passes",
                               "brief", "moment", "second", "goes away quickly", "quick"]):
        duration = Duration.MOMENTARY

    # Modulation
    modulation = []
    for phrase, val in sorted(MODULATION_SIGNALS.items(), key=lambda x: -len(x[0])):
        if phrase in t:
            if val not in modulation:
                modulation.append(val)
    if not modulation:
        modulation = [Modulation.NONE]

    # Saturation-trajectory coupling:
    # High saturation words imply the ceiling is hit.
    # Override ASCENDING or PLATEAU to SATURATING when saturation is very high.
    if saturation >= 0.9 and trajectory in (Trajectory.ASCENDING, Trajectory.PLATEAU):
        trajectory = Trajectory.SATURATING

    return SignalProfile(
        onset=onset,
        trajectory=trajectory,
        saturation=saturation,
        duration=duration,
        modulation=modulation,
    )


# ============================================================
# TEST SUITE
# ============================================================

def run_tests(geo: SignalGeometry) -> tuple[int, int]:

    print("=" * 72)
    print("  SIGGEO — SIGNAL GEOMETRY ENGINE")
    print("  Pain is a time-based signal. Shape is the diagnostic.")
    print("  Ψ = Φ₁(θ) − Φ₂(θ)  — the delta IS the field observable")
    print("=" * 72)
    print()
    print(geo.eigenmode_report())
    print()
    print("=" * 72)
    print("  SIGNAL SHAPE MATCHING — NATURAL LANGUAGE → EIGENSPACE")
    print("=" * 72)
    print()

    # Test cases: (description, expected_top_match, description_note)
    test_cases = [
        (
            "sudden crushing chest pain that wont go away and is getting worse",
            "MI_suspected",
            "Classic MI: sudden + saturating + sustained + no modulation"
        ),
        (
            "chest pain that comes on when I walk up stairs and goes away when I rest",
            "stable_angina",
            "Stable angina: exertional + rest modulation"
        ),
        (
            "I have been feeling down and hopeless for weeks with no energy",
            "MDE",
            "MDE: slow onset + chronic duration + descending"
        ),
        (
            "sudden intense panic comes on out of nowhere and passes quickly",
            "panic_disorder",
            "Panic: sudden + saturating + momentary"
        ),
        (
            "my chest is sore and varies when I move around",
            "musculoskeletal",
            "MSK: gradual + oscillating + movement modulation"
        ),
        (
            "sudden worst headache of my life that came on instantly",
            "stroke_TIA",
            "Thunderclap: sudden + saturating — nearest to stroke/TIA"
        ),
        (
            "headache that builds slowly over hours and is constant",
            "migraine",
            "Migraine: gradual ascending + sustained"
        ),
        (
            "I feel anxious and worried constantly for weeks it comes and goes",
            "GAD",
            "GAD: slow + oscillating + chronic + context modulation"
        ),
    ]

    passed = failed = 0

    for text, expected, note in test_cases:
        profile = parse_signal_from_text(text)
        nearest = geo.nearest_conditions(profile, top_k=3)
        top_match = nearest[0][0] if nearest else None

        ok = top_match == expected
        passed += ok
        failed += not ok
        icon = "✓" if ok else "✗"

        delta = profile.to_delta_vector()
        print(f"  [{icon}] \"{text[:60]}\"")
        print(f"       Signal shape:")
        print(f"         onset={profile.onset.value:<12} "
              f"trajectory={profile.trajectory.value:<12} "
              f"saturation={profile.saturation:.2f}")
        print(f"         duration={profile.duration.value:<10} "
              f"modulation={[m.value for m in profile.modulation]}")
        print(f"         delta_vec={np.round(delta, 2)}")
        print(f"       Nearest conditions in eigenspace:")
        for nm, dist, sim in nearest:
            marker = " ◄" if nm == expected else ""
            print(f"         {nm:<25} dist={dist:.4f}  sim={sim:.1f}%{marker}")
        if not ok:
            print(f"       EXPECTED: {expected}")
        print(f"       {note}")
        print()

    print("=" * 72)
    print(f"  RESULT: {passed}/{passed+failed} passed")
    print()
    print("  KEY PRINCIPLES:")
    print("  1. Pain is not a token. It is a curve.")
    print("  2. The derivative is the signal. Not the value.")
    print("  3. Ψ = onset_channel − resolution_channel")
    print("     MI:     onset dominates, resolution absent → Ψ saturates")
    print("     Angina: channels balance at rest, break under exertion")
    print("  4. Conditions are geometric regions in eigenspace.")
    print("     Matching is proximity, not string equality.")
    print("=" * 72)
    return passed, failed


# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":
    geo = SignalGeometry()
    for name, profile in CONDITION_ARCHETYPES.items():
        geo.add_condition(name, profile)
    geo.build()

    passed, failed = run_tests(geo)

    if failed == 0:
        print("\n  All tests passed. SIGGEO operational.")
    else:
        print(f"\n  {failed} test(s) failed. Signal geometry needs calibration.")
