"""The mic filter must ignore flickers but pass a sustained loud sound (phone speaker on the mic)."""

from software.backend.core.sensors import SoundFilter


def feed(f, flags, alert="NORMAL", filtered=False, start=1000.0):
    out = None
    for i, flag in enumerate(flags):
        out = f.observe(flag, alert, filtered, now=start + i * 0.4)
    return out


def test_flickering_mic_is_ignored():
    f = SoundFilter()
    # Random single blips, even with the old firmware's COLLISION alert attached
    for i, flag in enumerate([1, 0, 0, 1, 0, 0, 0, 1, 0, 1, 0, 0]):
        sound, collision = f.observe(flag, "COLLISION" if flag else "NORMAL", False, now=1000 + i * 0.4)
        assert not sound
        assert not collision
    assert not f.collision_allowed(now=1005.0)


def test_sustained_sound_triggers_collision():
    f = SoundFilter()
    sound, collision = feed(f, [1, 1, 1, 1])
    assert sound and collision


def test_manual_collision_passes_hardware_echo():
    f = SoundFilter()
    f.manual_collision(now=1000.0)
    sound, collision = f.observe(0, "COLLISION", False, now=1001.0)
    assert collision and not sound
    sound, collision = f.observe(0, "COLLISION", False, now=1000.0 + SoundFilter.MANUAL_GRACE_S + 1)
    assert not collision


def test_filtered_firmware_is_trusted():
    f = SoundFilter()
    assert f.observe(1, "NORMAL", True, now=1000.0) == (True, True)
    assert f.observe(0, "NORMAL", True, now=1000.4) == (False, False)
    assert f.observe(0, "COLLISION", True, now=1000.8) == (False, True)
    assert f.collision_allowed(now=1001.0)


def test_stuck_mic_flag_is_ignored():
    f = SoundFilter()
    # Flag stuck at 1 for 20 s (old firmware reading an inverted module in a quiet room)
    states = [f.observe(1, "NORMAL", False, now=1000 + i * 0.4) for i in range(50)]
    assert states[5][0]                      # looks like a real sound at first...
    assert states[-1] == (False, False)      # ...but is dropped once it is clearly stuck
    assert not f.collision_allowed(now=1020.0)
