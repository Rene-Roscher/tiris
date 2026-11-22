from tiris.events import find_runs, threshold


def minutes(ws, t0=0):
    return [(t0 + i * 60, w, w / 60) for i, w in enumerate(ws)]


def test_fridge_dip_is_one_run():
    ws = [0] * 5 + [60, 60, 2, 60, 60, 60] + [0] * 10
    runs = find_runs(minutes(ws), 10)
    assert len(runs) == 1
    assert runs[0]["start"] == 5 * 60 and runs[0]["end"] == 11 * 60
    assert abs(runs[0]["wh"] - (60 * 5 + 2) / 60) < 1e-9


def test_gap_longer_than_merge_splits():
    ws = [60, 60, 0, 0, 0, 0, 60, 60]
    assert len(find_runs(minutes(ws), 10)) == 2


def test_blip_is_dropped():
    assert find_runs(minutes([0, 80, 0, 0, 0, 0, 0]), 10) == []


def test_threshold_ignores_idle_level():
    ws = [20] * 80 + [1000] * 20      # idles at 20 W, works at 1 kW
    assert threshold(ws) >= 150
