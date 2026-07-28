import pytest

from analysis_core import resample_odometry


def row(timestamp, uav_id, x):
    return {"timestamp": timestamp, "uav_id": uav_id, "x": x, "y": 0, "z": 2}


def test_unsynchronized_timestamps_are_linearly_resampled():
    rows = [
        row(0.00, 1, 0.0), row(0.10, 1, 1.0), row(0.20, 1, 2.0),
        row(0.02, 2, 2.0), row(0.12, 2, 1.0), row(0.22, 2, 0.0),
    ]
    timeline, positions = resample_odometry(rows, sample_hz=10.0, max_gap=0.11)
    assert timeline[0] == pytest.approx(0.02)
    assert positions[1][0, 0] == pytest.approx(0.2)
    assert positions[2][0, 0] == pytest.approx(2.0)


def test_missing_odom_segment_is_an_explicit_error():
    rows = [
        row(0.0, 1, 0), row(0.1, 1, 0), row(1.0, 1, 0),
        row(0.0, 2, 1), row(0.1, 2, 1), row(0.2, 2, 1),
    ]
    with pytest.raises(ValueError, match="odometry gap"):
        resample_odometry(rows, sample_hz=20.0, max_gap=0.25)


def test_non_finite_odom_is_rejected():
    rows = [
        row(0.0, 1, 0), row(0.1, 1, float("nan")),
        row(0.0, 2, 1), row(0.1, 2, 1),
    ]
    with pytest.raises(ValueError, match="finite"):
        resample_odometry(rows, sample_hz=20.0, max_gap=0.25)
