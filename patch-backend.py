from pathlib import Path
def replace(path, old, new):
    p = Path(path)
    s = p.read_text()
    if new in s:
        return
    if s.count(old) != 1:
        raise RuntimeError(f"Unexpected upstream source: {path}")
    p.write_text(s.replace(old, new))
p = Path("source/rust/allie-fast/src/lib.rs")
s = p.read_text()
addition = """
// One UCI worker per process. Stop is checked between native KL batches.
pub static UCI_STOP: std::sync::atomic::AtomicBool =
    std::sync::atomic::AtomicBool::new(false);

#[pyfunction]
fn uci_stop(value: bool) {
    UCI_STOP.store(value, std::sync::atomic::Ordering::Relaxed);
}
"""
if "pub static UCI_STOP:" not in s:
    p.write_text(s + addition)
replace(str(p), '    m.add("INTERFACE", INTERFACE)?;',
    '    m.add("INTERFACE", INTERFACE)?;\n'
    '    m.add_function(wrap_pyfunction!(uci_stop, m)?)?;')
replace("source/rust/allie-fast/src/search/kl.rs",
    "(t + self.lag <= deadline).then(",
    "(!crate::UCI_STOP.load(std::sync::atomic::Ordering::Relaxed)"
    " && t + self.lag <= deadline).then(")