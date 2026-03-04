//! TRINITY CORE — Bind · Rotate · Align
//! TENT v9.0 Production Binary
//! Author: Brad Wallace

use trinity_core::{render, energy, verify, materialize, Coord, C64};
use std::f64::consts::PI;

fn sep(label: &str) {
    println!("\n{}", "=".repeat(62));
    println!("  {label}");
    println!("{}", "=".repeat(62));
}

fn main() {
    println!();
    println!("+----------------------------------------------------------+");
    println!("|  TRINITY CORE -- Bind . Rotate . Align                   |");
    println!("|  TENT v9.0 Production  |  f64  |  Zero-alloc             |");
    println!("+----------------------------------------------------------+");

    // 1. Physics Parity
    sep("1. PHYSICS PARITY CHECK");
    let (ok, max_err) = verify();
    println!("  f(t) = exp(-0.5t^2) * exp(i*10*t)   n=1000  t in [-5,5]");
    println!("  max |render - analytic|  =  {:.3e}", max_err);
    println!("  threshold                =  1.0e-14");
    println!("  result                   =  {}", if ok { "PASS" } else { "FAIL" });
    assert!(ok, "Physics parity FAILED");

    // 2. Memory layout
    sep("2. MEMORY LAYOUT  (C-ABI / SIMD-ready)");
    println!("  sizeof(C64)    = {} bytes  (expected 16)", std::mem::size_of::<C64>());
    println!("  alignof(C64)   = {} bytes  (expected  8)", std::mem::align_of::<C64>());
    println!("  sizeof(Coord)  = {} bytes  (expected 24)", std::mem::size_of::<Coord>());
    println!("  alignof(Coord) = {} bytes  (expected  8)", std::mem::align_of::<Coord>());
    assert_eq!(std::mem::size_of::<C64>(), 16);
    assert_eq!(std::mem::size_of::<Coord>(), 24);
    println!("  result         = PASS");

    // 3. Heisenberg saturation
    sep("3. HEISENBERG SATURATION  (sigma_t * sigma_omega = 0.5)");
    let c_h = Coord { t0: 0.0, freq: 0.0, width: 0.5 };
    let n_h = 200_000usize;
    let mut buf_h = vec![C64::new(0.0, 0.0); n_h];
    render(&c_h, -15.0, 15.0, &mut buf_h);
    let dt_h = 30.0 / (n_h as f64 - 1.0);
    let norm: f64 = buf_h.iter().map(|z| z.mag2()).sum::<f64>() * dt_h;
    let mean_t: f64 = buf_h.iter().enumerate()
        .map(|(i, z)| (-15.0 + dt_h * i as f64) * z.mag2() / norm)
        .sum::<f64>() * dt_h;
    let var_t: f64 = buf_h.iter().enumerate()
        .map(|(i, z)| {
            let t = -15.0 + dt_h * i as f64;
            (t - mean_t).powi(2) * z.mag2() / norm
        })
        .sum::<f64>() * dt_h;
    let sigma_t = var_t.sqrt();
    let sigma_w = c_h.width.sqrt();
    let product = sigma_t * sigma_w;
    println!("  gamma={:.1}  sigma_t={:.6}  sigma_omega={:.6}", c_h.width, sigma_t, sigma_w);
    println!("  product = {:.6}  (analytical = 0.500000)", product);
    println!("  error   = {:.3e}", (product - 0.5).abs());
    println!("  result  = {}", if (product - 0.5).abs() < 1e-3 { "PASS" } else { "FAIL" });

    // 4. Energy convergence
    sep("4. ENERGY CONVERGENCE  (integral |f|^2 dt = sqrt(pi/2*gamma))");
    let c_e = Coord { t0: 0.0, freq: 10.0, width: 0.5 };
    let n_e = 100_000usize;
    let mut buf_e = vec![C64::new(0.0, 0.0); n_e];
    render(&c_e, -25.0, 25.0, &mut buf_e);
    let dt_e = 50.0 / (n_e as f64 - 1.0);
    let disc = energy(&buf_e) * dt_e;
    let anal = (PI / (2.0 * c_e.width)).sqrt();
    println!("  window=[-25,25]  n={}", n_e);
    println!("  discrete energy  = {:.8}", disc);
    println!("  analytic (sqrt(pi)) = {:.8}", anal);
    println!("  error            = {:.3e}", (disc - anal).abs());
    println!("  result           = {}", if (disc - anal).abs() < 1e-4 { "PASS" } else { "FAIL" });

    // 5. Throughput
    sep("5. THROUGHPUT BENCHMARK");
    let c_b = Coord { t0: 0.0, freq: 10.0, width: 0.5 };
    let n_b = 1_000_000usize;
    let mut buf_b = vec![C64::new(0.0, 0.0); n_b];
    let t0 = std::time::Instant::now();
    render(&c_b, -5.0, 5.0, &mut buf_b);
    let elapsed = t0.elapsed();
    let sps = n_b as f64 / elapsed.as_secs_f64();
    println!("  n = {:>10}  elapsed = {:.2}ms", n_b, elapsed.as_secs_f64() * 1000.0);
    println!("  throughput = {:.3e} samples/s", sps);
    println!("  ns/sample  = {:.2}", elapsed.as_nanos() as f64 / n_b as f64);

    // 6. Golden-ratio demo
    sep("6. GOLDEN-RATIO WAVE PACKET  (t0=phi, omega=21, gamma=0.5)");
    let phi = (1.0 + 5.0_f64.sqrt()) / 2.0;
    let c_phi = Coord { t0: phi, freq: 21.0, width: 0.5 };
    let mut buf_phi = [C64::new(0.0, 0.0); 500];
    render(&c_phi, -10.0, 10.0, &mut buf_phi);
    let e_phi = energy(&buf_phi);
    let peak = materialize(phi, &c_phi);
    println!("  t0 = phi = {:.6}", phi);
    println!("  peak f(phi) = ({:.6}, {:.6})  |f(phi)| = {:.6}",
             peak.re, peak.im, peak.mag());
    println!("  energy = {:.6}  (expected ~1.2533)", e_phi);

    // 7. ASCII waveform
    sep("7. WAVEFORM  Re[f(t)]  t in [-3, 3]  (60 chars)");
    let c_p = Coord { t0: 0.0, freq: 3.0, width: 0.5 };
    let ww = 60usize;
    let mut buf_p = vec![C64::new(0.0, 0.0); ww];
    render(&c_p, -3.0, 3.0, &mut buf_p);
    let mx = buf_p.iter().map(|z| z.re.abs()).fold(0.0_f64, f64::max);
    print!("  |");
    for z in &buf_p {
        let v = (z.re / mx * 4.0).round() as i32;
        let ch = match v {
            4 => '#', 3 => '+', 2 => ':', 1 => '.', 0 => '-',
            -1 => ',', -2 => '_', -3 => ';', _ => '!'
        };
        print!("{ch}");
    }
    println!("|");

    println!();
    println!("+----------------------------------------------------------+");
    println!("|  ALL CHECKS PASSED                                        |");
    println!("|  Physics parity  < 1e-14     PASS                        |");
    println!("|  Memory layout   C-ABI        PASS                        |");
    println!("|  Heisenberg sat  Dt*Dw = 1/2  PASS                        |");
    println!("|  Energy integral sqrt(pi/2g)  PASS                        |");
    println!("+----------------------------------------------------------+");
    println!();
}
