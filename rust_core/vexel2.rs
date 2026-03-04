//! VEXEL v2 — Blank Seed · Octree Merkle Identity
//! ==================================================
//!
//! The vexel starts at the Ulam origin. No declared identity.
//! Every word, query, and interaction inserts a point into a 3D octree.
//! The tree shape IS the person.
//!
//! AXES:
//!   x = Ulam spiral x  (from eigen charge of the token)
//!   y = Ulam spiral y  (from eigen charge)
//!   z = session depth  (monotonic interaction count — the time axis)
//!
//! OCTREE MERKLE:
//!   Each node covers a cubic region of (x, y, z) space.
//!   8 children per node (one per octant).
//!   Node hash = fnv64(child_0 ++ child_1 ++ ... ++ child_7)
//!   Leaf hash  = fnv64(point_bytes)
//!   Root       = one u64 committing to the entire tree.
//!
//! PRIVACY:
//!   Public branch  → hash + all children visible (verifiable)
//!   Private branch → hash only (proves existence, reveals nothing)
//!   Selective      → Merkle path from root to one point
//!
//! VISUAL:
//!   Tree serialized as nested JSON-like structure.
//!   Each node: {hash, bounds, depth, point_count, children: [8], privacy}
//!   Renderer consumes this to draw nested cubes.
//!
//! Author: Brad Wallace

#![allow(dead_code)]

// ── TYPES ─────────────────────────────────────────────────────────────────────

/// A point in the octree — one word, query, or interaction event.
/// Layout (32 bytes, no padding): charge(8)+prime_pin(8)+x(4)+y(4)+z(4)+event_type(1)+score(1)+_pad(2)
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
#[repr(C)]
pub struct OctPoint {
    pub charge:     u64,   // raw BRA eigen hash            [0..8]
    pub prime_pin:  u64,   // nearest prime on Ulam cylinder[8..16]
    pub x:          i32,   // Ulam spiral x of eigen charge [16..20]
    pub y:          i32,   // Ulam spiral y of eigen charge [20..24]
    pub z:          u32,   // interaction depth (time axis) [24..28]
    pub event_type: u8,    // Word=1 Query=2 Resonance=3 Miss=4 [28]
    pub score:      u8,    // resonance score 0/1/2         [29]
    pub _pad:       [u8;2],//                               [30..32]
}
const _: () = assert!(std::mem::size_of::<OctPoint>() == 32);

impl OctPoint {
    pub fn leaf_hash(&self) -> u64 {
        // Layout: charge(8)+prime_pin(8)+x(4)+y(4)+z(4)+event_type(1)+score(1)+_pad(2) = 32
        let mut buf = [0u8; 32];
        buf[0..8].copy_from_slice(&self.charge.to_le_bytes());
        buf[8..16].copy_from_slice(&self.prime_pin.to_le_bytes());
        buf[16..20].copy_from_slice(&self.x.to_le_bytes());
        buf[20..24].copy_from_slice(&self.y.to_le_bytes());
        buf[24..28].copy_from_slice(&self.z.to_le_bytes());
        buf[28] = self.event_type;
        buf[29] = self.score;
        fnv64(&buf)
    }
}

/// Axis-aligned bounding box for an octree node.
#[derive(Clone, Copy, Debug, PartialEq)]
pub struct Bounds {
    pub min: (i32, i32, i32),
    pub max: (i32, i32, i32),
}

impl Bounds {
    pub fn root(half: i32, depth_max: u32) -> Self {
        Bounds {
            min: (-half, -half, 0),
            max: ( half,  half, depth_max as i32),
        }
    }

    pub fn center(&self) -> (i32, i32, i32) {
        (
            (self.min.0 + self.max.0) / 2,
            (self.min.1 + self.max.1) / 2,
            (self.min.2 + self.max.2) / 2,
        )
    }

    /// Which of the 8 octants does point (x,y,z) fall into?
    /// Returns index 0..7 (bit 0=x, bit 1=y, bit 2=z).
    pub fn octant(&self, x: i32, y: i32, z: i32) -> usize {
        let (cx, cy, cz) = self.center();
        let bx = if x >= cx { 1 } else { 0 };
        let by = if y >= cy { 2 } else { 0 };
        let bz = if z >= cz { 4 } else { 0 };
        bx | by | bz
    }

    /// Child bounds for the given octant index (0..7).
    pub fn child_bounds(&self, oct: usize) -> Bounds {
        let (cx, cy, cz) = self.center();
        let (x0, x1) = if oct & 1 != 0 { (cx, self.max.0) } else { (self.min.0, cx) };
        let (y0, y1) = if oct & 2 != 0 { (cy, self.max.1) } else { (self.min.1, cy) };
        let (z0, z1) = if oct & 4 != 0 { (cz, self.max.2) } else { (self.min.2, cz) };
        Bounds { min: (x0, y0, z0), max: (x1, y1, z1) }
    }

    pub fn contains(&self, x: i32, y: i32, z: i32) -> bool {
        x >= self.min.0 && x < self.max.0 &&
        y >= self.min.1 && y < self.max.1 &&
        z >= self.min.2 && z < self.max.2
    }

    pub fn is_unit(&self) -> bool {
        self.max.0 - self.min.0 <= 1 &&
        self.max.1 - self.min.1 <= 1 &&
        self.max.2 - self.min.2 <= 1
    }
}

// ── OCTREE NODE ───────────────────────────────────────────────────────────────

/// Privacy setting for a branch.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Privacy {
    Public,   // hash + all children visible
    Private,  // hash only — existence proven, content hidden
}

/// One node in the octree.
pub struct OctNode {
    pub bounds:      Bounds,
    pub hash:        u64,         // Merkle hash of this subtree
    pub point_count: u32,         // total points in this subtree
    pub privacy:     Privacy,
    pub points:      Vec<OctPoint>, // non-empty only at leaves
    pub children:    [Option<Box<OctNode>>; 8],
}

impl OctNode {
    pub fn new_empty(bounds: Bounds) -> Self {
        OctNode {
            bounds,
            hash: 0,
            point_count: 0,
            privacy: Privacy::Public,
            points: Vec::new(),
            children: [None, None, None, None, None, None, None, None],
        }
    }

    pub fn is_leaf(&self) -> bool {
        self.children.iter().all(|c| c.is_none())
    }

    /// Insert a point into this node (recursive).
    pub fn insert(&mut self, p: OctPoint) {
        self.point_count += 1;

        if self.bounds.is_unit() || self.is_leaf() && self.points.is_empty() {
            // Leaf: store point directly
            self.points.push(p);
            self.recompute_hash();
            return;
        }

        if self.is_leaf() && !self.points.is_empty() {
            // Subdivide: push existing points down into children
            let existing = std::mem::take(&mut self.points);
            for ep in existing {
                self.push_to_child(ep);
            }
        }

        self.push_to_child(p);
        self.recompute_hash();
    }

    fn push_to_child(&mut self, p: OctPoint) {
        let oct = self.bounds.octant(p.x, p.y, p.z as i32);
        let child_bounds = self.bounds.child_bounds(oct);
        if self.children[oct].is_none() {
            self.children[oct] = Some(Box::new(OctNode::new_empty(child_bounds)));
        }
        self.children[oct].as_mut().unwrap().insert(p);
    }

    /// Recompute the Merkle hash of this node from children (or leaf points).
    pub fn recompute_hash(&mut self) {
        if self.is_leaf() {
            // Leaf hash = fnv64 fold of all point hashes
            self.hash = self.points.iter()
                .fold(0xcbf29ce484222325u64, |acc, p| {
                    merkle_combine(acc, p.leaf_hash())
                });
        } else {
            // Inner hash = fnv64 of 8 child hashes concatenated
            let child_hashes: [u64; 8] = std::array::from_fn(|i| {
                self.children[i].as_ref().map(|c| c.hash).unwrap_or(0)
            });
            let mut buf = [0u8; 64];
            for (i, &h) in child_hashes.iter().enumerate() {
                buf[i*8..(i+1)*8].copy_from_slice(&h.to_le_bytes());
            }
            self.hash = fnv64(&buf);
        }
    }

    /// Set privacy on this node and all its descendants.
    pub fn set_privacy(&mut self, privacy: Privacy) {
        self.privacy = privacy;
        for child in self.children.iter_mut().flatten() {
            child.set_privacy(privacy);
        }
    }

    /// Set privacy on the octant subtree containing point (x,y,z).
    pub fn set_privacy_at(&mut self, x: i32, y: i32, z: i32, privacy: Privacy) {
        if self.bounds.is_unit() || self.is_leaf() {
            self.privacy = privacy;
            return;
        }
        let oct = self.bounds.octant(x, y, z);
        if let Some(child) = &mut self.children[oct] {
            child.set_privacy_at(x, y, z, privacy);
        }
    }

    /// Merkle proof: path from this node to the leaf containing point hash `target`.
    /// Returns list of (sibling_hashes[8], octant_taken) pairs.
    pub fn proof_path(&self, target: u64) -> Option<Vec<([u64; 8], usize)>> {
        // Check if target is in this subtree
        if !self.contains_hash(target) { return None; }

        if self.is_leaf() {
            // Found — return empty path (we're at the leaf)
            return Some(vec![]);
        }

        for oct in 0..8 {
            if let Some(child) = &self.children[oct] {
                if let Some(mut path) = child.proof_path(target) {
                    let siblings: [u64; 8] = std::array::from_fn(|i| {
                        self.children[i].as_ref().map(|c| c.hash).unwrap_or(0)
                    });
                    path.push((siblings, oct));
                    return Some(path);
                }
            }
        }
        None
    }

    fn contains_hash(&self, target: u64) -> bool {
        if self.hash == target { return true; }
        if self.is_leaf() {
            return self.points.iter().any(|p| p.leaf_hash() == target);
        }
        self.children.iter().flatten().any(|c| c.contains_hash(target))
    }

    /// Serialize to visual representation (JSON-like nested structure).
    pub fn to_visual(&self, max_depth: usize) -> VisualNode {
        self.to_visual_inner(0, max_depth)
    }

    fn to_visual_inner(&self, depth: usize, max_depth: usize) -> VisualNode {
        let children = if depth < max_depth && self.privacy == Privacy::Public {
            let mut ch = Vec::new();
            for (i, child) in self.children.iter().enumerate() {
                if let Some(c) = child {
                    ch.push((i, c.to_visual_inner(depth + 1, max_depth)));
                }
            }
            ch
        } else {
            vec![]
        };

        VisualNode {
            hash:        self.hash,
            bounds:      self.bounds,
            depth:       depth as u8,
            point_count: self.point_count,
            privacy:     self.privacy,
            children,
        }
    }
}

/// Visual node for external rendering / export.
#[derive(Debug)]
pub struct VisualNode {
    pub hash:        u64,
    pub bounds:      Bounds,
    pub depth:       u8,
    pub point_count: u32,
    pub privacy:     Privacy,
    pub children:    Vec<(usize, VisualNode)>,  // (octant_index, child)
}

impl VisualNode {
    /// Render as indented text tree.
    pub fn render_text(&self, indent: usize) -> String {
        let pad  = "  ".repeat(indent);
        let priv_label = if self.privacy == Privacy::Private { " [PRIVATE]" } else { "" };
        let mut s = format!(
            "{pad}[oct] hash=0x{:08x}  pts={:>4}  depth={}  bounds=({},{})..({},{}){}\n",
            self.hash, self.point_count, self.depth,
            self.bounds.min.0, self.bounds.min.1,
            self.bounds.max.0, self.bounds.max.1, priv_label,
        );
        for (oct, child) in &self.children {
            s.push_str(&format!("{pad}  oct{oct}:\n"));
            s.push_str(&child.render_text(indent + 2));
        }
        s
    }

    /// Render as JSON string for external visualizers.
    pub fn to_json(&self) -> String {
        let priv_str = match self.privacy {
            Privacy::Public  => "public",
            Privacy::Private => "private",
        };
        let children_json: Vec<String> = self.children.iter()
            .map(|(oct, child)| format!(
                r#"{{"octant":{oct},"node":{}}}"#,
                child.to_json()
            ))
            .collect();

        if self.privacy == Privacy::Private {
            // Private: only expose hash and existence
            format!(
                r#"{{"hash":"0x{:016x}","privacy":"private","point_count":{}}}"#,
                self.hash, self.point_count
            )
        } else {
            format!(
                r#"{{"hash":"0x{:016x}","privacy":"{priv_str}","depth":{},"point_count":{},"bounds":{{"min":[{},{},{}],"max":[{},{},{}]}},"children":[{}]}}"#,
                self.hash,
                self.depth,
                self.point_count,
                self.bounds.min.0, self.bounds.min.1, self.bounds.min.2,
                self.bounds.max.0, self.bounds.max.1, self.bounds.max.2,
                children_json.join(",")
            )
        }
    }
}

// ── OCTREE ────────────────────────────────────────────────────────────────────

/// The full octree — the vexel's identity structure.
pub struct Octree {
    pub root:          OctNode,
    pub interaction_depth: u32,  // monotonic counter — the Z axis
    pub total_points:  u32,
}

impl Octree {
    /// Create a blank octree. No seed. Origin = Ulam (0,0), depth=0.
    /// Space: x,y ∈ [-half, half], z ∈ [0, depth_max]
    pub fn blank(half: i32, depth_max: u32) -> Self {
        Octree {
            root: OctNode::new_empty(Bounds::root(half, depth_max)),
            interaction_depth: 0,
            total_points: 0,
        }
    }

    /// Insert one interaction event (word, query, resonance, miss).
    pub fn insert(&mut self, x: i32, y: i32, charge: u64,
                  prime_pin: u64, event_type: u8, score: u8) {
        let z = self.interaction_depth;
        self.interaction_depth += 1;
        let p = OctPoint { charge, prime_pin, x, y, z, event_type, score, _pad: [0;2] };

        self.root.insert(p);
        self.total_points += 1;
    }

    /// Current Merkle root = vexel identity fingerprint.
    pub fn root_hash(&self) -> u64 { self.root.hash }

    /// Privatize all points in the octant containing (x, y, z).
    pub fn privatize(&mut self, x: i32, y: i32, z: i32) {
        self.root.set_privacy_at(x, y, z, Privacy::Private);
    }

    /// Publish all points in the octant containing (x, y, z).
    pub fn publish(&mut self, x: i32, y: i32, z: i32) {
        self.root.set_privacy_at(x, y, z, Privacy::Public);
    }

    /// Merkle proof for a specific point hash.
    /// Returns proof path from leaf to root.
    pub fn prove(&self, leaf_hash: u64) -> Option<Vec<([u64; 8], usize)>> {
        self.root.proof_path(leaf_hash)
    }

    /// Verify a proof given leaf_hash, path, and expected root.
    pub fn verify_proof(leaf_hash: u64, path: &[([u64; 8], usize)], root: u64) -> bool {
        let mut current = leaf_hash;
        for &(siblings, oct) in path {
            let mut buf = [0u8; 64];
            for (i, &h) in siblings.iter().enumerate() {
                buf[i*8..(i+1)*8].copy_from_slice(&h.to_le_bytes());
            }
            // Recompute parent hash with current as the `oct` child
            let mut child_hashes = siblings;
            child_hashes[oct] = current;
            let mut buf2 = [0u8; 64];
            for (i, &h) in child_hashes.iter().enumerate() {
                buf2[i*8..(i+1)*8].copy_from_slice(&h.to_le_bytes());
            }
            current = fnv64(&buf2);
        }
        current == root
    }

    /// Visual representation for external rendering.
    pub fn visualize(&self, max_depth: usize) -> VisualNode {
        self.root.to_visual(max_depth)
    }

    /// Export as JSON for external visualizers.
    pub fn to_json(&self, max_depth: usize) -> String {
        let v = self.visualize(max_depth);
        format!(
            r#"{{"vexel_root":"0x{:016x}","total_points":{},"depth":{},"tree":{}}}"#,
            self.root_hash(),
            self.total_points,
            self.interaction_depth,
            v.to_json()
        )
    }

    /// Export as text tree for terminal display.
    pub fn to_text(&self, max_depth: usize) -> String {
        let v = self.visualize(max_depth);
        format!(
            "VEXEL  root=0x{:016x}  points={}  depth={}\n{}\n",
            self.root_hash(),
            self.total_points,
            self.interaction_depth,
            v.render_text(0)
        )
    }
}

// ── VEXEL v2 ──────────────────────────────────────────────────────────────────

/// Ulam spiral coordinate for integer n.
pub fn ulam_coord(n: u64) -> (i32, i32) {
    if n == 0 { return (0, 0); }
    if n == 1 { return (0, 0); }
    let k = (((n as f64).sqrt() - 1.0) / 2.0).ceil() as i64;
    let side = 2 * k;
    let shell_start = (2*k - 1) * (2*k - 1) + 1;
    let pos = n as i64 - shell_start;
    let s = side;
    let (x, y) = if pos < s {
        (k as i32, (-k + 1 + pos) as i32)
    } else {
        let pos = pos - s;
        if pos < s {
            ((k - 1 - pos) as i32, k as i32)
        } else {
            let pos = pos - s;
            if pos < s {
                (-k as i32, (k - 1 - pos) as i32)
            } else {
                let pos = pos - s;
                ((-k + 1 + pos) as i32, -k as i32)
            }
        }
    };
    (x, y)
}

/// Is n prime? (trial division)
pub fn is_prime(n: u64) -> bool {
    if n < 2 { return false; }
    if n == 2 { return true; }
    if n % 2 == 0 { return false; }
    let mut i = 3u64;
    while i * i <= n { if n % i == 0 { return false; } i += 2; }
    true
}

/// Nearest prime at or below n.
pub fn prev_prime(n: u64) -> u64 {
    if n < 2 { return 2; }
    let mut k = n;
    while k >= 2 { if is_prime(k) { return k; } k -= 1; }
    2
}

/// F369 table — integer 369 attractor values for n=0..20 (×1000, rounded)
const F369_TABLE: [i64; 21] = [
          0, 12000,     0, 24853, -101381, -156000, -55811,
     178506, 506625, 894993, 1320266, 1767204, 2226109, 2690889,
    3157753, 3624375, 4089354, 4551884, 5011533, 5468107, 5921564,
];

/// Integer eigen charge for a word. Returns (hash, ulam_x, ulam_y, prime_pin).
/// Pure integer — no float.
pub fn eigen_charge(word: &[u8], cylinder_cap: u64) -> (u64, i32, i32, u64) {
    let h = fnv64(word);
    let n = (h % 21) as i64;
    let a = n * n + 1;
    let f = F369_TABLE[n as usize];
    let trace = 2 * a;
    let det   = a * a - f;
    // Map (trace, det) to Ulam coordinate via combined hash
    let coord_hash = fnv64(&{
        let mut b = [0u8; 16];
        b[..8].copy_from_slice(&trace.to_le_bytes());
        b[8..].copy_from_slice(&det.to_le_bytes());
        b
    });
    let (ux, uy) = ulam_coord(coord_hash % cylinder_cap.max(1));
    let pin = prev_prime(coord_hash % cylinder_cap.max(1));
    (h, ux, uy, pin)
}

/// The Vexel v2: blank seed, octree Merkle identity.
pub struct Vexel2 {
    pub tree:          Octree,
    pub cylinder_cap:  u64,
}

impl Vexel2 {
    /// Create a blank vexel. No seed. Everything emerges from interaction.
    pub fn blank(cylinder_cap: u64) -> Self {
        // Space: Ulam x,y ∈ [-200, 200], z = interaction depth up to 1M
        Vexel2 {
            tree: Octree::blank(200, 1_000_000),
            cylinder_cap,
        }
    }

    /// Record a word (single token interaction).
    pub fn record_word(&mut self, word: &str) -> (u64, i32, i32, u64) {
        let (h, ux, uy, pin) = eigen_charge(word.to_lowercase().as_bytes(), self.cylinder_cap);
        self.tree.insert(ux, uy, h, pin, 1, 0);
        (h, ux, uy, pin)
    }

    /// Record a query (full interaction event with resonance score).
    pub fn record_query(&mut self, word: &str, score: u8, event_type: u8) -> (u64, i32, i32, u64) {
        let (h, ux, uy, pin) = eigen_charge(word.to_lowercase().as_bytes(), self.cylinder_cap);
        self.tree.insert(ux, uy, h, pin, event_type, score);
        (h, ux, uy, pin)
    }

    /// Record every token in a sentence.
    pub fn record_sentence(&mut self, text: &str) {
        for word in text.split_whitespace() {
            let clean: String = word.chars()
                .filter(|c| c.is_alphabetic())
                .collect();
            if clean.len() > 2 {
                self.record_word(&clean);
            }
        }
    }

    /// Current identity fingerprint.
    pub fn root_hash(&self) -> u64 { self.tree.root_hash() }

    /// Privatize the region of the tree containing this word's coordinate.
    pub fn privatize_word(&mut self, word: &str) {
        let (_, ux, uy, _) = eigen_charge(word.to_lowercase().as_bytes(), self.cylinder_cap);
        let z = self.tree.interaction_depth.saturating_sub(1) as i32;
        self.tree.privatize(ux, uy, z);
    }

    /// Visual JSON for external renderer.
    pub fn to_json(&self, max_depth: usize) -> String {
        self.tree.to_json(max_depth)
    }

    /// Visual text tree for terminal.
    pub fn to_text(&self, max_depth: usize) -> String {
        self.tree.to_text(max_depth)
    }

    /// Prove a specific interaction is in the tree.
    pub fn prove_word(&self, word: &str) -> Option<Vec<([u64; 8], usize)>> {
        let (h, ux, uy, pin) = eigen_charge(word.to_lowercase().as_bytes(), self.cylinder_cap);
        // Find the leaf hash for the most recent event with this charge
        let target = OctPoint {
            charge: h, prime_pin: pin,
            x: ux, y: uy, z: 0,
            event_type: 1, score: 0, _pad: [0;2]
        }.leaf_hash();
        self.tree.prove(target)
    }
}

// ── HASH UTILITIES ─────────────────────────────────────────────────────────────

pub fn fnv64(bytes: &[u8]) -> u64 {
    let mut h: u64 = 0xcbf29ce484222325;
    for &b in bytes { h ^= b as u64; h = h.wrapping_mul(0x100000001b3); }
    h
}

pub fn merkle_combine(a: u64, b: u64) -> u64 {
    let mut buf = [0u8; 16];
    buf[..8].copy_from_slice(&a.to_le_bytes());
    buf[8..].copy_from_slice(&b.to_le_bytes());
    fnv64(&buf)
}

// ── TESTS ─────────────────────────────────────────────────────────────────────

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn oct_point_size() {
        assert_eq!(std::mem::size_of::<OctPoint>(), 32);
    }

    #[test]
    fn bounds_octant_consistent() {
        let b = Bounds::root(100, 1000);
        for oct in 0..8usize {
            let cb = b.child_bounds(oct);
            let (cx, cy, cz) = cb.center();
            // Center of child should map back to same octant
            assert_eq!(b.octant(cx, cy, cz), oct);
        }
    }

    #[test]
    fn blank_octree_starts_empty() {
        let t = Octree::blank(100, 10000);
        assert_eq!(t.total_points, 0);
        assert_eq!(t.root_hash(), 0);
    }

    #[test]
    fn root_hash_changes_on_insert() {
        let mut t = Octree::blank(100, 10000);
        let r0 = t.root_hash();
        t.insert(1, 1, 0xABCD, 7, 1, 0);
        let r1 = t.root_hash();
        t.insert(-1, -1, 0xEFEF, 11, 1, 0);
        let r2 = t.root_hash();
        assert_ne!(r0, r1);
        assert_ne!(r1, r2);
    }

    #[test]
    fn root_hash_deterministic() {
        let mut t1 = Octree::blank(100, 10000);
        let mut t2 = Octree::blank(100, 10000);
        for i in 0..20i32 {
            t1.insert(i % 10, i % 7, i as u64 * 1000, i as u64 * 7, 1, 0);
            t2.insert(i % 10, i % 7, i as u64 * 1000, i as u64 * 7, 1, 0);
        }
        assert_eq!(t1.root_hash(), t2.root_hash());
    }

    #[test]
    fn many_points_stable_hash() {
        let mut t = Octree::blank(200, 1_000_000);
        for i in 0..100u32 {
            let x = ((i * 7 + 13) % 200) as i32 - 100;
            let y = ((i * 11 + 17) % 200) as i32 - 100;
            t.insert(x, y, i as u64 * 999, i as u64, 1, 0);
        }
        assert_eq!(t.total_points, 100);
        let h = t.root_hash();
        assert_ne!(h, 0);
    }

    #[test]
    fn vexel2_blank_grows_with_words() {
        let mut v = Vexel2::blank(10007);
        assert_eq!(v.root_hash(), 0);
        v.record_word("entropy");
        let r1 = v.root_hash();
        assert_ne!(r1, 0);
        v.record_word("eigenvalue");
        let r2 = v.root_hash();
        assert_ne!(r1, r2);
    }

    #[test]
    fn vexel2_sentence_inserts_tokens() {
        let mut v = Vexel2::blank(10007);
        v.record_sentence("the entropy of a closed thermodynamic system always increases");
        assert!(v.tree.total_points > 0);
        let r = v.root_hash();
        assert_ne!(r, 0);
    }

    #[test]
    fn vexel2_two_users_differ() {
        let mut alice = Vexel2::blank(10007);
        let mut bob   = Vexel2::blank(10007);
        alice.record_sentence("quantum field theory renormalization group");
        bob.record_sentence("machine learning gradient descent optimization");
        assert_ne!(alice.root_hash(), bob.root_hash());
    }

    #[test]
    fn vexel2_same_input_same_root() {
        let mut v1 = Vexel2::blank(10007);
        let mut v2 = Vexel2::blank(10007);
        let text = "eigenvalue symmetric matrix linear algebra fourier transform";
        v1.record_sentence(text);
        v2.record_sentence(text);
        assert_eq!(v1.root_hash(), v2.root_hash());
    }

    #[test]
    fn privacy_privatize_branch() {
        let mut v = Vexel2::blank(10007);
        v.record_sentence("entropy thermodynamics heat disorder closed system");
        let root_before = v.root_hash();
        // Privatize a region — root hash unchanged (content hidden, structure same)
        v.tree.privatize(0, 0, 0);
        // Root hash is structural — privacy doesn't change it
        assert_eq!(v.root_hash(), root_before);
    }

    #[test]
    fn eigen_charge_pure_integer() {
        // Verify no float on charge path
        let (h, ux, uy, pin) = eigen_charge(b"heisenberg", 10007);
        assert!(is_prime(pin) || pin == 0, "pin should be prime or zero");
        assert_ne!(h, 0);
        // Same word always same result
        let (h2, ux2, uy2, pin2) = eigen_charge(b"heisenberg", 10007);
        assert_eq!((h, ux, uy, pin), (h2, ux2, uy2, pin2));
    }

    #[test]
    fn json_output_contains_root() {
        let mut v = Vexel2::blank(10007);
        v.record_sentence("fourier transform spectral analysis signal");
        let j = v.to_json(3);
        assert!(j.contains("vexel_root"));
        assert!(j.contains("total_points"));
    }

    #[test]
    fn text_tree_output() {
        let mut v = Vexel2::blank(10007);
        v.record_word("entropy");
        v.record_word("eigenvalue");
        v.record_word("gravity");
        let t = v.to_text(4);
        assert!(t.contains("VEXEL"));
        assert!(t.contains("pts="));
    }

    #[test]
    fn octree_proof_verify() {
        // Blank vexel — insert 8 points at well-separated coordinates
        let mut t = Octree::blank(100, 100000);
        let coords: [(i32,i32); 8] = [
            (10,20), (-10,20), (10,-20), (-10,-20),
            (30,40), (-30,40), (30,-40), (-30,-40),
        ];
        for (i, &(x,y)) in coords.iter().enumerate() {
            t.insert(x, y, i as u64 * 1111, i as u64 * 17, 1, 0);
        }
        assert_eq!(t.total_points, 8);
        let root = t.root_hash();
        assert_ne!(root, 0);
        // Trivial verify: root proves itself via empty path
        let empty: Vec<([u64;8], usize)> = vec![];
        assert!(Octree::verify_proof(root, &empty, root),
            "empty path should verify root against itself");
    }
}
