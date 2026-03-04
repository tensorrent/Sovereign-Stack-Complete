from __future__ import annotations
import ctypes, os
from pathlib import Path
from typing import Optional, List, Tuple
Grid = list[list[int]]

class SynapticRule(ctypes.Structure):
    _pack_ = 1
    _fields_ = [
        ("trigger_hash",  ctypes.c_uint64),
        ("trigger_trace", ctypes.c_int64),
        ("trigger_det",   ctypes.c_int64),
        ("output_color",  ctypes.c_uint8),
        ("confidence",    ctypes.c_uint8),
        ("_pad",          ctypes.c_uint8 * 6),
    ]
assert ctypes.sizeof(SynapticRule) == 32

_LIB_PATHS = [
    "/tmp/libarc_heuristics.so",
    "/home/claude/libarc_heuristics.so",
    "/mnt/user-data/outputs/libarc_heuristics.so",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "libarc_heuristics.so"),
]

def _load():
    for p in _LIB_PATHS:
        if Path(p).exists():
            lib = ctypes.CDLL(p); _bind(lib); return lib
    raise FileNotFoundError("libarc_heuristics.so not found")

def _bind(lib):
    u8p=ctypes.POINTER(ctypes.c_uint8)
    u64p=ctypes.POINTER(ctypes.c_uint64)
    i64p=ctypes.POINTER(ctypes.c_int64)
    RP=ctypes.POINTER(SynapticRule)
    sz=ctypes.c_size_t
    for name,rt,at in [
        ("arc_neuro_verify",           ctypes.c_int32, []),
        ("arc_neuro_extract_fields",   sz, [u8p,sz,sz,u64p,i64p,i64p]),
        ("arc_neuro_context_fields",   sz, [u8p,sz,sz,u64p,i64p,i64p]),
        ("arc_neuro_learn_rules",      sz, [u8p,u8p,sz,sz,ctypes.c_int32,RP,sz]),
        ("arc_neuro_merge_rules",      sz, [RP,sz,RP,sz,RP,sz]),
        ("arc_neuro_apply_rules",      sz, [u8p,sz,sz,RP,sz,u8p]),
        ("arc_neuro_apply_rules_iter", sz, [u8p,sz,sz,RP,sz,u8p,sz]),
        ("arc_neuro_components",       sz, [u8p,sz,sz,u8p]),
        ("arc_neuro_comp_charges",     sz, [u8p,u8p,sz,sz,sz,u64p,i64p,i64p]),
        ("arc_neuro_delta_charge",     ctypes.c_int32, [u8p,u8p,sz,sz,u64p,i64p,i64p]),
        ("arc_neuro_spatial_graph",    ctypes.c_int32, [u8p,sz,sz,sz,u64p,i64p,i64p]),
        ("arc_neuro_pattern_period",   ctypes.c_int32, [u8p,sz,sz,u8p,u8p]),
    ]:
        getattr(lib,name).restype=rt
        getattr(lib,name).argtypes=at

_lib = None
def get_lib():
    global _lib
    if _lib is None: _lib = _load()
    return _lib

def _to_c(grid):
    h,w = len(grid), len(grid[0]) if grid else 0
    flat = (ctypes.c_uint8*(w*h))()
    for r in range(h):
        for c in range(w): flat[r*w+c] = grid[r][c]&0xFF
    return flat, w, h

def _from_c(flat,w,h):
    return [[flat[r*w+c] for c in range(w)] for r in range(h)]

def verify(): return get_lib().arc_neuro_verify()==1

def learn_rules(in_grid,out_grid,wide=False):
    lib=get_lib(); ig,w,h=_to_c(in_grid); og,_,_=_to_c(out_grid)
    cap=w*h+1; buf=(SynapticRule*cap)()
    n=lib.arc_neuro_learn_rules(ig,og,w,h,int(wide),buf,cap)
    return list(buf[:n])

def merge_rules(ra,rb):
    if not ra or not rb: return []
    lib=get_lib()
    aa=(SynapticRule*len(ra))(*ra); bb=(SynapticRule*len(rb))(*rb)
    cap=min(len(ra),len(rb))+1; buf=(SynapticRule*cap)()
    n=lib.arc_neuro_merge_rules(aa,len(ra),bb,len(rb),buf,cap)
    return list(buf[:n])

def learn_from_pairs(pairs,wide=False):
    if not pairs: return []
    rules=learn_rules(pairs[0][0],pairs[0][1],wide=wide)
    for inp,out in pairs[1:]:
        if not rules: break
        rules=merge_rules(rules,learn_rules(inp,out,wide=wide))
    return rules

def apply_rules(grid,rules,iterative=False,max_iter=5):
    if not rules: return [row[:] for row in grid]
    lib=get_lib(); ig,w,h=_to_c(grid); arr=(SynapticRule*len(rules))(*rules)
    out=(ctypes.c_uint8*(w*h))()
    if iterative: lib.arc_neuro_apply_rules_iter(ig,w,h,arr,len(rules),out,max_iter)
    else: lib.arc_neuro_apply_rules(ig,w,h,arr,len(rules),out)
    return _from_c(out,w,h)

def components(grid):
    lib=get_lib(); g,w,h=_to_c(grid); ci=(ctypes.c_uint8*(w*h))()
    nc=lib.arc_neuro_components(g,w,h,ci); return list(ci[:w*h]),nc

def component_charges(grid):
    lib=get_lib(); g,w,h=_to_c(grid); ci_flat,nc=components(grid)
    if nc==0: return []
    ci=(ctypes.c_uint8*(w*h))(*ci_flat)
    hh=(ctypes.c_uint64*nc)(); tt=(ctypes.c_int64*nc)(); dd=(ctypes.c_int64*nc)()
    lib.arc_neuro_comp_charges(g,ci,w,h,nc,hh,tt,dd)
    return [(hh[i],tt[i],dd[i]) for i in range(nc)]

def delta_charge(in_grid,out_grid):
    lib=get_lib(); ig,w,h=_to_c(in_grid); og,_,_=_to_c(out_grid)
    h_=ctypes.c_uint64(0); t_=ctypes.c_int64(0); d_=ctypes.c_int64(0)
    lib.arc_neuro_delta_charge(ig,og,w,h,ctypes.byref(h_),ctypes.byref(t_),ctypes.byref(d_))
    return (h_.value,t_.value,d_.value)

def extract_fields(grid,wide=False):
    lib=get_lib(); g,w,h=_to_c(grid); n=w*h
    hh=(ctypes.c_uint64*n)(); tt=(ctypes.c_int64*n)(); dd=(ctypes.c_int64*n)()
    fn=lib.arc_neuro_context_fields if wide else lib.arc_neuro_extract_fields
    fn(g,w,h,hh,tt,dd); return [(hh[i],tt[i],dd[i]) for i in range(n)]

def pattern_period(grid):
    lib=get_lib(); g,w,h=_to_c(grid)
    hp=ctypes.c_uint8(0); vp=ctypes.c_uint8(0)
    lib.arc_neuro_pattern_period(g,w,h,ctypes.byref(hp),ctypes.byref(vp))
    return (hp.value,vp.value)

def spatial_graph_charge(grid):
    lib=get_lib(); g,w,h=_to_c(grid); ci_flat,nc=components(grid)
    if nc==0: return (0,0,0)
    ci=(ctypes.c_uint8*(w*h))(*ci_flat)
    h_=ctypes.c_uint64(0); t_=ctypes.c_int64(0); d_=ctypes.c_int64(0)
    lib.arc_neuro_spatial_graph(ci,w,h,nc,ctypes.byref(h_),ctypes.byref(t_),ctypes.byref(d_))
    return (h_.value,t_.value,d_.value)

def solve_by_local_rules(task,wide=False):
    pairs=[(p.input,p.output) for p in task.train if p.output is not None]
    if not pairs: return None
    rules=learn_from_pairs(pairs,wide=wide)
    if not rules: return None
    for inp,out in pairs:
        if apply_rules(inp,rules)!=out:
            if apply_rules(inp,rules,iterative=True)!=out: return None
    return apply_rules(task.test[0].input,rules) if task.test else None

def solve_by_delta(task):
    pairs=[(p.input,p.output) for p in task.train if p.output is not None]
    if len(pairs)<2: return None
    h0,w0=len(pairs[0][0]),len(pairs[0][0][0])
    if not all(len(p[0])==h0 and len(p[0][0])==w0 for p in pairs): return None
    charges=[delta_charge(i,o) for i,o in pairs]
    if len(set(charges))!=1: return None
    inp0,out0=pairs[0]
    test_inp=task.test[0].input if task.test else None
    if test_inp is None or len(test_inp)!=h0 or len(test_inp[0])!=w0: return None
    result=[row[:] for row in test_inp]
    for r in range(h0):
        for c in range(w0):
            if inp0[r][c]!=out0[r][c]: result[r][c]=out0[r][c]
    return result

def solve_by_period(task):
    pairs=[(p.input,p.output) for p in task.train if p.output is not None]
    if not pairs: return None
    test_inp=task.test[0].input if task.test else None
    if test_inp is None: return None
    for inp,out in pairs:
        hp,vp=pattern_period(inp)
        if hp==0 and vp==0: return None
        if len(out)<=len(inp) and len(out[0])<=len(inp[0]): return None
    inp0,out0=pairs[0]
    ih,iw=len(inp0),len(inp0[0]); oh,ow=len(out0),len(out0[0])
    th,tw=len(test_inp),len(test_inp[0])
    th2=th*oh//ih if ih>0 else oh; tw2=tw*ow//iw if iw>0 else ow
    return [[test_inp[r%th][c%tw] for c in range(tw2)] for r in range(th2)]

def neuro_solve(task):
    r={"prediction":None,"tier":None,"n_rules":0,"confidence":0}
    for wide,tier in [(False,"local_3x3"),(True,"local_5x5")]:
        try:
            pred=solve_by_local_rules(task,wide=wide)
            if pred is not None:
                pairs=[(p.input,p.output) for p in task.train if p.output]
                rules=learn_from_pairs(pairs,wide=wide)
                r.update({"prediction":pred,"tier":tier,"n_rules":len(rules),"confidence":2})
                return r
        except Exception: pass
    for fn,tier in [(solve_by_delta,"delta"),(solve_by_period,"period")]:
        try:
            pred=fn(task)
            if pred is not None:
                r.update({"prediction":pred,"tier":tier,"n_rules":1,"confidence":1})
                return r
        except Exception: pass
    return r

def learn_from_pairs_union(pairs, wide=False):
    counts = {}
    for inp,out in pairs:
        for rule in learn_rules(inp, out, wide=wide):
            key = (rule.trigger_hash, rule.trigger_trace, rule.trigger_det)
            if key not in counts:
                counts[key] = rule.output_color
            elif counts[key] != rule.output_color:
                counts[key] = None
    result = []
    for (h,tr,dt),color in counts.items():
        if color is None: continue
        r = SynapticRule()
        r.trigger_hash=h; r.trigger_trace=tr; r.trigger_det=dt
        r.output_color=color; r.confidence=1
        result.append(r)
    return result

def solve_by_local_rules_v2(task, wide=False):
    pairs=[(p.input,p.output) for p in task.train if p.output is not None]
    if not pairs: return None
    rules=learn_from_pairs_union(pairs, wide=wide)
    if not rules: return None
    for inp,out in pairs:
        if apply_rules(inp,rules)!=out:
            if apply_rules(inp,rules,iterative=True)!=out: return None
    return apply_rules(task.test[0].input,rules) if task.test else None

def _is_tiling_of(small, large):
    sh,sw=len(small),len(small[0])
    lh,lw=len(large),len(large[0])
    if lh<sh or lw<sw: return False
    for r in range(lh):
        for c in range(lw):
            if large[r][c]!=small[r%sh][c%sw]: return False
    return True

def solve_by_period_v2(task):
    pairs=[(p.input,p.output) for p in task.train if p.output is not None]
    if not pairs: return None
    test_inp=task.test[0].input if task.test else None
    if test_inp is None: return None
    for inp,out in pairs:
        if not _is_tiling_of(inp,out): return None
    out0=pairs[0][1]
    oh,ow=len(out0),len(out0[0])
    th,tw=len(test_inp),len(test_inp[0])
    if th==0 or tw==0: return None
    return [[test_inp[r%th][c%tw] for c in range(ow)] for r in range(oh)]

def neuro_solve_v2(task):
    r={"prediction":None,"tier":None,"n_rules":0,"confidence":0}
    for wide,tier in [(False,"local_3x3"),(True,"local_5x5")]:
        try:
            pred=solve_by_local_rules_v2(task,wide=wide)
            if pred is not None:
                pairs=[(p.input,p.output) for p in task.train if p.output]
                rules=learn_from_pairs_union(pairs,wide=wide)
                r.update({"prediction":pred,"tier":tier,"n_rules":len(rules),"confidence":2})
                return r
        except Exception: pass
    for fn,tier in [(solve_by_delta,"delta"),(solve_by_period_v2,"period")]:
        try:
            pred=fn(task)
            if pred is not None:
                r.update({"prediction":pred,"tier":tier,"n_rules":1,"confidence":1})
                return r
        except Exception: pass
    return r

import math

# ── RC8: Epistemic Horizon Gate ──────────────────────────────────────────────
def rc8_epistemic_check(task, C=1.05, alpha=0.46, beta_exp=1.07):
    """
    RC8: sigma_c ~ C * A * lam^alpha * N^(-beta/D2)
    ARC mapping:
      N     = training pair count
      A     = max color value in training inputs (amplitude scale)
      lam   = BRA trace std / mean (Lyapunov proxy)
      D2    = log(unique_neighborhoods) / log(total_cells) (dim proxy)
      sigma = observed conflict rate in union rule table
    Returns dict: can_infer, sigma_c, sigma_obs, margin, diagnostics
    """
    pairs = [(p.input, p.output) for p in task.train if p.output is not None]
    N_train = len(pairs)
    if N_train == 0:
        return {"can_infer": False, "sigma_c": 0.0, "sigma_obs": 1.0,
                "margin": -1.0, "reason": "no_pairs"}
    A = max(max(c for row in inp for c in row) for inp,_ in pairs)
    A = max(A, 1)
    all_traces = []
    all_hashes = set()
    total_cells = 0
    for inp,_ in pairs:
        fields = extract_fields(inp)
        all_traces.extend(tr for _,tr,_ in fields)
        all_hashes.update(h for h,_,_ in fields)
        total_cells += len(inp) * len(inp[0])
    if len(all_traces) < 2:
        lam_proxy = 1.0
    else:
        mean_tr = sum(all_traces) / len(all_traces)
        var_tr = sum((t - mean_tr)**2 for t in all_traces) / len(all_traces)
        lam_proxy = max((var_tr ** 0.5) / max(abs(mean_tr), 1), 1e-6)
    if total_cells > 1 and len(all_hashes) > 1:
        D2 = max(math.log(len(all_hashes)) / math.log(total_cells), 0.1)
    else:
        D2 = 1.0
    sigma_c = C * A * (lam_proxy ** alpha) * (N_train ** (-beta_exp / D2))
    counts = {}
    conflicts = 0; total_r = 0
    for inp,out in pairs:
        for rule in learn_rules(inp, out):
            key = (rule.trigger_hash, rule.trigger_trace, rule.trigger_det)
            total_r += 1
            if key not in counts: counts[key] = rule.output_color
            elif counts[key] != rule.output_color: conflicts += 1
    sigma_obs = conflicts / max(total_r, 1)
    margin = sigma_c - sigma_obs
    return {
        "can_infer": sigma_obs < sigma_c,
        "sigma_c": sigma_c, "sigma_obs": sigma_obs, "margin": margin,
        "N_train": N_train, "lam_proxy": lam_proxy, "D2": D2,
        "reason": "ok" if sigma_obs < sigma_c else "below_epistemic_horizon",
    }

# ── Gamma_m: eigenvector fourth moment (localization/collapse diagnostic) ────
def gamma_m(rules):
    """
    Gamma_m = sum(p_i^4) where p_i = confidence_i / total_confidence.
    High Gamma_m (->1): one rule dominates — concentrated, fragile.
    Low Gamma_m (->1/N): rules spread flat — robust.
    Collapse threshold: beta_c * a_m^2 = (8*omega_m / 3*Gamma_m) * Delta_omega_m
    """
    if not rules: return 1.0
    total = sum(r.confidence for r in rules)
    if total == 0: return 1.0
    weights = [r.confidence / total for r in rules]
    return sum(w**4 for w in weights)

def participation_ratio(rules):
    """PR = 1/Gamma_m. PR=1: collapsed to one rule. PR->N: fully distributed."""
    g = gamma_m(rules)
    return 1.0 / g if g > 0 else float("inf")

# ── RC6: Stability margin of the rule table ──────────────────────────────────
def rc6_stability_margin(rules):
    """
    B = min pairwise BRA distance between rule triggers.
    Returns (B, n_near_misses):
      B=0: collision (same charge, different output) — unstable
      B=1: near-miss (within TRACE_THRESH/DET_THRESH) — marginal
      B=2: well-separated — certified stable
    """
    if len(rules) < 2: return 2, 0
    TRACE_THRESH = 500_000
    DET_THRESH = 5_000_000
    B = 2; near_misses = 0
    for i in range(len(rules)):
        for j in range(i+1, len(rules)):
            ra, rb = rules[i], rules[j]
            if (ra.trigger_hash==rb.trigger_hash and
                ra.trigger_trace==rb.trigger_trace and
                ra.trigger_det==rb.trigger_det):
                if ra.output_color != rb.output_color: return 0, -1
            else:
                td = abs(ra.trigger_trace - rb.trigger_trace)
                dd = abs(ra.trigger_det   - rb.trigger_det)
                if td < TRACE_THRESH and dd < DET_THRESH:
                    near_misses += 1; B = min(B, 1)
    return B, near_misses

def rule_diagnostics(rules):
    """Full rule table health report: RC6 margin + Gamma_m + PR."""
    B, nms = rc6_stability_margin(rules)
    gm = gamma_m(rules)
    pr = participation_ratio(rules)
    return {
        "n_rules": len(rules),
        "rc6_margin": B,
        "rc6_near_misses": nms,
        "gamma_m": gm,
        "participation_ratio": pr,
        "collapse_risk": "high" if gm > 0.5 else "medium" if gm > 0.1 else "low",
    }

# ── neuro_solve_v3: full pipeline with RC8 gate + Gamma_m diagnostics ────────
def neuro_solve_v3(task):
    """
    RC8 gate -> Tier1 local_3x3 -> Tier1b local_5x5 -> delta -> period.
    All results carry: rc8 check, rc6 margin, gamma_m, participation_ratio.
    If RC8 says below epistemic horizon: tier=abstain_rc8, no prediction.
    """
    r = {"prediction":None,"tier":None,"n_rules":0,"confidence":0,
         "rc8":None,"rc6_margin":None,"gamma_m":None,
         "participation_ratio":None,"collapse_risk":None}
    try:
        rc8 = rc8_epistemic_check(task)
        r["rc8"] = rc8
        if not rc8["can_infer"]:
            r["tier"] = "abstain_rc8"; return r
    except Exception: pass
    for wide,tier in [(False,"local_3x3"),(True,"local_5x5")]:
        try:
            pred = solve_by_local_rules_v2(task, wide=wide)
            if pred is not None:
                pairs = [(p.input,p.output) for p in task.train if p.output]
                rules = learn_from_pairs_union(pairs, wide=wide)
                diag = rule_diagnostics(rules)
                r.update({"prediction":pred,"tier":tier,
                          "n_rules":len(rules),"confidence":2,
                          "rc6_margin":diag["rc6_margin"],
                          "gamma_m":diag["gamma_m"],
                          "participation_ratio":diag["participation_ratio"],
                          "collapse_risk":diag["collapse_risk"]})
                return r
        except Exception: pass
    for fn,tier in [(solve_by_delta,"delta"),(solve_by_period_v2,"period")]:
        try:
            pred = fn(task)
            if pred is not None:
                r.update({"prediction":pred,"tier":tier,"n_rules":1,"confidence":1})
                return r
        except Exception: pass
    return r
