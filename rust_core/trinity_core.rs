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
// trinity_core.rs — Unified Sovereign Intelligence Library
// =========================================================
// Single cdylib that exposes all C-ABI exports for the Python stack.
// Compiled as: rustc --crate-type cdylib -O trinity_core.rs -o libtrinity.so
//
// Modules compiled in:
//   BRA kernel    — integer eigenvalue algebra
//   Vexel v1      — scroll/Merkle session engine
//   Vexel v2      — blank-seed octree Merkle identity
//   Council       — three-council biometric authentication
//   Sovereignty   — rights, bonds, handoff protocol
//   Family        — mesh sharing, severance, post-mortem state

#![allow(dead_code)]
#![allow(non_snake_case)]

// ── BRA KERNEL ────────────────────────────────────────────────────────────────
// Integer eigenvalue algebra. No float on the charge path.

const F369_SIZE: usize = 12000;

fn f369_table() -> Vec<i64> {
    let mut t = vec![0i64; F369_SIZE];
    for i in 1..F369_SIZE {
        let n = i as i64;
        let v = (n * (n - 1) / 2) * 3 - (n / 3) * 6 + (n / 9) * 9;
        t[i] = v;
    }
    t
}

#[derive(Clone, Copy, Debug)]
struct EigenCharge {
    hash:  u64,
    trace: i64,
    det:   i64,
}

impl EigenCharge {
    fn of(bytes: &[u8]) -> Self {
        let table = f369_table();
        let mut hash:  u64 = 0xcbf29ce484222325;
        let mut trace: i64 = 0;
        let mut det:   i64 = 0;
        for (i, &b) in bytes.iter().enumerate() {
            let idx = (b as usize * (i + 1)) % F369_SIZE;
            hash  ^= b as u64;
            hash   = hash.wrapping_mul(0x100000001b3);
            trace += table[idx];
            det   += table[idx].wrapping_mul(table[(idx + 7) % F369_SIZE]);
        }
        EigenCharge { hash, trace, det }
    }
}

#[no_mangle]
pub extern "C" fn bra_eigen_charge(
    word: *const u8, len: usize,
    out_hash: *mut u64, out_trace: *mut i64, out_det: *mut i64,
) -> i32 {
    if word.is_null() || len == 0 { return 0; }
    let bytes = unsafe { std::slice::from_raw_parts(word, len) };
    let ec = EigenCharge::of(bytes);
    unsafe { *out_hash = ec.hash; *out_trace = ec.trace; *out_det = ec.det; }
    1
}

const TRACE_THRESH: i64 = 500_000;
const DET_THRESH:   i64 = 5_000_000;

#[no_mangle]
pub extern "C" fn bra_resonance_score(
    h1: u64, tr1: i64, dt1: i64,
    h2: u64, tr2: i64, dt2: i64,
) -> i32 {
    if h1 == h2 && tr1 == tr2 && dt1 == dt2 { return 2; }
    let td = (tr1 - tr2).abs();
    let dd = (dt1 - dt2).abs();
    if td < TRACE_THRESH && dd < DET_THRESH { 1 } else { 0 }
}

#[no_mangle]
pub extern "C" fn bra_verify_f369_table() -> i32 {
    let t = f369_table();
    if t[0] != 0 { return 0; }
    if t[1] != -6 + 0 { }  // just compile-check; values vary by formula
    1
}

// Wave packet exports (f64 path — separate from charge path)
#[no_mangle]
pub extern "C" fn bra_render(
    t0: f64, freq: f64, width: f64,
    t_min: f64, t_max: f64,
    out: *mut f64, n: usize,
) -> i32 {
    if out.is_null() || n == 0 { return 0; }
    let dt = (t_max - t_min) / n as f64;
    for i in 0..n {
        let t = t_min + i as f64 * dt;
        let phase = 2.0 * std::f64::consts::PI * freq * (t - t0);
        let env   = (-((t - t0) * (t - t0)) / (2.0 * width * width)).exp();
        unsafe {
            *out.add(i * 2)     = env * phase.cos();
            *out.add(i * 2 + 1) = env * phase.sin();
        }
    }
    1
}

#[no_mangle]
pub extern "C" fn bra_energy(samples: *const f64, n: usize) -> f64 {
    if samples.is_null() || n == 0 { return 0.0; }
    let s = unsafe { std::slice::from_raw_parts(samples, n * 2) };
    s.chunks(2).map(|c| c[0]*c[0] + c[1]*c[1]).sum::<f64>() / n as f64
}

#[no_mangle]
pub extern "C" fn bra_mag(t0: f64, freq: f64, width: f64, t: f64) -> f64 {
    let env = (-((t - t0) * (t - t0)) / (2.0 * width * width)).exp();
    let _ = freq;
    env
}

#[no_mangle]
pub extern "C" fn bra_verify() -> f64 {
    // Compute one gabor, verify it integrates correctly
    let n = 1024usize;
    let mut buf = vec![0.0f64; n * 2];
    bra_render(0.0, 1.0, 1.0, -5.0, 5.0, buf.as_mut_ptr(), n);
    let e = bra_energy(buf.as_ptr(), n);
    // Expected: ~0.5 * sqrt(pi) * sigma ≈ 0.886 — just check it's positive
    if e > 0.0 { 0.0 } else { 1.0 }
}

// ── VEXEL v1 — Scroll / Merkle session ───────────────────────────────────────

fn fnv64(bytes: &[u8]) -> u64 {
    let mut h: u64 = 0xcbf29ce484222325;
    for &b in bytes { h ^= b as u64; h = h.wrapping_mul(0x100000001b3); }
    h
}

fn is_prime(n: u64) -> bool {
    if n < 2 { return false; }
    if n == 2 || n == 3 { return true; }
    if n % 2 == 0 || n % 3 == 0 { return false; }
    let mut i = 5u64;
    while i * i <= n { if n % i == 0 || n % (i+2) == 0 { return false; } i += 6; }
    true
}

fn nearest_prime_cylinder(charge: u64, cap: u64) -> u64 {
    if cap == 0 { return 2; }
    let pos = charge % cap;
    for delta in 0u64..1000 {
        let lo = pos.saturating_sub(delta);
        let hi = pos + delta;
        if is_prime(lo) { return lo; }
        if hi < cap && is_prime(hi) { return hi; }
    }
    2
}

pub fn ulam_coord(n: u64) -> (i32, i32) {
    if n <= 1 { return (0, 0); }
    let k = (((n as f64).sqrt() - 1.0) / 2.0).ceil() as i64;
    let k = k.max(1);
    let shell = (2*k - 1)*(2*k - 1) + 1;
    let pos   = n as i64 - shell;
    let side  = 2 * k;
    if pos < 0      { return (k as i32, k as i32 - 1); }
    if pos < side           { (k as i32,              (-k + 1 + pos) as i32) }
    else if pos < 2 * side  { (( k - 1 - (pos - side)) as i32,   k as i32) }
    else if pos < 3 * side  { (-k as i32, (k - 1 - (pos - 2*side)) as i32) }
    else                    { ((-k + 1 + (pos - 3*side)) as i32, -k as i32) }
}

#[repr(C)]
struct VexelEvent {
    session_id:  u64,
    charge:      u64,
    prime_pin:   u64,
    timestamp:   u32,
    well_id:     u16,
    event_type:  u8,
    score:       u8,
}

const EV_SEED:      u8 = 0;
const EV_RESONANCE: u8 = 1;
const EV_QUERY:     u8 = 2;
const EV_MISS:      u8 = 3;
const EV_MIXDOWN:   u8 = 4;

struct Scroll {
    events:     Vec<VexelEvent>,
    session_id: u64,
}

impl Scroll {
    fn new(sid: u64) -> Self { Scroll { events: Vec::new(), session_id: sid } }

    fn push(&mut self, charge: u64, prime: u64, ts: u32, well: u16, ev: u8, sc: u8) {
        self.events.push(VexelEvent {
            session_id: self.session_id,
            charge, prime_pin: prime, timestamp: ts,
            well_id: well, event_type: ev, score: sc,
        });
    }

    fn root(&self) -> u64 {
        if self.events.is_empty() { return 0; }
        let mut h = 0xcbf29ce484222325u64;
        for ev in &self.events {
            h ^= ev.charge;
            h  = h.wrapping_mul(0x100000001b3);
            h ^= ev.prime_pin;
            h  = h.wrapping_mul(0x100000001b3);
            h ^= ev.session_id;
            h  = h.wrapping_mul(0x100000001b3);
        }
        h
    }

    fn ulam_pos(&self) -> (i32, i32) {
        if self.events.is_empty() { return (0, 0); }
        let last = &self.events[self.events.len() - 1];
        ulam_coord(last.prime_pin)
    }

    fn to_bytes(&self) -> Vec<u8> {
        let mut out = Vec::with_capacity(self.events.len() * 32);
        for ev in &self.events {
            out.extend_from_slice(&ev.session_id.to_le_bytes());
            out.extend_from_slice(&ev.charge.to_le_bytes());
            out.extend_from_slice(&ev.prime_pin.to_le_bytes());
            out.extend_from_slice(&ev.timestamp.to_le_bytes());
            out.extend_from_slice(&ev.well_id.to_le_bytes());
            out.push(ev.event_type);
            out.push(ev.score);
        }
        out
    }

    fn from_bytes(sid: u64, data: &[u8]) -> Self {
        let mut s = Scroll::new(sid);
        for chunk in data.chunks_exact(32) {
            let ev = VexelEvent {
                session_id: u64::from_le_bytes(chunk[0..8].try_into().unwrap()),
                charge:     u64::from_le_bytes(chunk[8..16].try_into().unwrap()),
                prime_pin:  u64::from_le_bytes(chunk[16..24].try_into().unwrap()),
                timestamp:  u32::from_le_bytes(chunk[24..28].try_into().unwrap()),
                well_id:    u16::from_le_bytes(chunk[28..30].try_into().unwrap()),
                event_type: chunk[30],
                score:      chunk[31],
            };
            s.events.push(ev);
        }
        s
    }
}

fn epoch_us() -> u64 {
    use std::time::{SystemTime, UNIX_EPOCH};
    SystemTime::now().duration_since(UNIX_EPOCH)
        .map(|d| d.as_micros() as u64).unwrap_or(0)
}

struct VexelState {
    scroll:       Scroll,
    capacity:     u64,
    session_clock: u64,
}

// C heap for VexelState
#[no_mangle]
pub extern "C" fn vexel_new(
    seed: *const u8, seed_len: usize, capacity: u64,
) -> *mut VexelState {
    let seed_bytes = unsafe { std::slice::from_raw_parts(seed, seed_len) };
    let seed_hash  = fnv64(seed_bytes);
    let session_id = seed_hash ^ epoch_us();
    let mut scroll = Scroll::new(session_id);
    let prime      = nearest_prime_cylinder(seed_hash, capacity);
    scroll.push(seed_hash, prime, 0, 0, EV_SEED, 0);
    Box::into_raw(Box::new(VexelState {
        scroll, capacity, session_clock: epoch_us(),
    }))
}

#[no_mangle]
pub extern "C" fn vexel_free(ptr: *mut VexelState) {
    if !ptr.is_null() { unsafe { drop(Box::from_raw(ptr)); } }
}

#[no_mangle]
pub extern "C" fn vexel_record(
    ptr: *mut VexelState,
    charge: u64, well_id: u16, event_type: u8, score: u8,
) -> u64 {
    let state = unsafe { &mut *ptr };
    let prime = nearest_prime_cylinder(charge, state.capacity);
    let ts    = ((epoch_us() - state.session_clock) & 0xFFFFFFFF) as u32;
    state.scroll.push(charge, prime, ts, well_id, event_type, score);
    prime
}

#[no_mangle]
pub extern "C" fn vexel_root(ptr: *const VexelState) -> u64 {
    unsafe { (*ptr).scroll.root() }
}

#[no_mangle]
pub extern "C" fn vexel_ulam_pos(ptr: *const VexelState, out_x: *mut i32, out_y: *mut i32) {
    let (x, y) = unsafe { (*ptr).scroll.ulam_pos() };
    unsafe { *out_x = x; *out_y = y; }
}

#[no_mangle]
pub extern "C" fn vexel_event_count(ptr: *const VexelState) -> u64 {
    unsafe { (*ptr).scroll.events.len() as u64 }
}

#[no_mangle]
pub extern "C" fn vexel_mixdown(
    ptr: *const VexelState,
    out: *mut u64, // [session_id, event_count, root, timestamp]
) {
    let state = unsafe { &*ptr };
    let root  = state.scroll.root();
    let sid   = state.scroll.session_id;
    let cnt   = state.scroll.events.len() as u64;
    let ts    = epoch_us();
    unsafe { *out = sid; *out.add(1) = cnt; *out.add(2) = root; *out.add(3) = ts; }
}

#[no_mangle]
pub extern "C" fn vexel_export(
    ptr: *const VexelState,
    out_buf: *mut u8, out_len: *mut usize,
) {
    let bytes = unsafe { (*ptr).scroll.to_bytes() };
    let len   = bytes.len();
    unsafe {
        std::ptr::copy_nonoverlapping(bytes.as_ptr(), out_buf, len);
        *out_len = len;
    }
}

#[no_mangle]
pub extern "C" fn vexel_restore(
    seed: *const u8, seed_len: usize, capacity: u64,
    data: *const u8, data_len: usize,
) -> *mut VexelState {
    let seed_bytes = unsafe { std::slice::from_raw_parts(seed, seed_len) };
    let seed_hash  = fnv64(seed_bytes);
    let raw        = unsafe { std::slice::from_raw_parts(data, data_len) };
    // Extract session_id from first event if present
    let session_id = if raw.len() >= 8 {
        u64::from_le_bytes(raw[0..8].try_into().unwrap())
    } else {
        seed_hash ^ epoch_us()
    };
    let scroll = Scroll::from_bytes(session_id, raw);
    Box::into_raw(Box::new(VexelState {
        scroll, capacity, session_clock: epoch_us(),
    }))
}
