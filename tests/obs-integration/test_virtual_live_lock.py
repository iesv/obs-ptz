"""Optional live-lock policy for software viewports, retaining camera protection."""
from test_filter_devices import make_program, studio_mode
from test_virtual_ptz import virtual_cam


def test_virtual_viewport_unlocks_on_scene_changes(obs_world, virtual_cam, studio_mode, tmp_path):
    """Enable global protection, then check this specific kind's exception.

    A manual padlock still applies until the next scene change. Existing
    physical-camera and third-party-device tests exercise the default policy.
    """
    obs_world.set_live_move_lock(True)
    scenes = obs_world.ws.call("GetSceneList")["scenes"]
    scene = next(s["sceneName"] for s in scenes if any(
        item["sourceName"] == virtual_cam
        for item in obs_world.ws.call("GetSceneItemList", {"sceneName": s["sceneName"]})["sceneItems"]))
    make_program(obs_world, scene)
    obs_world.wait_for_device_source(virtual_cam, tmp_path / "device.json",
                                    lambda device: device["live"] and not device["locked"])
    obs_world.set_device_locked(virtual_cam, True)
    assert obs_world.device_source(virtual_cam, tmp_path / "device.json")["locked"]
    other = obs_world.create_scene()
    obs_world.ws.call("SetCurrentPreviewScene", {"sceneName": other})
    obs_world.wait_for_device_source(virtual_cam, tmp_path / "device.json",
                                    lambda device: device["live"] and not device["locked"])
