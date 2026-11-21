// Measured cost of tauri-plugin-window-state's two disk operations on this
// machine's real store: serde_json::from_reader(BufReader<File>) on start and
// serde_json::to_vec_pretty + std::fs::write on exit (plugin 2.5.0, lib.rs:138-160,
// 537-547). Same crates, same payload as ~/Library/Application Support/com.ephe.ephe/.window-state.json.
use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use std::fs::File;
use std::io::BufReader;
use std::time::Instant;

#[derive(Serialize, Deserialize, Default, Clone, PartialEq)]
struct WindowState {
    width: u32,
    height: u32,
    x: i32,
    y: i32,
    prev_x: i32,
    prev_y: i32,
    maximized: bool,
    visible: bool,
    decorated: bool,
    fullscreen: bool,
}

fn pct(v: &mut Vec<f64>, p: f64) -> f64 {
    v.sort_by(|a, b| a.partial_cmp(b).unwrap());
    v[((v.len() as f64 - 1.0) * p).round() as usize]
}

fn main() {
    let args: Vec<String> = std::env::args().collect();
    let src = args.get(1).cloned().unwrap_or_else(|| {
        format!(
            "{}/Library/Application Support/com.ephe.ephe/.window-state.json",
            std::env::var("HOME").unwrap()
        )
    });
    let reps: usize = args.get(2).and_then(|s| s.parse().ok()).unwrap_or(200);
    let bytes = std::fs::read(&src).expect("state file");
    let tmp = std::env::temp_dir().join("bench-winstate-out.json");

    let mut read_ms = Vec::new();
    let mut write_ms = Vec::new();
    for _ in 0..reps {
        let t = Instant::now();
        let f = File::open(&src).unwrap();
        let mut r = BufReader::new(f);
        let states: HashMap<String, WindowState> = serde_json::from_reader(&mut r).unwrap();
        read_ms.push(t.elapsed().as_secs_f64() * 1000.0);
        std::hint::black_box(&states);

        let t = Instant::now();
        let out = serde_json::to_vec_pretty(&states).unwrap();
        std::fs::write(&tmp, out).unwrap();
        write_ms.push(t.elapsed().as_secs_f64() * 1000.0);
    }
    let med = |v: &mut Vec<f64>| pct(v, 0.5);
    println!(
        "file={} bytes={} records={} reps={}",
        src,
        bytes.len(),
        serde_json::from_slice::<HashMap<String, WindowState>>(&bytes).unwrap().len(),
        reps
    );
    println!("read  median_ms={:.4} p95_ms={:.4}", med(&mut read_ms), pct(&mut read_ms, 0.95));
    println!("write median_ms={:.4} p95_ms={:.4}", med(&mut write_ms), pct(&mut write_ms, 0.95));
}
