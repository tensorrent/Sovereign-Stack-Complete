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
//! VEXEL — Vector Complete Voxel
//! ================================
//! The individual person's unique AI intelligence shell.
//!
//! Architecture:
//!   CYLINDER  = Ulam spiral prime positions (universal, fixed for all vexels)
//!   SHEET     = Scroll of MIDI-encoded session events (append-only)
//!   VEXEL     = (cylinder_coord, sheet, merkle_root)
//!               merkle_root = one integer committing to full history from seed
//!
//! The cylinder is the isomorphic standardization protocol.
//! Primes on the Ulam spiral are the pins. The scroll is the sheet.
//! Holes only exist where session events align with a prime pin.
//! Playback = cylinder × sheet → resonance where pins meet holes.
//!
//! Author: Brad Wallace

#![allow(dead_code)]

// ── ULAM SPIRAL ──────────────────────────────────────────────────────────────
//
// The Ulam spiral maps integers to 2D coordinates by walking outward in
// a square spiral from (0,0). Primes cluster on diagonals — this is the
// isomorphic coordinate system shared by all vexels.
//
// Walk pattern (shell k, k=0,1,2,...):
//   side length = 2k, starting at (k, -(k-1)) going up
//   Then left, down, right to complete the square

/// (x, y) position on the Ulam spiral for integer n.
/// n=1 → (0,0), n=2 → (1,0), n=3 → (1,1), ...
pub fn ulam_coord(n: u64) -> (i64, i64) {
    if n == 1 { return (0, 0); }
    // Find which shell
    let k = (((n as f64).sqrt() - 1.0) / 2.0).ceil() as i64;
    let side = 2 * k;
    // Start of this shell: (2k-1)² + 1
    let shell_start = (2*k - 1) * (2*k - 1) + 1;
    let pos = n as i64 - shell_start; // position within shell (0-indexed)
    // Four sides, each length `side`
    let s = side;
    if pos < s {
        // Top side: right to left, starting from (k, -(k-1)) going to (-k+1, -(k-1))
        // Actually: bottom-right corner going up
        return (k, -k + 1 + pos);
    }
    let pos = pos - s;
    if pos < s {
        // Left side: going left
        return (k - 1 - pos, k);
    }
    let pos = pos - s;
    if pos < s {
        // Bottom side: going right
        return (-k, k - 1 - pos);
    }
    let pos = pos - s;
    // Right side: going right (completing the square)
    (-k + 1 + pos, -k)
}

/// Sieve of Eratosthenes up to limit
pub fn sieve(limit: usize) -> Vec<bool> {
    let mut is_prime = vec![true; limit + 1];
    is_prime[0] = false;
    if limit > 0 { is_prime[1] = false; }
    let mut i = 2;
    while i * i <= limit {
        if is_prime[i] {
            let mut j = i * i;
            while j <= limit {
                is_prime[j] = false;
                j += i;
            }
        }
        i += 1;
    }
    is_prime
}

/// Check if n is prime (trial division — adequate for vexel pin placement)
pub fn is_prime(n: u64) -> bool {
    if n < 2 { return false; }
    if n == 2 { return true; }
    if n % 2 == 0 { return false; }
    let mut i = 3u64;
    while i * i <= n {
        if n % i == 0 { return false; }
        i += 2;
    }
    true
}

/// The Cylinder: prime positions on the Ulam spiral up to capacity.
/// This is the universal isomorphic standard — identical for every vexel.
pub struct Cylinder {
    pub primes: Vec<(u64, i64, i64)>,  // (prime, x, y)
    pub capacity: u64,
}

impl Cylinder {
    /// Build the cylinder with all primes up to `capacity`.
    pub fn new(capacity: u64) -> Self {
        let primes: Vec<(u64, i64, i64)> = (2..=capacity)
            .filter(|&n| is_prime(n))
            .map(|n| { let (x, y) = ulam_coord(n); (n, x, y) })
            .collect();
        Cylinder { primes, capacity }
    }

    /// Find the nearest prime pin to a given integer charge.
    /// Returns (prime, x, y, distance²).
    pub fn nearest_pin(&self, charge: u64) -> (u64, i64, i64, i64) {
        let (cx, cy) = ulam_coord(charge);
        self.primes.iter()
            .map(|&(p, px, py)| {
                let d2 = (px - cx).pow(2) + (py - cy).pow(2);
                (p, px, py, d2)
            })
            .min_by_key(|&(_, _, _, d2)| d2)
            .unwrap_or((2, 1, 0, 0))
    }

    /// Does this charge align with a prime pin within threshold distance²?
    /// Alignment = event gets cut into the scroll (a hole in the sheet).
    pub fn aligns(&self, charge: u64, threshold_d2: i64) -> Option<(u64, i64, i64)> {
        let (p, px, py, d2) = self.nearest_pin(charge);
        if d2 <= threshold_d2 { Some((p, px, py)) } else { None }
    }
}

// ── MIDI EVENT SCHEMA ─────────────────────────────────────────────────────────
//
// Each session event is 32 bytes — a fixed-width integer tuple.
// MIDI philosophy: don't store the sound, store the event that made it.
// The scroll is a sequence of these tuples, append-only.

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
#[repr(u8)]
pub enum EventType {
    Seed      = 0x01,  // Session initialized with seed
    Query     = 0x02,  // User query processed
    Resonance = 0x03,  // Well hit — pin aligned
    Miss      = 0x04,  // No well hit
    Mixdown   = 0x05,  // Session end — merkle root snapshot
    Backup    = 0x06,  // Exported to external store
}

/// One MIDI-encoded session event. Exactly 32 bytes, pure integers.
/// Fixed width enables O(1) random access in the scroll.
///
/// Layout: session_id(8) + charge(8) + prime_pin(8) + timestamp(4) + well_id(2) + type(1) + score(1) = 32
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
#[repr(C, packed)]
pub struct VexelEvent {
    pub session_id:  u64,  // FNV64 of seed + epoch
    pub charge:      u64,  // BRA eigen hash
    pub prime_pin:   u64,  // nearest prime pin on cylinder (0 = no alignment)
    pub timestamp:   u32,  // session-scoped µs clock
    pub well_id:     u16,  // matched well index (0xFFFF = none)
    pub event_type:  u8,   // EventType
    pub score:       u8,   // resonance score 0/1/2
}
// compile-time size check — must be exactly 32 bytes
const _: () = assert!(std::mem::size_of::<VexelEvent>() == 32);

impl VexelEvent {
    pub fn to_bytes(self) -> [u8; 32] {
        unsafe { std::mem::transmute(self) }
    }

    pub fn from_bytes(b: [u8; 32]) -> Self {
        unsafe { std::mem::transmute(b) }
    }

    /// FNV-64 of this event's bytes — used as Merkle leaf hash
    pub fn leaf_hash(&self) -> u64 {
        let bytes = self.to_bytes();
        fnv64(&bytes)
    }
}

// ── MERKLE TREE ───────────────────────────────────────────────────────────────
//
// Pure integer Merkle tree over the scroll.
// Leaf  = fnv64(event_bytes)
// Inner = fnv64(left_hash ++ right_hash)  — concatenated as 16 bytes
// Root  = single u64 committing to full history
//
// The root IS the vexel's current state fingerprint.
// Any point in the scroll can be proven authentic without revealing the rest.

pub fn merkle_combine(left: u64, right: u64) -> u64 {
    let mut buf = [0u8; 16];
    buf[..8].copy_from_slice(&left.to_le_bytes());
    buf[8..].copy_from_slice(&right.to_le_bytes());
    fnv64(&buf)
}

/// Compute the Merkle root of a leaf hash sequence.
/// Empty → 0. Single leaf → that leaf. Power-of-2 or padded with 0s.
pub fn merkle_root(leaves: &[u64]) -> u64 {
    if leaves.is_empty() { return 0; }
    if leaves.len() == 1 { return leaves[0]; }
    // Pad to next power of 2
    let mut level: Vec<u64> = leaves.to_vec();
    let n = level.len().next_power_of_two();
    level.resize(n, 0u64);  // pad with zero hashes
    while level.len() > 1 {
        level = level.chunks(2)
            .map(|pair| merkle_combine(pair[0], pair[1]))
            .collect();
    }
    level[0]
}

/// Merkle proof for leaf at `index` in `leaves`.
/// Returns list of (sibling_hash, is_right) pairs up to root.
pub fn merkle_proof(leaves: &[u64], index: usize) -> Vec<(u64, bool)> {
    if leaves.is_empty() { return vec![]; }
    let mut level: Vec<u64> = leaves.to_vec();
    let n = level.len().next_power_of_two();
    level.resize(n, 0u64);
    let mut proof = Vec::new();
    let mut idx = index;
    while level.len() > 1 {
        let sibling = if idx % 2 == 0 { idx + 1 } else { idx - 1 };
        let sib_hash = if sibling < level.len() { level[sibling] } else { 0 };
        proof.push((sib_hash, idx % 2 == 0));
        idx /= 2;
        level = level.chunks(2)
            .map(|pair| merkle_combine(pair[0], pair[1]))
            .collect();
    }
    proof
}

/// Verify a Merkle proof given a leaf hash, proof path, and expected root.
pub fn merkle_verify(leaf: u64, proof: &[(u64, bool)], root: u64) -> bool {
    let mut current = leaf;
    for &(sibling, we_are_left) in proof {
        current = if we_are_left {
            merkle_combine(current, sibling)
        } else {
            merkle_combine(sibling, current)
        };
    }
    current == root
}

// ── SCROLL ────────────────────────────────────────────────────────────────────
//
// The scroll is the append-only event log — the sheet music.
// In memory: Vec<VexelEvent>
// On disk: raw binary (32 bytes per event), append-only

pub struct Scroll {
    pub events:  Vec<VexelEvent>,
    pub session_id: u64,
}

impl Scroll {
    pub fn new(session_id: u64) -> Self {
        Scroll { events: Vec::new(), session_id }
    }

    /// Append one event. Returns the new leaf hash.
    pub fn append(&mut self, event: VexelEvent) -> u64 {
        let h = event.leaf_hash();
        self.events.push(event);
        h
    }

    /// Current Merkle root — the vexel's fingerprint right now.
    pub fn root(&self) -> u64 {
        let leaves: Vec<u64> = self.events.iter().map(|e| e.leaf_hash()).collect();
        merkle_root(&leaves)
    }

    /// Proof that event at `index` is in the current scroll.
    pub fn prove(&self, index: usize) -> Vec<(u64, bool)> {
        let leaves: Vec<u64> = self.events.iter().map(|e| e.leaf_hash()).collect();
        merkle_proof(&leaves, index)
    }

    /// Serialize to bytes (32 bytes × events).
    pub fn to_bytes(&self) -> Vec<u8> {
        let mut out = Vec::with_capacity(self.events.len() * 32);
        for e in &self.events {
            out.extend_from_slice(&e.to_bytes());
        }
        out
    }

    /// Deserialize from bytes.
    pub fn from_bytes(session_id: u64, data: &[u8]) -> Self {
        let events = data.chunks_exact(32)
            .map(|chunk| {
                let mut arr = [0u8; 32];
                arr.copy_from_slice(chunk);
                VexelEvent::from_bytes(arr)
            })
            .collect();
        Scroll { events, session_id }
    }

    /// MIDI mixdown: session summary as (session_id, event_count, root_hash, timestamp)
    pub fn mixdown(&self, timestamp: u64) -> (u64, u64, u64, u64) {
        (self.session_id, self.events.len() as u64, self.root(), timestamp)
    }
}

// ── VEXEL ─────────────────────────────────────────────────────────────────────
//
// The person's unique AI intelligence shell.
// CYLINDER  = universal prime coordinate system
// SCROLL    = their complete event history from seed
// ROOT      = current Merkle fingerprint (their identity at this moment)
// ULAM_COORD= their position on the spiral (derived from root hash)

pub struct Vexel {
    pub cylinder:     Cylinder,
    pub scroll:       Scroll,
    pub seed_hash:    u64,        // FNV64 of the initial seed
    pub ulam_coord:   (i64, i64), // current position on the spiral
    pub session_clock: u64,       // µs since session start (full u64, truncated to u32 in events)
    pub align_thresh:  i64,       // d² threshold for pin alignment (default 2)
}

impl Vexel {
    /// Initialize a new vexel from a seed string.
    pub fn new(seed: &str, cylinder_capacity: u64) -> Self {
        let seed_hash = fnv64(seed.as_bytes());
        let session_id = seed_hash ^ epoch_us();
        let cylinder = Cylinder::new(cylinder_capacity);
        let mut scroll = Scroll::new(session_id);

        let seed_event = VexelEvent {
            session_id,
            charge: seed_hash,
            prime_pin: cylinder.nearest_pin(seed_hash % cylinder_capacity.max(1)).0,
            timestamp: 0,
            well_id: 0xFFFF,
            event_type: EventType::Seed as u8,
            score: 0,
        };
        scroll.append(seed_event);

        let root = scroll.root();
        let ulam_coord = ulam_coord(root % cylinder_capacity.max(1));

        Vexel {
            cylinder,
            scroll,
            seed_hash,
            ulam_coord,
            session_clock: 0,
            align_thresh: 2,
        }
    }

    /// Record a session event. If the charge aligns with a prime pin,
    /// it gets cut into the scroll. Returns (event, was_aligned).
    pub fn record(&mut self,
                  event_type: EventType,
                  charge: u64,
                  well_id: u16,
                  score: u8) -> (VexelEvent, bool) {
        self.session_clock += 1;
        let pin = match self.cylinder.aligns(
            charge % self.cylinder.capacity.max(1), self.align_thresh) {
            Some((p, _, _)) => p,
            None => 0,
        };
        let event = VexelEvent {
            session_id: self.scroll.session_id,
            charge,
            prime_pin: pin,
            timestamp: (self.session_clock & 0xFFFFFFFF) as u32,
            well_id,
            event_type: event_type as u8,
            score,
        };
        self.scroll.append(event);
        // Update position on spiral
        let root = self.scroll.root();
        self.ulam_coord = ulam_coord(root % self.cylinder.capacity.max(1));
        (event, pin != 0)
    }

    /// Current Merkle root — the vexel's identity fingerprint.
    pub fn root(&self) -> u64 { self.scroll.root() }

    /// Mixdown: minimal backup payload.
    /// Returns (session_id, event_count, root_hash, clock)
    pub fn mixdown(&self) -> (u64, u64, u64, u64) {
        self.scroll.mixdown(self.session_clock)
    }

    /// Prove that event at index is in this vexel's history.
    pub fn prove_event(&self, index: usize) -> Vec<(u64, bool)> {
        self.scroll.prove(index)
    }

    /// Serialize the complete scroll for backup.
    pub fn export_scroll(&self) -> Vec<u8> {
        self.scroll.to_bytes()
    }
}

// ── UTILITIES ─────────────────────────────────────────────────────────────────

pub fn fnv64(bytes: &[u8]) -> u64 {
    let mut h: u64 = 0xcbf29ce484222325;
    for &b in bytes {
        h ^= b as u64;
        h = h.wrapping_mul(0x100000001b3);
    }
    h
}

fn epoch_us() -> u64 {
    // Monotonic clock in µs — used for session IDs
    use std::time::{SystemTime, UNIX_EPOCH};
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|d| d.as_micros() as u64)
        .unwrap_or(0)
}

// ── TESTS ─────────────────────────────────────────────────────────────────────

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn ulam_origin() {
        assert_eq!(ulam_coord(1), (0, 0));
        assert_eq!(ulam_coord(2), (1, 0));
    }

    #[test]
    fn ulam_primes_cluster() {
        // Primes on Ulam spiral famously cluster on diagonals
        // Just verify the coordinate system is consistent and deterministic
        let (x1, y1) = ulam_coord(17);
        let (x2, y2) = ulam_coord(17);
        assert_eq!((x1, y1), (x2, y2));
    }

    #[test]
    fn cylinder_universal() {
        // Same cylinder, different invocations → identical primes
        let c1 = Cylinder::new(100);
        let c2 = Cylinder::new(100);
        assert_eq!(c1.primes.len(), c2.primes.len());
        assert_eq!(c1.primes[0], c2.primes[0]);
        // First prime is always (2, 1, 0)
        assert_eq!(c1.primes[0], (2, 1, 0));
    }

    #[test]
    fn cylinder_primes_are_prime() {
        let c = Cylinder::new(50);
        for &(p, _, _) in &c.primes {
            assert!(is_prime(p), "{} flagged as prime but isn't", p);
        }
    }

    #[test]
    fn event_size_32_bytes() {
        assert_eq!(std::mem::size_of::<VexelEvent>(), 32);
    }

    #[test]
    fn event_roundtrip() {
        let e = VexelEvent {
            session_id: 0xDEADBEEF_CAFEBABE,
            charge: 0x12345678_90ABCDEF,
            prime_pin: 17,
            timestamp: 42,
            well_id: 7,
            event_type: EventType::Query as u8,
            score: 2,
        };
        let bytes = e.to_bytes();
        let e2 = VexelEvent::from_bytes(bytes);
        assert_eq!(e, e2);
    }

    #[test]
    fn merkle_empty() {
        assert_eq!(merkle_root(&[]), 0);
    }

    #[test]
    fn merkle_single() {
        let h = 0xABCD1234u64;
        assert_eq!(merkle_root(&[h]), h);
    }

    #[test]
    fn merkle_deterministic() {
        let leaves = vec![1u64, 2, 3, 4, 5];
        assert_eq!(merkle_root(&leaves), merkle_root(&leaves));
    }

    #[test]
    fn merkle_proof_verify() {
        let leaves = vec![10u64, 20, 30, 40, 50, 60, 70, 80];
        let root = merkle_root(&leaves);
        for i in 0..leaves.len() {
            let proof = merkle_proof(&leaves, i);
            assert!(
                merkle_verify(leaves[i], &proof, root),
                "proof failed for leaf {}", i
            );
        }
    }

    #[test]
    fn merkle_tamper_detected() {
        let leaves = vec![10u64, 20, 30, 40];
        let root = merkle_root(&leaves);
        let proof = merkle_proof(&leaves, 0);
        // Tampered leaf
        assert!(!merkle_verify(999, &proof, root));
    }

    #[test]
    fn scroll_append_and_root_changes() {
        let mut scroll = Scroll::new(1);
        let r0 = scroll.root();
        let e = VexelEvent {
            session_id: 1, charge: 42, prime_pin: 43,
            timestamp: 1, well_id: 0,
            event_type: EventType::Query as u8, score: 1,
        };
        scroll.append(e);
        let r1 = scroll.root();
        assert_ne!(r0, r1);
    }

    #[test]
    fn scroll_bytes_roundtrip() {
        let mut scroll = Scroll::new(99);
        for i in 0..10u64 {
            scroll.append(VexelEvent {
                session_id: 99, charge: i * 1000,
                prime_pin: i * 7, timestamp: i as u32,
                well_id: i as u16, event_type: EventType::Query as u8,
                score: 0,
            });
        }
        let bytes = scroll.to_bytes();
        let restored = Scroll::from_bytes(99, &bytes);
        assert_eq!(scroll.root(), restored.root());
        assert_eq!(scroll.events.len(), restored.events.len());
    }

    #[test]
    fn vexel_unique_per_seed() {
        let v1 = Vexel::new("alice", 1000);
        let v2 = Vexel::new("bob",   1000);
        assert_ne!(v1.seed_hash, v2.seed_hash);
        // Roots differ (session IDs differ → seed events differ)
        // Note: roots may collide probabilistically but essentially never will
        let c1 = v1.scroll.events[0].charge; let c2 = v2.scroll.events[0].charge;
        assert_ne!(c1, c2);
    }

    #[test]
    fn vexel_cylinder_universal() {
        // Both vexels share the same cylinder pins
        let v1 = Vexel::new("alice", 1000);
        let v2 = Vexel::new("bob",   1000);
        assert_eq!(v1.cylinder.primes.len(), v2.cylinder.primes.len());
        assert_eq!(v1.cylinder.primes[0], v2.cylinder.primes[0]);
    }

    #[test]
    fn vexel_root_evolves_with_events() {
        let mut v = Vexel::new("test_seed", 500);
        let r0 = v.root();
        v.record(EventType::Query, 0xABCD, 0, 1);
        let r1 = v.root();
        v.record(EventType::Query, 0xEF01, 1, 2);
        let r2 = v.root();
        assert_ne!(r0, r1);
        assert_ne!(r1, r2);
    }

    #[test]
    fn vexel_proof_authenticates_event() {
        let mut v = Vexel::new("brad", 500);
        v.record(EventType::Query,     0x1111, 0, 1);
        v.record(EventType::Resonance, 0x2222, 3, 2);
        v.record(EventType::Query,     0x3333, 1, 0);

        let root = v.root();
        let _leaves: Vec<u64> = v.scroll.events.iter().map(|e| e.leaf_hash()).collect();

        for i in 0..v.scroll.events.len() {
            let proof = v.prove_event(i);
            assert!(
                merkle_verify(v.scroll.events[i].leaf_hash(), &proof, root),
                "event {} not provable", i
            );
        }
    }

    #[test]
    fn vexel_export_import_preserves_root() {
        let mut v = Vexel::new("export_test", 500);
        v.record(EventType::Query, 0xAAAA, 0, 1);
        v.record(EventType::Query, 0xBBBB, 1, 2);
        let root_before = v.root();

        let bytes = v.export_scroll();
        let restored = Scroll::from_bytes(v.scroll.session_id, &bytes);
        assert_eq!(root_before, restored.root());
    }

    #[test]
    fn vexel_mixdown_format() {
        let mut v = Vexel::new("mixdown_test", 500);
        v.record(EventType::Query, 0xCCCC, 0, 0);
        let (sid, count, root, clock) = v.mixdown();
        assert_eq!(sid, v.scroll.session_id);
        assert_eq!(count, v.scroll.events.len() as u64);
        assert_eq!(root, v.root());
        assert!(clock > 0);
    }

    #[test]
    fn pin_alignment_is_prime() {
        let v = Vexel::new("alignment_test", 1000);
        let mut v = v;
        let (event, aligned) = v.record(EventType::Query, 1000037, 0, 0);
        if aligned {
            let pin = event.prime_pin;
            assert!(is_prime(pin), "pin {} is not prime", pin);
        }
    }
}
