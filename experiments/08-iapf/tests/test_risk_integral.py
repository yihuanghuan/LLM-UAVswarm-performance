import numpy as np
import pytest

from analysis_core import risk_integral


def test_risk_integral_matches_trapezoidal_definition():
    time = np.array([0.0, 1.0, 2.0])
    distance = np.array([1.0, 0.5, 1.0])
    assert risk_integral(time, distance, 1.0) == pytest.approx(0.25)


def test_safe_distance_has_zero_risk():
    assert risk_integral([0, 1], [1.2, 1.2], 1.0) == 0.0
