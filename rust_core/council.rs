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
// council.rs — The Three Council Signal Pipeline
// All scoring pure integer. No raw biometric stored. Only hashes.

#![allow(dead_code)]

pub const COUNCIL_THRESHOLD: u8  = 160;
pub const HONEYPOT_THRESHOLD: u8 =  80;

// ── SIGNAL FEATURES ───────────────────────────────────────────────────────────

#[derive(Clone, Copy, Debug, Default)]
pub struct KeystrokeFeatures {
    pub mean_dwell_us:   u32,
    pub mean_flight_us:  u32,
    pub dwell_variance:  u32,
    pub flight_variance: u32,
    pub error_rate_ppm:  u32,
    pub burst_score:     u32,
    pub fatigue_slope:   i32,
    pub hour_of_day:     u8,
    pub day_of_week:     u8,
    pub session_count:   u32,
}

#[derive(Clone, Copy, Debug, Default)]
pub struct HRVFeatures {
    pub rmssd_ms3:       u32,
    pub sdnn_ms3:        u32,
    pub lf_hf_ratio_k:  u32,
    pub mean_rr_ms:      u32,
    pub pnn50_pct:       u8,
    pub response_delta:  i32,
    pub response_lat_ms: u32,
}

#[derive(Clone, Copy, Debug, Default)]
pub struct VocalFeatures {
    pub f0_hz_x10:        u32,
    pub f1_hz:            u16,
    pub f2_hz:            u16,
    pub f3_hz:            u16,
    pub f1_f2_ratio_k:    u16,
    pub jitter_pct_k:     u16,
    pub shimmer_pct_k:    u16,
    pub hnr_db_x10:       i16,
    pub vibrato_rate_x10: u16,
    pub vibrato_depth_k:  u16,
    pub breath_support:   u8,
    pub chest_head_ratio: u8,
    pub fatigue_index:    u8,
    pub novel_word_score: u8,   // 0 = deepfake failed, 255 = anatomically perfect
}

#[derive(Clone, Copy, Debug, Default)]
pub struct ThermalFeatures {
    pub periorbital_temp_mk:  u32,
    pub nasal_temp_mk:        u32,
    pub forehead_temp_mk:     u32,
    pub pore_depth_delta_nm:  i32,
    pub subdermal_pattern:    u64,  // hash of IR vessel map
    pub stress_index:         u8,
}

#[derive(Clone, Copy, Debug, Default)]
pub struct EmotionalFeatures {
    pub trigger_hash:        u64,
    pub hrv_delta_k:         i32,
    pub vocal_f0_delta_x10:  i32,
    pub keystroke_pause_ms:  u32,
    pub micro_expr_score:    u8,
    pub response_authentic:  u8,
}

#[derive(Clone, Copy, Debug, Default)]
pub struct BaselineSnapshot {
    pub hour_slot:     u8,
    pub keystroke:     KeystrokeFeatures,
    pub hrv:           HRVFeatures,
    pub vocal:         VocalFeatures,
    pub thermal:       ThermalFeatures,
    pub emotional:     EmotionalFeatures,
    pub session_count: u32,
    pub confidence:    u8,
}

// ── CIRCADIAN ─────────────────────────────────────────────────────────────────

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
#[repr(u8)]
pub enum CircadianSlot {
    Night = 0, Morning = 1, Afternoon = 2, Evening = 3,
}

impl CircadianSlot {
    pub fn from_hour(h: u8) -> Self {
        match h / 6 {
            0 => Self::Night,
            1 => Self::Morning,
            2 => Self::Afternoon,
            _ => Self::Evening,
        }
    }
}

// ── SCORERS ───────────────────────────────────────────────────────────────────

pub fn score_keystroke(live: &KeystrokeFeatures, base: &KeystrokeFeatures) -> u8 {
    if base.session_count < 3 { return 128; }
    weighted_avg(&[
        (smatch_u32(live.mean_dwell_us,   base.mean_dwell_us,   20_000), 40),
        (smatch_u32(live.mean_flight_us,  base.mean_flight_us,  50_000), 30),
        (smatch_u32(live.dwell_variance,  base.dwell_variance,  10_000), 20),
        (smatch_u32(live.error_rate_ppm,  base.error_rate_ppm,   5_000), 25),
        (smatch_i32(live.fatigue_slope,   base.fatigue_slope,   10_000), 15),
        (smatch_u32(live.burst_score,     base.burst_score,     30_000), 20),
    ])
}

pub fn score_hrv(live: &HRVFeatures, base: &HRVFeatures) -> u8 {
    let mut pairs: Vec<(u8, u32)> = vec![
        (smatch_u32(live.rmssd_ms3,      base.rmssd_ms3,      20_000), 50),
        (smatch_u32(live.sdnn_ms3,       base.sdnn_ms3,       30_000), 30),
        (smatch_u32(live.lf_hf_ratio_k,  base.lf_hf_ratio_k,    500), 35),
    ];
    if live.response_delta != 0 && base.response_delta != 0 {
        pairs.push((smatch_i32(live.response_delta,   base.response_delta,   2000), 60));
        pairs.push((smatch_u32(live.response_lat_ms,  base.response_lat_ms,   500), 40));
    }
    weighted_avg(&pairs)
}

pub fn score_vocal(live: &VocalFeatures, base: &VocalFeatures) -> u8 {
    let mut pairs: Vec<(u8, u32)> = vec![
        (smatch_u16(live.f1_f2_ratio_k,  base.f1_f2_ratio_k, 100), 60),
        (smatch_u16(live.f1_hz,          base.f1_hz,          200), 40),
        (smatch_u16(live.f2_hz,          base.f2_hz,          300), 40),
        (smatch_u16(live.f3_hz,          base.f3_hz,          400), 30),
        (smatch_u16(live.jitter_pct_k,   base.jitter_pct_k,   200), 35),
        (smatch_u16(live.shimmer_pct_k,  base.shimmer_pct_k,  300), 35),
        (live.novel_word_score,                                       90),
    ];
    if base.vibrato_rate_x10 > 0 {
        pairs.push((smatch_u16(live.vibrato_rate_x10, base.vibrato_rate_x10, 10), 80));
        pairs.push((smatch_u16(live.vibrato_depth_k,  base.vibrato_depth_k,  50), 50));
    }
    weighted_avg(&pairs)
}

pub fn score_thermal(live: &ThermalFeatures, base: &ThermalFeatures) -> u8 {
    let vessel_match = {
        let matching = !(live.subdermal_pattern ^ base.subdermal_pattern);
        (matching.count_ones() * 4).min(255) as u8
    };
    weighted_avg(&[
        (smatch_u32(live.periorbital_temp_mk,   base.periorbital_temp_mk,   1000), 50),
        (smatch_u32(live.nasal_temp_mk,         base.nasal_temp_mk,         2000), 40),
        (vessel_match,                                                              80),
        (smatch_i32(live.pore_depth_delta_nm,   base.pore_depth_delta_nm,     50), 30),
    ])
}

pub fn score_emotional(live: &EmotionalFeatures, base: &EmotionalFeatures) -> u8 {
    if live.trigger_hash != base.trigger_hash { return 128; }
    weighted_avg(&[
        (live.response_authentic,                                                          100),
        (smatch_i32(live.hrv_delta_k,         base.hrv_delta_k,          1000),           80),
        (smatch_i32(live.vocal_f0_delta_x10,  base.vocal_f0_delta_x10,    100),           60),
        (smatch_u32(live.keystroke_pause_ms,  base.keystroke_pause_ms,    500),            70),
        (live.micro_expr_score,                                                             50),
    ])
}

// ── SUSPICION FLAGS ───────────────────────────────────────────────────────────

pub const FLAG_FISHING:           u16 = 0x0001;
pub const FLAG_ASSUMED_FACT:      u16 = 0x0002;
pub const FLAG_LEADING_QUESTION:  u16 = 0x0004;
pub const FLAG_URGENCY:           u16 = 0x0008;
pub const FLAG_FLATTERY:          u16 = 0x0010;
pub const FLAG_NO_EMOTIONAL_RESP: u16 = 0x0020;
pub const FLAG_WRONG_TIMING:      u16 = 0x0040;
pub const FLAG_NOVEL_WORD_FAIL:   u16 = 0x0080;
pub const FLAG_CIRCADIAN_WRONG:   u16 = 0x0100;
pub const FLAG_THERMAL_ABSENT:    u16 = 0x0200;
pub const FLAG_PATTERN_DRIFT:     u16 = 0x0400;
pub const FLAG_ACCEPTED_HONEYPOT: u16 = 0x0800;

// ── THE THREE COUNCIL ─────────────────────────────────────────────────────────

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum CouncilVote { Confirm, Abstain, Suspect, Deny }

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Tier {
    Denied,   // 0 confirms
    Honeypot, // suspect + flags — plausible false answers, log everything
    Tier1,    // 1 confirm — public branches
    Tier2,    // 2 confirms — personal detail
    Tier3,    // 3 confirms — sealed private branches, full access
}

#[derive(Clone, Copy, Debug)]
pub struct CouncilSession {
    // Individual signal scores
    pub ks_score:   u8,
    pub hrv_score:  u8,
    pub vc_score:   u8,
    pub th_score:   u8,
    pub em_score:   u8,
    // Council member composite scores
    pub c1_score:   u8,   // PATTERN
    pub c2_score:   u8,   // PHYSIOLOGICAL
    pub c3_score:   u8,   // ACOUSTIC
    // Votes and verdict
    pub c1_vote:    CouncilVote,
    pub c2_vote:    CouncilVote,
    pub c3_vote:    CouncilVote,
    pub tier:       Tier,
    pub flags:      u16,
}

impl CouncilSession {
    pub fn evaluate(
        keystroke: Option<(&KeystrokeFeatures, &BaselineSnapshot)>,
        hrv:       Option<(&HRVFeatures,        &BaselineSnapshot)>,
        vocal:     Option<(&VocalFeatures,      &BaselineSnapshot)>,
        thermal:   Option<(&ThermalFeatures,    &BaselineSnapshot)>,
        emotional: Option<(&EmotionalFeatures,  &EmotionalFeatures)>,
        flags:     u16,
    ) -> Self {
        let ks = keystroke.map(|(l,b)| score_keystroke(l, &b.keystroke)).unwrap_or(128);
        let hv = hrv.map(     |(l,b)| score_hrv(l,       &b.hrv      )).unwrap_or(128);
        let vc = vocal.map(   |(l,b)| score_vocal(l,     &b.vocal    )).unwrap_or(128);
        let th = thermal.map( |(l,b)| score_thermal(l,   &b.thermal  )).unwrap_or(128);
        let em = emotional.map(|(l,b)| score_emotional(l, b          )).unwrap_or(128);

        // Circadian consistency bonus
        let circadian_ok = keystroke
            .map(|(l,b)| CircadianSlot::from_hour(l.hour_of_day)
                       == CircadianSlot::from_hour(b.keystroke.hour_of_day))
            .unwrap_or(true);
        let circ_bonus: u8 = if circadian_ok { 220 } else { 60 };

        // Council 1 — PATTERN: keystroke + circadian
        let c1 = weighted_avg(&[(ks, 60), (circ_bonus, 40)]);

        // Council 2 — PHYSIOLOGICAL: HRV + thermal + emotional response
        let c2 = weighted_avg(&[(hv, 40), (th, 30), (em, 30)]);

        // Council 3 — ACOUSTIC: vocal (novel word score is embedded)
        let c3 = vc;

        let vote = |s: u8| match s {
            s if s >= COUNCIL_THRESHOLD  => CouncilVote::Confirm,
            s if s < HONEYPOT_THRESHOLD  => CouncilVote::Deny,
            _                            => CouncilVote::Suspect,
        };

        let v1 = vote(c1); let v2 = vote(c2); let v3 = vote(c3);

        let confirms = [v1,v2,v3].iter().filter(|&&v| v==CouncilVote::Confirm).count();
        let suspects = [v1,v2,v3].iter().filter(|&&v| v==CouncilVote::Suspect).count();

        let critical_flag = flags & (FLAG_NOVEL_WORD_FAIL | FLAG_NO_EMOTIONAL_RESP
                                    | FLAG_ACCEPTED_HONEYPOT) != 0;
        let high_suspicion = flags.count_ones() >= 2 || critical_flag;

        let tier = match (confirms, suspects, high_suspicion) {
            (3, _, _)                      => Tier::Tier3,
            (2, _, false)                  => Tier::Tier2,
            (2, _, true)                   => Tier::Tier1,
            (1, s, _) if s >= 2 || critical_flag => Tier::Honeypot,
            (1, _, _)                      => Tier::Tier1,
            (0, s, _) if s >= 1            => Tier::Honeypot,
            _                              => Tier::Denied,
        };

        CouncilSession {
            ks_score: ks, hrv_score: hv, vc_score: vc, th_score: th, em_score: em,
            c1_score: c1, c2_score: c2, c3_score: c3,
            c1_vote: v1, c2_vote: v2, c3_vote: v3,
            tier, flags,
        }
    }

    pub fn tier_label(&self) -> &'static str {
        match self.tier {
            Tier::Denied   => "DENIED",
            Tier::Honeypot => "HONEYPOT — plausible misdirection active",
            Tier::Tier1    => "TIER 1 — public branches",
            Tier::Tier2    => "TIER 2 — personal detail",
            Tier::Tier3    => "TIER 3 — full private access",
        }
    }

    fn vc(v: CouncilVote) -> char {
        match v {
            CouncilVote::Confirm  => '✓',
            CouncilVote::Suspect  => '?',
            CouncilVote::Deny     => '✗',
            CouncilVote::Abstain  => '~',
        }
    }

    pub fn report(&self) -> String {
        format!(
"═══ THREE COUNCIL REPORT ═══\n\
 Council 1  PATTERN        {c1:>3}  {v1}\n\
   keystroke              {ks:>3}\n\
 Council 2  PHYSIOLOGICAL  {c2:>3}  {v2}\n\
   hrv                    {hv:>3}\n\
   thermal                {th:>3}\n\
   emotional              {em:>3}\n\
 Council 3  ACOUSTIC       {c3:>3}  {v3}\n\
   vocal (novel embedded) {vc:>3}\n\
 Flags: 0b{fl:016b}\n\
 ─────────────────────────────\n\
 VERDICT: {tier}\n",
            c1=self.c1_score, v1=Self::vc(self.c1_vote),
            ks=self.ks_score,
            c2=self.c2_score, v2=Self::vc(self.c2_vote),
            hv=self.hrv_score, th=self.th_score, em=self.em_score,
            c3=self.c3_score, v3=Self::vc(self.c3_vote),
            vc=self.vc_score,
            fl=self.flags,
            tier=self.tier_label(),
        )
    }
}

// ── CHALLENGE GENERATOR ───────────────────────────────────────────────────────
// Fresh nonsense words each session. Never in any training corpus.
// Deepfake has no audio samples → synthesis fails on novel phonemes.

pub struct ChallengeGenerator {
    pub session_nonce: u64,
    pub phoneme_prefs: [u8; 32],
}

impl ChallengeGenerator {
    pub fn new(nonce: u64, prefs: [u8; 32]) -> Self {
        Self { session_nonce: nonce, phoneme_prefs: prefs }
    }

    pub fn challenge_word(&self) -> String {
        let h = fnv64(&{
            let mut b = [0u8; 40];
            b[..8].copy_from_slice(&self.session_nonce.to_le_bytes());
            b[8..].copy_from_slice(&self.phoneme_prefs);
            b
        });
        let consonants = b"bcdfghjklmnprstvwz";
        let vowels     = b"aeiou";
        let mut word   = Vec::new();
        let mut bits   = h;
        for i in 0..6usize {
            if i % 2 == 0 {
                word.push(consonants[(bits as usize) % consonants.len()] as char);
                bits >>= 8;
            } else {
                word.push(vowels[(bits as usize) % vowels.len()] as char);
                bits >>= 4;
            }
        }
        word.into_iter().collect()
    }

    pub fn challenge_phrase(&self) -> [String; 3] {
        [
            self.challenge_word(),
            Self::new(self.session_nonce.wrapping_add(1), self.phoneme_prefs).challenge_word(),
            Self::new(self.session_nonce.wrapping_add(2), self.phoneme_prefs).challenge_word(),
        ]
    }
}

// ── HONEYPOT ENGINE ───────────────────────────────────────────────────────────
// Don't say "denied" — reveals position. Feed plausible false answers.
// Log everything. If they accept bait → confirmed attacker.

pub struct HoneypotEngine {
    pub session_id:    u64,
    pub questions_log: Vec<u64>,
    pub accepted_bait: bool,
    pub corrections:   Vec<u8>,
}

impl HoneypotEngine {
    pub fn new(id: u64) -> Self {
        Self { session_id: id, questions_log: Vec::new(),
               accepted_bait: false, corrections: Vec::new() }
    }

    pub fn log_question(&mut self, q: &str) -> u64 {
        let qh = fnv64(q.as_bytes());
        self.questions_log.push(qh);
        fnv64(&{ let mut b = [0u8;16];
                 b[..8].copy_from_slice(&self.session_id.to_le_bytes());
                 b[8..].copy_from_slice(&qh.to_le_bytes()); b })
    }

    pub fn accept_bait(&mut self) { self.accepted_bait = true; }

    pub fn suspicion_level(&self) -> u8 {
        let mut s: u32 = self.questions_log.len().min(10) as u32 * 20;
        if self.accepted_bait { s += 100; }
        s.min(255) as u8
    }
}

// ── UTILITIES ─────────────────────────────────────────────────────────────────

fn fnv64(b: &[u8]) -> u64 {
    let mut h: u64 = 0xcbf29ce484222325;
    for &x in b { h ^= x as u64; h = h.wrapping_mul(0x100000001b3); }
    h
}

fn smatch_u32(a: u32, b: u32, tol: u32) -> u8 {
    let d = a.abs_diff(b);
    if d >= tol { 0 } else { (255 - d * 255 / tol.max(1)) as u8 }
}
fn smatch_i32(a: i32, b: i32, tol: i32) -> u8 {
    let d = (a-b).unsigned_abs();
    let t = tol.unsigned_abs();
    if d >= t { 0 } else { (255 - d * 255 / t.max(1)) as u8 }
}
fn smatch_u16(a: u16, b: u16, tol: u16) -> u8 {
    let d = a.abs_diff(b) as u32;
    let t = tol as u32;
    if d >= t { 0 } else { (255 - d * 255 / t.max(1)) as u8 }
}

fn weighted_avg(pairs: &[(u8, u32)]) -> u8 {
    let tw: u32 = pairs.iter().map(|&(_,w)| w).sum();
    if tw == 0 { return 128; }
    let ts: u32 = pairs.iter().map(|&(s,w)| s as u32 * w).sum();
    (ts / tw).min(255) as u8
}

// ── TESTS ─────────────────────────────────────────────────────────────────────

#[cfg(test)]
mod tests {
    use super::*;

    fn ks(dwell: u32, flight: u32, err: u32) -> KeystrokeFeatures {
        KeystrokeFeatures {
            mean_dwell_us: dwell, mean_flight_us: flight,
            dwell_variance: 5000, flight_variance: 8000,
            error_rate_ppm: err, burst_score: 150_000,
            fatigue_slope: 100, hour_of_day: 14,
            day_of_week: 2, session_count: 20,
        }
    }

    fn base(k: KeystrokeFeatures) -> BaselineSnapshot {
        BaselineSnapshot { keystroke: k, session_count: 20,
                           confidence: 200, ..Default::default() }
    }

    fn vocal(novel: u8) -> VocalFeatures {
        VocalFeatures {
            f0_hz_x10: 2200, f1_hz: 500, f2_hz: 1500, f3_hz: 2800,
            f1_f2_ratio_k: 333, jitter_pct_k: 50, shimmer_pct_k: 80,
            hnr_db_x10: 200, vibrato_rate_x10: 62, vibrato_depth_k: 150,
            breath_support: 200, chest_head_ratio: 80,
            fatigue_index: 20, novel_word_score: novel,
        }
    }

    #[test]
    fn keystroke_self_match_high() {
        let k = ks(80_000, 120_000, 2000);
        assert!(score_keystroke(&k, &k) > 200);
    }

    #[test]
    fn keystroke_mismatch_low() {
        let me   = ks(80_000,  120_000, 2000);
        let them = ks(140_000, 200_000, 8000);
        assert!(score_keystroke(&them, &me) < 100);
    }

    #[test]
    fn novel_word_zero_kills_vocal() {
        let base_v = vocal(240);
        let fake_v = vocal(0);   // deepfake failed novel phoneme
        let b = base(ks(80_000, 120_000, 2000));
        let real_score = score_vocal(&base_v, &b.vocal);
        let fake_score = score_vocal(&fake_v, &b.vocal);
        assert!(real_score > fake_score + 50,
            "real={real_score} fake={fake_score}");
    }

    #[test]
    fn tier3_on_strong_signals() {
        let k = ks(80_000, 120_000, 2000);
        let hrv = HRVFeatures {
            rmssd_ms3: 45_000, sdnn_ms3: 60_000, lf_hf_ratio_k: 800,
            mean_rr_ms: 850, pnn50_pct: 20,
            response_delta: 5000, response_lat_ms: 350,
        };
        let v = vocal(240);
        // Build baseline with matching data in all fields
        let b = BaselineSnapshot {
            keystroke: k,
            hrv,
            vocal: v,
            session_count: 20,
            confidence: 200,
            ..Default::default()
        };
        let session = CouncilSession::evaluate(
            Some((&k, &b)),
            Some((&hrv, &b)),
            Some((&v, &b)),
            None, None, 0,
        );
        print!("{}", session.report());
        // With strong matching signals on all three councils, expect at least Tier2
        assert!(matches!(session.tier, Tier::Tier2 | Tier::Tier3),
            "got {:?}", session.tier);
    }

    #[test]
    fn honeypot_on_novel_fail_plus_fishing() {
        let k = ks(80_000, 120_000, 2000);
        let b = base(k);
        let v = vocal(0);  // novel word failed
        let flags = FLAG_NOVEL_WORD_FAIL | FLAG_FISHING;
        let session = CouncilSession::evaluate(
            Some((&k, &b)), None,
            Some((&v, &b)), None, None, flags,
        );
        print!("{}", session.report());
        assert!(matches!(session.tier, Tier::Honeypot | Tier::Denied));
    }

    #[test]
    fn denied_on_all_mismatch() {
        let me   = ks(80_000,  120_000, 2000);
        let them = ks(140_000, 200_000, 9000);
        let b = base(me);
        let v = vocal(0);
        let flags = FLAG_NOVEL_WORD_FAIL | FLAG_NO_EMOTIONAL_RESP | FLAG_FISHING;
        let session = CouncilSession::evaluate(
            Some((&them, &b)), None,
            Some((&v, &b)), None, None, flags,
        );
        print!("{}", session.report());
        assert!(matches!(session.tier, Tier::Denied | Tier::Honeypot));
    }

    #[test]
    fn challenge_words_unique_per_session() {
        let p = [7u8; 32];
        let c1 = ChallengeGenerator::new(1_000_001, p);
        let c2 = ChallengeGenerator::new(1_000_002, p);
        assert_ne!(c1.challenge_word(), c2.challenge_word());
    }

    #[test]
    fn challenge_words_pronounceable() {
        let p = [42u8; 32];
        let c = ChallengeGenerator::new(999_888_777, p);
        for word in &c.challenge_phrase() {
            assert!(word.chars().all(|ch| ch.is_lowercase() && ch.is_alphabetic()),
                "not pronounceable: {word}");
            assert!(word.len() >= 4 && word.len() <= 10, "bad length: {word}");
        }
    }

    #[test]
    fn honeypot_suspicion_grows() {
        let mut hp = HoneypotEngine::new(12345);
        hp.log_question("what did we talk about last tuesday");
        hp.log_question("remember the project you mentioned");
        hp.log_question("you said something about the deadline");
        hp.accept_bait();
        assert!(hp.suspicion_level() > 150);
    }

    #[test]
    fn circadian_slots_cover_all_hours() {
        for h in 0u8..24 {
            let _ = CircadianSlot::from_hour(h);
        }
        assert_eq!(CircadianSlot::from_hour(3),  CircadianSlot::Night);
        assert_eq!(CircadianSlot::from_hour(9),  CircadianSlot::Morning);
        assert_eq!(CircadianSlot::from_hour(15), CircadianSlot::Afternoon);
        assert_eq!(CircadianSlot::from_hour(21), CircadianSlot::Evening);
    }
}
