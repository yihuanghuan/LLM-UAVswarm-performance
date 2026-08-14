from readiness_gate import ContinuousReadinessGate, ReadySample


def sample(now, **updates):
    values = dict(
        received_monotonic=now, system_ready=True, armed=True,
        offboard=True, failsafe=False, altitude=1.5,
        position_derived_speed=0.1,
    )
    values.update(updates)
    return ReadySample(**values)


def test_requires_every_uav_and_continuous_hold():
    gate = ContinuousReadinessGate([1, 2], hold_time=1.0)
    gate.update(1, sample(10.0))
    assert gate.evaluate(10.0) is False
    gate.update(2, sample(10.0))
    assert gate.evaluate(10.0) is False
    gate.update(1, sample(10.8))
    gate.update(2, sample(10.8))
    assert gate.evaluate(10.8) is False
    gate.update(1, sample(11.0))
    gate.update(2, sample(11.0))
    assert gate.evaluate(11.0) is True


def test_speed_or_feedback_loss_resets_hold():
    gate = ContinuousReadinessGate([1], hold_time=1.0)
    gate.update(1, sample(0.0))
    gate.evaluate(0.0)
    gate.update(1, sample(0.6, position_derived_speed=0.31))
    assert gate.evaluate(0.6) is False
    gate.update(1, sample(1.0))
    assert gate.evaluate(1.0) is False
    gate.update(1, sample(2.0))
    assert gate.evaluate(2.0) is True
