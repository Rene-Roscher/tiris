"""Cycle detection on synthetic power curves (no database needed)."""
from tiris.analysis import detect_cycles


def curve(segments):
    """segments: [(seconds, watts), ...] sampled every 2 s."""
    t, out = 0.0, []
    for dur, w in segments:
        for _ in range(int(dur / 2)):
            out.append((t, w))
            t += 2
    return out


def test_fridge_like_cycles():
    pts = curve([(600, 1), (300, 90), (600, 1), (300, 90), (600, 1)])   # two 5-minute runs
    c = detect_cycles(pts, on_w=10)
    assert c["count"] == 2
    assert 295 <= c["median_s"] <= 305
    assert 0.25 <= c["duty"] <= 0.3


def test_hysteresis_counts_a_wobbling_run_once():
    # around the threshold: 12 W, 8 W, 12 W ... stays above off (5 W), so it is one run, not many
    pts = curve([(60, 1)] + [(10, 12), (10, 8)] * 20 + [(60, 1)])
    assert detect_cycles(pts, on_w=10)["count"] == 1


def test_gap_is_not_on_time():
    pts = [(0, 50), (2, 50), (3600, 50), (3602, 0)]   # an hour without samples in between
    assert detect_cycles(pts, on_w=10)["duty"] < 0.01


def test_inrush_spike_does_not_raise_the_threshold():
    from tiris import analysis
    pts = curve([(600, 1), (2, 590), (300, 75), (600, 1), (2, 590), (300, 75), (600, 1)])
    ws = [w for _, w in pts]
    p95 = sorted(ws)[int(len(ws) * 0.95)]
    assert max(3.0, p95 * 0.15) < 75          # the running power stays above the threshold
    assert analysis.detect_cycles(pts, on_w=max(3.0, p95 * 0.15))["count"] == 2
