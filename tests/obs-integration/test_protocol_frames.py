"""Protocol vectors, independent of the plugin's encoder."""
from ptzsim.backends.pelco import PelcoCameraLogic
from ptzsim.state import PTZState


def test_standard_d_diagonal_frame_and_bad_checksum():
    state = PTZState()
    camera = PelcoCameraLogic(state)
    camera.handle_frame(bytes.fromhex("ff 01 00 12 3f 3f 91"))
    assert state.snapshot().pan_speed == 1.0
    assert state.snapshot().tilt_speed == -1.0
    camera.handle_frame(bytes.fromhex("ff 01 00 00 00 00 02"))
    assert state.snapshot().pan_speed == 1.0
    camera.handle_frame(bytes.fromhex("ff 01 00 00 00 00 01"))
    assert state.snapshot().pan_speed == 0.0
