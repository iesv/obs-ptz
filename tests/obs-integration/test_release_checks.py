"""Regression checks for release-review findings, using isolated real OBS."""
import json
import urllib.request

from conftest import SETTINGS_DIALOG
from test_filter_devices import FilterPtzsim
from test_soft_ptz import soft_cam


def test_a_hidden_settings_preview_releases_its_source(obs_world, soft_cam):
    showing = lambda: obs_world.ws.call("GetSourceActive", {"sourceName": soft_cam})["videoShowing"]
    obs_world.open_settings_dialog(soft_cam)
    obs_world.wait_for(showing)
    obs_world.ui.invoke(SETTINGS_DIALOG, method="hide")
    obs_world.wait_for(lambda: not showing())
    obs_world.open_settings_dialog(soft_cam)
    obs_world.wait_for(showing)
    obs_world.ui.invoke(SETTINGS_DIALOG, method="hide")
    obs_world.wait_for(lambda: not showing())


def test_a_connected_tcp_camera_can_change_its_port(obs_world, tmp_path):
    cameras = [FilterPtzsim(), FilterPtzsim()]
    source = "release-check-tcp-host-change"

    def state(camera):
        with urllib.request.urlopen(camera.debug_url, timeout=3) as response:
            return json.load(response)

    try:
        for camera in cameras:
            camera.start()
        scene = obs_world.create_scene()
        obs_world.ws.call("CreateInput", {
            "sceneName": scene, "inputName": source, "inputKind": "ffmpeg_source", "inputSettings": {},
        })
        obs_world.ws.call("CreateSourceFilter", {
            "sourceName": source, "filterName": "PTZ", "filterKind": "ca.secretlab.obs-ptz.visca",
            "filterSettings": {"type": "visca-over-tcp", "host": "127.0.0.1", "tcp_port": cameras[0].tcp_port},
        })
        obs_world.wait_for_device_by_name(source, tmp_path / "device.json",
                                          lambda r: r["found"] and r["bound"])
        obs_world.wait_for_device_state(source, tmp_path / "state.json",
                                       lambda r: r["state"].get("connected") is True)
        obs_world.call_proc(source, "ptz_move", {"pan": 0.5, "tilt": 0.0})
        obs_world.wait_for(lambda: state(cameras[0])["pan_speed"] > 0)
        obs_world.call_proc(source, "ptz_stop")
        obs_world.wait_for(lambda: state(cameras[0])["pan_speed"] == 0)
        obs_world.ws.call("SetSourceFilterSettings", {
            "sourceName": source, "filterName": "PTZ", "filterSettings": {"tcp_port": cameras[1].tcp_port},
        })
        obs_world.wait_for(lambda: bool(state(cameras[1])["visca_inquiries"]), timeout=10)
        obs_world.wait_for_device_state(source, tmp_path / "state.json",
                                       lambda r: r["state"].get("connected") is True)
        obs_world.call_proc(source, "ptz_move", {"pan": 0.7, "tilt": 0.0})
        obs_world.wait_for(lambda: state(cameras[1])["pan_speed"] > 0, timeout=10)
        assert state(cameras[0])["pan_speed"] == 0
    finally:
        if obs_world.device_uuid(source):
            obs_world.ws.call("RemoveInput", {"inputName": source})
        for camera in cameras:
            camera.stop()
