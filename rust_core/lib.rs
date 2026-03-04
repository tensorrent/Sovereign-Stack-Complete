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
//! TRINITY CORE — Bind · Rotate · Align
//! ======================================
//! 91-line Rust kernel replacing the Python tensor ops.
//! Zero-alloc hot path. f64 precision. SIMD-ready layout.
//!
//! f(t) = e^(-γ(t-t₀)²) · e^(iωt)
//!
//! Author: Brad Wallace

#![allow(dead_code)]

// use std::f64::consts::PI;  // reserved for future extensions

// ── Complex f64 (inline, no external crate) ────────────────────────
#[derive(Clone, Copy, Debug, PartialEq)]
#[repr(C)]
pub struct C64 {
    pub re: f64,
    pub im: f64,
}

impl C64 {
    #[inline]
    pub const fn new(re: f64, im: f64) -> Self {
        Self { re, im }
    }
    #[inline]
    pub fn mag2(self) -> f64 {
        self.re * self.re + self.im * self.im
    }
    #[inline]
    pub fn mag(self) -> f64 {
        self.mag2().sqrt()
    }
    #[inline]
    pub fn phase(self) -> f64 {
        self.im.atan2(self.re)
    }
    #[inline]
    pub fn mul(self, o: Self) -> Self {
        Self::new(
            self.re * o.re - self.im * o.im,
            self.re * o.im + self.im * o.re,
        )
    }
    #[inline]
    pub fn scale(self, s: f64) -> Self {
        Self::new(self.re * s, self.im * s)
    }
}

// ── UTSL Coordinate (24 bytes, Copy) ───────────────────────────────
#[derive(Clone, Copy, Debug)]
#[repr(C)]
pub struct Coord {
    pub t0:    f64,   // temporal centre
    pub freq:  f64,   // carrier frequency  (ω)
    pub width: f64,   // Gaussian width     (γ)
}

// ── The 3 Ops ──────────────────────────────────────────────────────
#[inline]
pub fn bind(x: f64, width: f64) -> f64 {
    (-width * x * x).exp()
}
#[inline]
pub fn rotate(x: f64, freq: f64) -> C64 {
    let (s, c) = (freq * x).sin_cos();
    C64::new(c, s)
}
#[inline]
pub fn align(x: f64, shift: f64) -> f64 {
    x - shift
}

/// Materialize a single sample: `e^{-γ(t-t₀)²} · e^{iω(t-t₀)}`
#[inline]
pub fn materialize(t: f64, c: &Coord) -> C64 {
    let dt = align(t, c.t0);
    rotate(dt, c.freq).scale(bind(dt, c.width))
}

// ── Buffer render (hot loop) ───────────────────────────────────────
/// Fill `out[0..n]` with the materialized wave packet.
/// `t_min..t_max` is linearly spaced across `n` samples.
pub fn render(c: &Coord, t_min: f64, t_max: f64, out: &mut [C64]) {
    let n = out.len();
    if n == 0 {
        return;
    }
    let step = (t_max - t_min) / (n as f64 - 1.0).max(1.0);
    for i in 0..n {
        let t = t_min + step * i as f64;
        out[i] = materialize(t, c);
    }
}

/// Total energy: Σ |f(t)|²
pub fn energy(buf: &[C64]) -> f64 {
    buf.iter().map(|z| z.mag2()).sum()
}

// ── Physics parity check ───────────────────────────────────────────
pub fn verify() -> (bool, f64) {
    let c = Coord {
        t0:    0.0,
        freq:  10.0,
        width: 0.5,
    };
    let mut buf = [C64::new(0.0, 0.0); 1000];
    render(&c, -5.0, 5.0, &mut buf);
    let mut max_err: f64 = 0.0;
    let step = 10.0 / 999.0;
    for i in 0..1000 {
        let t = -5.0 + step * i as f64;
        let gt = C64::new(
            (-0.5 * t * t).exp() * (10.0 * t).cos(),
            (-0.5 * t * t).exp() * (10.0 * t).sin(),
        );
        let dr = (buf[i].re - gt.re).abs();
        let di = (buf[i].im - gt.im).abs();
        let err = dr.max(di);
        if err > max_err {
            max_err = err;
        }
    }
    (max_err < 1e-14, max_err)
}

// ═══════════════════════════════════════════════════════════════════
// TEST SUITE
// ═══════════════════════════════════════════════════════════════════
#[cfg(test)]
mod tests {
    use super::*;
    use std::f64::consts::PI;

    const EPS: f64 = 1e-14;   // physics parity threshold
    const LOOSE: f64 = 1e-10; // analytical approximation threshold

    // ── C64 arithmetic ────────────────────────────────────────────
    #[test]
    fn c64_new_stores_components() {
        let z = C64::new(3.0, -4.0);
        assert_eq!(z.re, 3.0);
        assert_eq!(z.im, -4.0);
    }

    #[test]
    fn c64_mag2_pythagorean() {
        let z = C64::new(3.0, 4.0);
        assert!((z.mag2() - 25.0).abs() < EPS);
        assert!((z.mag()  -  5.0).abs() < EPS);
    }

    #[test]
    fn c64_mag2_avoids_sqrt_for_zero() {
        let z = C64::new(0.0, 0.0);
        assert_eq!(z.mag2(), 0.0);
        assert_eq!(z.mag(),  0.0);
    }

    #[test]
    fn c64_phase_unit_circle_quadrants() {
        assert!((C64::new( 1.0,  0.0).phase() - 0.0      ).abs() < EPS);
        assert!((C64::new( 0.0,  1.0).phase() - PI / 2.0 ).abs() < EPS);
        assert!((C64::new(-1.0,  0.0).phase() - PI        ).abs() < EPS);
        assert!((C64::new( 0.0, -1.0).phase() + PI / 2.0 ).abs() < EPS);
    }

    #[test]
    fn c64_mul_i_squared_is_minus_one() {
        let i = C64::new(0.0, 1.0);
        let i2 = i.mul(i);
        assert!((i2.re + 1.0).abs() < EPS);
        assert!( i2.im.abs()         < EPS);
    }

    #[test]
    fn c64_mul_commutativity() {
        let a = C64::new(2.0, 3.0);
        let b = C64::new(-1.0, 4.0);
        let ab = a.mul(b);
        let ba = b.mul(a);
        assert!((ab.re - ba.re).abs() < EPS);
        assert!((ab.im - ba.im).abs() < EPS);
    }

    #[test]
    fn c64_mul_modulus_is_product() {
        let a = C64::new(2.0, 1.0);
        let b = C64::new(3.0, -2.0);
        let product_mag = a.mul(b).mag();
        assert!((product_mag - a.mag() * b.mag()).abs() < 1e-13);
    }

    #[test]
    fn c64_scale_real() {
        let z = C64::new(2.0, 3.0);
        let s = z.scale(4.0);
        assert!((s.re - 8.0 ).abs() < EPS);
        assert!((s.im - 12.0).abs() < EPS);
    }

    #[test]
    fn c64_scale_zero_gives_origin() {
        let z = C64::new(99.0, -77.0);
        let s = z.scale(0.0);
        assert_eq!(s.re, 0.0);
        assert_eq!(s.im, 0.0);
    }

    #[test]
    fn c64_repr_c_size_and_align() {
        // Must be exactly 16 bytes, align 8
        assert_eq!(std::mem::size_of::<C64>(), 16);
        assert_eq!(std::mem::align_of::<C64>(), 8);
    }

    // ── Coord ─────────────────────────────────────────────────────
    #[test]
    fn coord_size_is_24_bytes() {
        assert_eq!(std::mem::size_of::<Coord>(), 24);
        assert_eq!(std::mem::align_of::<Coord>(), 8);
    }

    // ── Align ─────────────────────────────────────────────────────
    #[test]
    fn align_identity_when_shift_zero() {
        for &t in &[-5.0_f64, 0.0, 3.14, 1e6] {
            assert_eq!(align(t, 0.0), t);
        }
    }

    #[test]
    fn align_translates_to_origin() {
        assert!((align(5.0, 5.0)).abs() < EPS);
        assert!((align(-3.0, -3.0)).abs() < EPS);
    }

    #[test]
    fn align_signed_displacement() {
        assert!((align(3.0, 1.0) - 2.0).abs() < EPS);
        assert!((align(1.0, 3.0) + 2.0).abs() < EPS);
    }

    // ── Bind ──────────────────────────────────────────────────────
    #[test]
    fn bind_peak_at_zero() {
        assert!((bind(0.0, 1.0) - 1.0).abs() < EPS);
        assert!((bind(0.0, 0.5) - 1.0).abs() < EPS);
        assert!((bind(0.0, 100.0) - 1.0).abs() < EPS);
    }

    #[test]
    fn bind_decays_from_centre() {
        // bind is strictly decreasing in |x|
        let w = 0.5;
        assert!(bind(0.0, w) > bind(1.0, w));
        assert!(bind(1.0, w) > bind(2.0, w));
        assert!(bind(2.0, w) > bind(3.0, w));
    }

    #[test]
    fn bind_is_symmetric() {
        for &x in &[0.5_f64, 1.0, 2.0, 5.0] {
            assert!((bind(x, 0.5) - bind(-x, 0.5)).abs() < EPS);
        }
    }

    #[test]
    fn bind_range_zero_to_one() {
        for &x in &[-10.0_f64, -1.0, 0.0, 1.0, 10.0] {
            let b = bind(x, 0.5);
            assert!(b > 0.0, "bind must be positive");
            assert!(b <= 1.0, "bind must not exceed 1");
        }
    }

    #[test]
    fn bind_analytical_value() {
        // bind(1, 0.5) = exp(-0.5)
        let expected = (-0.5_f64).exp();
        assert!((bind(1.0, 0.5) - expected).abs() < EPS);
    }

    #[test]
    fn bind_width_controls_spread() {
        // wider width (larger γ) → narrower envelope
        assert!(bind(1.0, 2.0) < bind(1.0, 0.5));
    }

    // ── Rotate ────────────────────────────────────────────────────
    #[test]
    fn rotate_unit_modulus() {
        for &x in &[-10.0_f64, -1.0, 0.0, 1.0, PI, 10.0] {
            let r = rotate(x, 5.0);
            assert!((r.mag() - 1.0).abs() < EPS,
                    "rotate({x}) mag = {}", r.mag());
        }
    }

    #[test]
    fn rotate_at_zero_is_one() {
        let r = rotate(0.0, 7.0);
        assert!((r.re - 1.0).abs() < EPS);
        assert!( r.im.abs()         < EPS);
    }

    #[test]
    fn rotate_quarter_period() {
        // rotate(π/2ω, ω) = i  (= cos(π/2) + i·sin(π/2))
        let omega = 4.0;
        let r = rotate(PI / (2.0 * omega), omega);
        assert!( r.re.abs()         < EPS);
        assert!((r.im - 1.0).abs() < EPS);
    }

    #[test]
    fn rotate_half_period() {
        let omega = 3.0;
        let r = rotate(PI / omega, omega);
        assert!((r.re + 1.0).abs() < EPS);   // cos(π) = -1
        assert!( r.im.abs()         < 1e-15);
    }

    #[test]
    fn rotate_full_period_identity() {
        let omega = 2.0;
        let r = rotate(2.0 * PI / omega, omega);
        assert!((r.re - 1.0).abs() < EPS);
        assert!( r.im.abs()         < EPS);
    }

    #[test]
    fn rotate_sin_cos_parity() {
        // rotate(x, ω).re = cos(ωx), .im = sin(ωx)
        for &x in &[0.3_f64, 1.1, 2.7, 5.0] {
            let omega = 7.0;
            let r = rotate(x, omega);
            assert!((r.re - (omega * x).cos()).abs() < EPS);
            assert!((r.im - (omega * x).sin()).abs() < EPS);
        }
    }

    // ── materialize ───────────────────────────────────────────────
    #[test]
    fn materialize_peak_at_t0() {
        let c = Coord { t0: 2.5, freq: 10.0, width: 0.5 };
        let peak = materialize(2.5, &c);
        // At t=t0, dt=0, bind=1, rotate=(1,0) → should be (1,0)
        assert!((peak.re - 1.0).abs() < EPS);
        assert!( peak.im.abs()         < EPS);
    }

    #[test]
    fn materialize_modulus_equals_bind() {
        // |materialize(t)| = bind(t-t0, γ) because |rotate| = 1
        let c = Coord { t0: 0.0, freq: 21.0, width: 0.5 };
        for &t in &[-2.0_f64, -1.0, 0.0, 1.0, 2.0] {
            let m = materialize(t, &c);
            let dt = align(t, c.t0);
            let expected_mag = bind(dt, c.width);
            assert!((m.mag() - expected_mag).abs() < EPS,
                    "at t={t}: mag={} expected={expected_mag}", m.mag());
        }
    }

    #[test]
    fn materialize_phase_equals_rotate_phase() {
        let c = Coord { t0: 0.0, freq: 3.0, width: 0.5 };
        for &t in &[0.1_f64, 0.5, 1.0, 2.0] {
            let m = materialize(t, &c);
            let dt = align(t, c.t0);
            let expected_phase = rotate(dt, c.freq).phase();
            let diff = (m.phase() - expected_phase).abs();
            assert!(diff < EPS || (diff - 2.0 * PI).abs() < EPS,
                    "phase mismatch at t={t}: got={} exp={expected_phase}", m.phase());
        }
    }

    #[test]
    fn materialize_decays_away_from_centre() {
        let c = Coord { t0: 0.0, freq: 10.0, width: 0.5 };
        let at_0  = materialize(0.0,  &c).mag();
        let at_1  = materialize(1.0,  &c).mag();
        let at_5  = materialize(5.0,  &c).mag();
        assert!(at_0 > at_1, "peak should be at centre");
        assert!(at_1 > at_5, "should decay with distance");
        assert!(at_5 < 1e-5, "far from centre should be near zero");
    }

    // ── render ────────────────────────────────────────────────────
    #[test]
    fn render_empty_buffer_is_noop() {
        let c = Coord { t0: 0.0, freq: 10.0, width: 0.5 };
        let mut buf: Vec<C64> = vec![];
        render(&c, -5.0, 5.0, &mut buf);
        // Should not panic; nothing to check
    }

    #[test]
    fn render_single_sample_at_t_min() {
        let c = Coord { t0: 0.0, freq: 10.0, width: 0.5 };
        let mut buf = [C64::new(0.0, 0.0); 1];
        render(&c, 0.0, 10.0, &mut buf);
        let expected = materialize(0.0, &c);
        assert!((buf[0].re - expected.re).abs() < EPS);
        assert!((buf[0].im - expected.im).abs() < EPS);
    }

    #[test]
    fn render_two_samples_endpoints() {
        let c = Coord { t0: 0.0, freq: 5.0, width: 0.5 };
        let mut buf = [C64::new(0.0, 0.0); 2];
        render(&c, 1.0, 3.0, &mut buf);
        let e0 = materialize(1.0, &c);
        let e1 = materialize(3.0, &c);
        assert!((buf[0].re - e0.re).abs() < EPS);
        assert!((buf[1].re - e1.re).abs() < EPS);
    }

    #[test]
    fn render_n_samples_match_materialize() {
        let c = Coord { t0: 1.0, freq: 7.0, width: 1.0 };
        let t_min = -3.0_f64;
        let t_max = 3.0_f64;
        let n = 256;
        let mut buf = vec![C64::new(0.0, 0.0); n];
        render(&c, t_min, t_max, &mut buf);
        let step = (t_max - t_min) / (n as f64 - 1.0);
        for i in 0..n {
            let t = t_min + step * i as f64;
            let expected = materialize(t, &c);
            assert!((buf[i].re - expected.re).abs() < EPS,
                    "re mismatch at i={i}");
            assert!((buf[i].im - expected.im).abs() < EPS,
                    "im mismatch at i={i}");
        }
    }

    // ── energy ────────────────────────────────────────────────────
    #[test]
    fn energy_empty_buffer_is_zero() {
        assert_eq!(energy(&[]), 0.0);
    }

    #[test]
    fn energy_unit_vector_is_one() {
        let buf = [C64::new(1.0, 0.0)];
        assert!((energy(&buf) - 1.0).abs() < EPS);
    }

    #[test]
    fn energy_is_sum_of_mag2() {
        let buf = [
            C64::new(3.0, 4.0),   // mag2 = 25
            C64::new(1.0, 0.0),   // mag2 = 1
            C64::new(0.0, 2.0),   // mag2 = 4
        ];
        assert!((energy(&buf) - 30.0).abs() < EPS);
    }

    #[test]
    fn energy_converges_toward_gaussian_integral() {
        // E = sqrt(π / 2γ). With γ=0.5: E = sqrt(π).
        // Over [-20, 20] with n=10000 almost all energy is captured.
        let c = Coord { t0: 0.0, freq: 10.0, width: 0.5 };
        let n = 10_000;
        let mut buf = vec![C64::new(0.0, 0.0); n];
        render(&c, -20.0, 20.0, &mut buf);
        let dt = 40.0 / (n as f64 - 1.0);
        let discrete_energy = energy(&buf) * dt;
        let analytical = (PI / (2.0 * c.width)).sqrt();
        assert!((discrete_energy - analytical).abs() < 1e-4,
                "E_discrete={discrete_energy:.6} E_analytic={analytical:.6}");
    }

    // ── verify (the physics contract) ────────────────────────────
    #[test]
    fn verify_passes() {
        let (ok, err) = verify();
        assert!(ok, "Physics parity FAILED: max_err = {err:.2e}");
    }

    #[test]
    fn verify_error_below_1e14() {
        let (_, err) = verify();
        assert!(err < 1e-14, "max_err = {err:.2e} exceeds 1e-14");
    }

    // ── Physics properties ────────────────────────────────────────
    #[test]
    fn time_bandwidth_saturation() {
        // For a Gabor atom: Δt = 1/(2√γ), Δω = √γ, Δt·Δω = 1/2.
        // Verify numerically by computing variance of |f|² as time dist.
        let c = Coord { t0: 0.0, freq: 0.0, width: 0.5 };
        let n = 100_000;
        let mut buf = vec![C64::new(0.0, 0.0); n];
        render(&c, -10.0, 10.0, &mut buf);
        let dt = 20.0 / (n as f64 - 1.0);

        // Compute E, mean t, variance t
        let norm: f64 = buf.iter().map(|z| z.mag2()).sum::<f64>() * dt;
        let mean_t: f64 = buf.iter().enumerate()
            .map(|(i, z)| {
                let t = -10.0 + dt * i as f64;
                z.mag2() * t / norm
            })
            .sum::<f64>() * dt;
        let var_t: f64 = buf.iter().enumerate()
            .map(|(i, z)| {
                let t = -10.0 + dt * i as f64;
                z.mag2() * (t - mean_t).powi(2) / norm
            })
            .sum::<f64>() * dt;
        let sigma_t = var_t.sqrt();
        // Expected: 1/(2√γ) = 1/(2*√0.5) = 1/√2 ≈ 0.7071
        let expected = 1.0 / (2.0 * c.width.sqrt());
        assert!((sigma_t - expected).abs() < 1e-3,
                "σ_t = {sigma_t:.4} expected {expected:.4}");
    }

    #[test]
    fn wavepacket_centred_at_t0() {
        // The probability distribution |f(t)|² should peak exactly at t0
        let c = Coord { t0: 1.618, freq: 21.0, width: 0.5 };
        let n = 10_000;
        let mut buf = vec![C64::new(0.0, 0.0); n];
        render(&c, -10.0, 10.0, &mut buf);
        let (peak_i, _) = buf.iter().enumerate()
            .max_by(|(_, a), (_, b)| a.mag2().partial_cmp(&b.mag2()).unwrap())
            .unwrap();
        let t_peak = -10.0 + 20.0 / (n as f64 - 1.0) * peak_i as f64;
        assert!((t_peak - c.t0).abs() < 0.01,
                "peak at {t_peak:.4} but t0 = {}", c.t0);
    }

    #[test]
    fn rotation_frequency_controls_phase_rate() {
        // At t0=0, phase advances at rate ω: phase(dt) ≈ ω·dt for small dt
        let c = Coord { t0: 0.0, freq: 21.0, width: 0.5 };
        let dt = 0.001_f64;
        let z0 = materialize(0.0,  &c);
        let z1 = materialize(dt, &c);
        // phase difference
        let dphi = z1.phase() - z0.phase();
        let expected = c.freq * dt;
        assert!((dphi - expected).abs() < 1e-8,
                "dφ/dt = {:.4} expected {:.4}", dphi / dt, c.freq);
    }

    #[test]
    fn golden_ratio_energy_ballpark() {
        // main() demo: t0=φ, ω=21, γ=0.5, n=500 on [-10,10]
        // energy should be in (1.0, 1.8) — consistent with finite window of √π
        let c = Coord { t0: 1.618, freq: 21.0, width: 0.5 };
        let mut buf = [C64::new(0.0, 0.0); 500];
        render(&c, -10.0, 10.0, &mut buf);
        let e = energy(&buf);
        // energy() is raw sum Σ|f_i|^2, not dt-normalised.
        // dt = 20/499 ~ 0.04008  → raw sum ~ sqrt(pi)/dt ~ 44.
        assert!(e > 30.0 && e < 60.0,
                "golden-ratio raw energy = {e:.6}, expected (30, 60)");
        // dt-normalised integral converges to sqrt(pi) ~ 1.7725
        let dt = 20.0_f64 / 499.0;
        let e_norm = e * dt;
        assert!(e_norm > 1.5 && e_norm < 2.0,
                "normalised energy = {e_norm:.6}, expected near 1.7725");
    }

    // ── Edge cases ────────────────────────────────────────────────
    #[test]
    fn very_narrow_packet_approximates_delta() {
        // γ → ∞: the Gaussian becomes a Dirac delta
        // Energy concentrates near t0
        // gamma=1e6: sigma = 1/(2*sqrt(1e6)) = 5e-4
        // bind(0.01, 1e6) = exp(-1e6 * 1e-4) = exp(-100) ~ 3.7e-44
        let c = Coord { t0: 0.0, freq: 1.0, width: 1.0e6 };
        let at_0  = materialize(0.0,  &c).mag();
        let at_01 = materialize(0.01, &c).mag();
        let at_1  = materialize(1.0,  &c).mag();
        assert!((at_0 - 1.0).abs() < EPS, "peak should be 1.0");
        assert!(at_01 < 1e-40, "narrow packet mag at 0.01 = {at_01:.2e}");
        assert!(at_1 == 0.0,   "narrow packet at 1.0 should flush to zero");
    }

    #[test]
    fn very_wide_packet_is_near_uniform() {
        // γ → 0: Gaussian → 1, packet is pure sinusoid
        let c = Coord { t0: 0.0, freq: 10.0, width: 1e-6 };
        for &t in &[-5.0_f64, 0.0, 5.0] {
            let m = materialize(t, &c);
            // mag should be ≈ 1 everywhere
            assert!((m.mag() - 1.0).abs() < 1e-4,
                    "wide packet: mag at t={t} = {:.6}", m.mag());
        }
    }

    #[test]
    fn zero_frequency_gives_real_valued_gaussian() {
        // ω=0 ⟹ e^(i·0) = 1, so f(t) = bind(t-t0, γ) · 1
        let c = Coord { t0: 0.0, freq: 0.0, width: 0.5 };
        for &t in &[-1.0_f64, 0.0, 1.0, 2.0] {
            let m = materialize(t, &c);
            let expected_re = bind(align(t, c.t0), c.width);
            assert!((m.re - expected_re).abs() < EPS);
            assert!( m.im.abs()                 < EPS);
        }
    }

    #[test]
    fn negative_frequency_mirrors_phase() {
        // f(t, ω=-ω₀) = conj(f(t, ω=ω₀))
        let t = 1.5_f64;
        let c_pos = Coord { t0: 0.0, freq:  5.0, width: 0.5 };
        let c_neg = Coord { t0: 0.0, freq: -5.0, width: 0.5 };
        let pos = materialize(t, &c_pos);
        let neg = materialize(t, &c_neg);
        assert!((pos.re - neg.re).abs() < EPS,   // real part same
                "re mismatch: {} vs {}", pos.re, neg.re);
        assert!((pos.im + neg.im).abs() < EPS,   // im part negated
                "im should negate: {} vs {}", pos.im, neg.im);
    }

    #[test]
    fn large_t0_shift_is_exact() {
        // shifting t0 by 1e6 should produce identical waveform shape
        let c1 = Coord { t0: 0.0,    freq: 10.0, width: 0.5 };
        let c2 = Coord { t0: 1.0e6,  freq: 10.0, width: 0.5 };
        for &dt in &[-1.0_f64, 0.0, 1.0] {
            let m1 = materialize(dt,            &c1);
            let m2 = materialize(c2.t0 + dt,   &c2);
            assert!((m1.re - m2.re).abs() < LOOSE,
                    "re shift mismatch at dt={dt}");
            assert!((m1.im - m2.im).abs() < LOOSE,
                    "im shift mismatch at dt={dt}");
        }
    }
}
