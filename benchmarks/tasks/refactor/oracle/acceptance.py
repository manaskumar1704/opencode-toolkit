import octk.refactor_target as mod


def test_behaviour_unchanged():
    assert mod.magnitude([-1, 2, -3]) == [1, 2, 3]


def test_redundant_helper_removed():
    assert not hasattr(mod, "_apply")
