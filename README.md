# Sovereign Stack — Complete Build

**Brad Wallace / tensorrent** — Sessions 1–22
One zip. Every piece. Nothing stochastic on the charge path.

---

## Architecture

| Layer | Directory | Purpose |
|-------|-----------|---------|
| **Rust Core** | `rust_core/` | Trinity Core cdylib — integer BRA kernel + neuromorphic heuristics |
| **ARC Solver** | `arc/` | ARC-AGI solver — 21 modules, deterministic constraint layer |
| **TENT + SEGGCI** | `tent_seggci/` | TENT v9/v10 engines + SEGGCI cognitive pipeline |
| **Hermes + Vexel** | `hermes_vexel_flow/` | Memory bridge, VQA, Claude Flow integration |
| **Session DAW** | `session_daw/` | DAW-model persistent memory (stems/mixdown) |
| **Papers** | `papers/` | All LaTeX/PDF/docx publications |
| **Deploy** | `deploy/` | Docker + requirements + OpenClaw config |
| **Validation** | `stress_test_*.py` | Collapse law, anti-phase bound, G_m factor tests |

---

## Key Components

### rust_core/ (11 files)

| File | Role |
|------|------|
| `trinity_core.rs` | Unified cdylib: BRA + Vexel + Council + Sovereignty + Family |
| `arc_heuristics.rs` | Neuromorphic integer kernel (804 lines) |
| `vexel.rs` / `vexel2.rs` | Scroll/Merkle session engine (v1 + v2) |
| `council.rs` | Three-council biometric auth |
| `sovereignty.rs` | Rights, bonds, handoff protocol |
| `family.rs` | Mesh sharing, severance, post-mortem state |

```bash
rustc --edition 2021 --crate-type cdylib -O rust_core/trinity_core.rs -o libtrinity.so
```

### arc/ (21 modules)

Core API (`arc_neuro.py`):
```python
neuro_solve_v3(task)          # RC8 gate → local_3x3 → local_5x5 → delta → period
rc8_epistemic_check(task)     # σ_c ~ A·√(λΔt)·N^(-1/D₂)
gamma_m(rules)                # Eigenvector 4th moment — collapse fragility
rc6_stability_margin(rules)   # B=0 collision / B=1 near-miss / B=2 certified
```

**Invariants:** No float on charge path (EigenCharge: u64 + i64 + i64). RC8 abstains if σ_obs ≥ σ_c.

### tent_seggci/ (10 files)

TENT v9/v10 engines, RC13/RC14 gates, LEXENV, SIGGEO, seed growth model.

### stress_test_*.py (3 scripts)

| Script | Tests | Result |
|--------|-------|--------|
| `stress_test_gamma_overlap.py` | G_m ≈ 1/3 across 5 topologies | ✅ |
| `stress_test_antiphase_bound.py` | Anti-phase η bound (7 regimes) | ✅ |
| `stress_test_collapse_law.py` | Collapse law (8 topologies, 5 tests) | ✅ |

---

## Phase Boundary Table

All layers share one structure: **two competing scalings determine a phase boundary**.

| Layer | First Scale | Second Scale |
|-------|-------------|--------------|
| RC6 stability | eigenvalue | forbidden set Z |
| RC7 perturbation | ‖ΔA‖₂ | stability margin B |
| RC8 detectability | Lyapunov divergence | sampling density |
| Load redistribution | convex cost | amplitude concentration |
| Mode collapse | nonlinear freq shift | spectral gap |

**Universal collapse law:** $\beta_c \cdot a_m^2 = \frac{8\omega_m}{3\,\mathcal{G}_m\,\Gamma_m} \cdot \Delta\omega_m$

---

## Quick Start

```bash
pip install -r deploy/sovereign_requirements.txt
rustc --edition 2021 --crate-type cdylib -O rust_core/arc_heuristics.rs -o libarc_heuristics.so
python3 tent_tests.py
python3 test_integration.py
python3 arc/arc_eval.py
```

---

## Related Repositories

- [Theory Paper](https://github.com/tensorrent/Unified-Stability-Epistemic-Limits-Nonlinear-mode-collaps-in-Coupled-Systems) — Unified Stability paper + stress tests
- [RC Stack](https://github.com/tensorrent/RC1-Deterministic-Constraint-Projection-Layer) — Constraint gate architecture
- [TENT](https://github.com/tensorrent/tent-io) — Tensor engine

*SIP License v1.1 — Brad Wallace / tensorrent*
