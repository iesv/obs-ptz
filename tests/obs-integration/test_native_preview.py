"""Check the native PTZ preview's own framebuffer, including preset captures."""

import json
import platform

import pytest
from conftest import OBS_MAIN, SETTINGS_DIALOG
from test_soft_ptz import FILTER_KIND, move, thumbnail_image, wait_for_position
from uidriver import UiDriverError


@pytest.mark.skipif(platform.system() != "Windows", reason="D3D11 native framebuffer probe")
def test_native_text_preview_after_preset_capture_and_surface_recreation(obs_world, tmp_path):
    """Source screenshots do not exercise the native window's swap chain.

    Match the reported transparent white GDI text and PTZ position, capture
    twenty presets while its settings preview remains visible, and inspect
    that preview after every capture. Also force a real Qt surface recreation
    so a one-way display shutdown cannot leave an exposed window unrendered.
    Save measurements even on failure for hosted-runner and real-GPU review.
    """
    source = "native-preview-text"
    scene = obs_world.create_scene()
    measurements = []
    was_studio = obs_world.ws.call("GetStudioModeEnabled")["studioModeEnabled"]
    obs_world.ws.call("CreateInput", {
        "sceneName": scene, "inputName": source, "inputKind": "text_gdiplus_v3",
        "inputSettings": {"text": "aaaaa", "font": {"face": "Arial", "size": 120},
                          "color": 16777215, "opacity": 100, "bk_opacity": 0},
    })
    obs_world.ws.call("CreateSourceFilter", {
        "sourceName": source, "filterName": "Soft PTZ", "filterKind": FILTER_KIND,
        "filterSettings": {"max_zoom": 4.0, "recall_seconds": 0.0},
    })
    obs_world.wait_for(lambda: obs_world.device_uuid(source))
    move(obs_world, source, pan=0.162, tilt=0.0, zoom=0.150)
    wait_for_position(obs_world, source, tmp_path, pan=0.162, tilt=0.0, zoom=0.150)
    obs_world.ws.call("SetStudioModeEnabled", {"studioModeEnabled": True})
    obs_world.ws.call("SetCurrentProgramScene", {"sceneName": scene})
    # A minimized main window can prevent presentation of child native windows.
    obs_world.ui.invoke(OBS_MAIN, method="showNormal")
    obs_world.open_settings_dialog(source)
    path = [SETTINGS_DIALOG, "sourcePreview"]

    def frame(label):
        pixels = {}

        def sample():
            try:
                pixels.update(obs_world.ui.call("native_display", path=path))
                return True
            except UiDriverError as exc:
                if exc.code != "no_frame":
                    raise
                measurements.append({"phase": label, "error": str(exc)})
                return None

        obs_world.wait_for(sample, timeout=6)
        measurements.append({"phase": label, **pixels})
        assert pixels["dark"] > 0.05, pixels
        assert 0.005 < pixels["white"] < 0.8, pixels

    try:
        frame("before")
        for index in range(20):
            preset = obs_world.create_preset(source, str(index), store="local")
            obs_world.wait_for(lambda: thumbnail_image(obs_world, source, preset))
            frame(f"preset-{index}")
        obs_world.ui.call("native_display", path=path, recreate=True)
        frame("surface-recreated")
    finally:
        (tmp_path / "native-preview-metrics.json").write_text(json.dumps(measurements, indent=2))
        obs_world.ui.invoke(SETTINGS_DIALOG, method="hide")
        obs_world.ws.call("RemoveInput", {"inputName": source})
        obs_world.ws.call("SetStudioModeEnabled", {"studioModeEnabled": was_studio})
