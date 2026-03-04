# Sovereign Stack — Complete Build
## Brad Wallace / tensorrent  |  Sessions 1–22

One zip. Every piece. Nothing stochastic on the charge path.

---

## Directory Layout

```
sovereign_stack/
├── rust_core/          # Trinity Core cdylib — integer BRA kernel + neuromorphic heuristics
├── arc/                # ARC-AGI solver — 13 modules (8% → 25-35% target)
├── tent_seggci/        # TENT v9/v10 + SEGGCI pipeline
├── hermes_vexel_flow/  # Hermes memory + Vexel scroll + Claude Flow
├── session_daw/        # DAW-model persistent memory (stems/mixdown)
├── deploy/             # Docker + requirements + OpenClaw config
├── docs/               # SOUL.md  CLAUDE.md  README.md
├── papers/             # All LaTeX/PDF/docx publications
├── tent_tests.py       # TENT full test suite
└── test_integration.py # Cross-stack integration tests
```

---

## rust_core/  (11 files)

| File | Role |
|---|---|
| trinity_core.rs | Unified cdylib: BRA + Vexel + Council + Sovereignty + Family |
| arc_heuristics.rs | Neuromorphic integer kernel: receptive-field rules, components, delta, period (804 lines) |
| vexel.rs | Vexel v1 — scroll/Merkle session engine |
| vexel2.rs | Vexel v2 — blank-seed octree Merkle identity |
| council.rs | Three-council biometric auth |
| sovereignty.rs | Rights, bonds, handoff protocol |
| family.rs | Mesh sharing, severance, post-mortem state |
| lib.rs | Unified cdylib entry point |
| main.rs | CLI harness |
| Cargo.toml | Workspace manifest |
| libarc_heuristics.so | Compiled neuromorphic kernel (Linux x86-64) |

**Compile:**
```bash
rustc --edition 2021 --crate-type cdylib -O rust_core/arc_heuristics.rs -o libarc_heuristics.so
rustc --edition 2021 --crate-type cdylib -O rust_core/trinity_core.rs -o libtrinity.so
```

---

## arc/  (13 files)

| File | Role |
|---|---|
| arc_types.py | Grid types, ARCTask, Pair |
| arc_bra.py | BRA integer eigenvalue charge path |
| arc_neuro.py | Neuromorphic bridge: RC8 gate, Γ_m, RC6 margin, neuro_solve_v3 |
| arc_programs.py | 60+ hand-crafted deterministic patterns |
| arc_solver.py | Main solve pipeline |
| arc_dsl_ext.py | Extended DSL: 60+ advanced primitives |
| arc_abstraction.py | Object-centric abstraction layer |
| arc_augment.py | D4+color augmentation engine |
| arc_search.py | Brute-force search with voting |
| arc_renderer.py | Grid renderer |
| arc_memory.py | Cross-task pattern library |
| arc_hermes.py | Hermes memory bridge |
| arc_eval.py | Evaluation harness |

**arc_neuro.py key API (Sessions 21–22):**
```python
neuro_solve_v3(task)   # RC8 gate → local_3x3 → local_5x5 → delta → period
rc8_epistemic_check(task)  # sigma_c ~ C·A·lam^alpha·N^(-beta/D2)
gamma_m(rules)         # eigenvector 4th moment — collapse fragility
rc6_stability_margin(rules)  # B=0 collision / B=1 near-miss / B=2 certified
rule_diagnostics(rules)  # full health report
```

**Architectural invariants:**
- No float on charge path (EigenCharge: u64 + i64 + i64)
- Ulam spiral = storage address only (vexel/scroll), NOT inference
- RC8: abstain if σ_obs ≥ σ_c
- Γ_m: high fourth moment → fragile rule table → collapse risk

---

## tent_seggci/  (10 files)

| File | Role |
|---|---|
| tent_v9_production.py | TENT v9: BRA resonance + density gates |
| tent_v10_pipeline.py | TENT v10: full cinema pipeline |
| tent_v10_vixel.py | Vixel field grid integration |
| rc13_stakes.py | RC13: consequence-aware stakes routing |
| rc14_escalation.py | RC14: escalation tiers |
| lexenv.py | LEXENV: contextual symbol binding |
| siggeo.py | SIGGEO: signal geometry engine |
| seed.py | Seed growth model: individual depth compounding |
| reasoning_engine.py | Lazy hypothesis derivation |
| sovereign_shell.py | Unified shell entry point |

---

## hermes_vexel_flow/  (7 files)

| File | Role |
|---|---|
| hermes_hooks.py | Hermes NousResearch integration |
| hermes_vexel.py | Vexel ↔ Hermes memory bridge |
| hermes_vqa.py | VQA multi-backend (Claude/Ollama/BLIP2) |
| hermes_config.yaml | Hermes configuration |
| vexel_flow.py | Claude Flow ↔ Vexel integration |
| flow_agent.py | Autonomous agent with scroll memory |
| flow_hooks.py | Flow lifecycle hooks |

---

## session_daw/  (1 file)

**session_daw.py** — DAW-model persistent memory architecture.
Every session = one stem in a channel. VexelEvents are 32-byte MIDI-encoded scroll entries.
Mixdown renders BRA-fingerprinted stems. Cross-session queries via resonance bus.
Voicing modes: spatial / harmonic / rhythmic / score / full_mix.
Ulam cylinder = storage address for scroll positions. Background sync to ARC pattern library.

---

## Phase Boundary Table (from Unified Stability paper)

All layers share one structure: two competing scalings determine a phase boundary.

| Layer | First Scale | Second Scale |
|---|---|---|
| RC6 stability | eigenvalue | quadratic root |
| RC7 perturbation | perturbation magnitude | stability margin B |
| RC8 detectability | Lyapunov divergence | geometric sampling density |
| Load redistribution | convex cost | amplitude concentration |
| Mode collapse | nonlinear freq shift | spectral gap |

**Universal collapse law:** β_c · a_m² = (8ω_m / 3Γ_m) · Δω_m

---

## Quick Start

```bash
pip install -r deploy/sovereign_requirements.txt
rustc --edition 2021 --crate-type cdylib -O rust_core/arc_heuristics.rs -o libarc_heuristics.so
python3 tent_tests.py
python3 test_integration.py
python3 arc/arc_eval.py
docker-compose -f deploy/docker-compose.yml up
```

---

*SIP License v1.1 — Brad Wallace / tensorrent — see papers/SEGGCI_Paper.docx*
