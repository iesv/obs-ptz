"""Opt-in soak test: PTZ_STRESS=1, PTZ_STRESS_CYCLES=100 (per source kind)."""
import json
import os
import statistics
import struct
import time
import zlib

import psutil
import pytest

from test_soft_ptz import (FILTER_KIND, GREEN, RED, duplicating_studio_mode, move,
                          thumbnail_image, wait_for_corners, wait_for_position)

pytestmark = pytest.mark.skipif(os.environ.get("PTZ_STRESS") != "1", reason="opt-in stress test")


def write_large_image(path):
    width, height = 1920, 1080
    row = b"\0" + bytes(RED) * (width // 2) + bytes(GREEN) * (width // 2)

    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))

    path.write_bytes(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
                     + chunk(b"IDAT", zlib.compress(row * height)) + chunk(b"IEND", b""))


@pytest.mark.parametrize("kind", ["image", "text"])
def test_source_copy_preset_and_transition_soak(obs_world, duplicating_studio_mode, tmp_path, kind):
    cycles = int(os.environ.get("PTZ_STRESS_CYCLES", "100"))
    assert cycles >= 20
    camera_scene, other_scene = obs_world.create_scene(), obs_world.create_scene()
    source = "stress-soft-ptz-" + kind
    if kind == "image":
        image = tmp_path / "large.png"
        write_large_image(image)
        input_kind, settings = "image_source", {"file": str(image)}
    else:
        kinds = obs_world.ws.call("GetInputKindList")["inputKinds"]
        input_kind = next(k for k in kinds if k.startswith(("text_gdiplus", "text_ft2_source")))
        settings = {"text": "Soft PTZ stress 0123456789", "font": {"face": "Arial", "size": 120}}
    obs_world.ws.call("CreateInput", {
        "sceneName": camera_scene, "inputName": source, "inputKind": input_kind, "inputSettings": settings,
    })
    obs_world.ws.call("CreateSourceFilter", {
        "sourceName": source, "filterName": "Soft PTZ", "filterKind": FILTER_KIND,
        "filterSettings": {"max_zoom": 4.0, "recall_seconds": 0.0},
    })
    obs_world.wait_for(lambda: obs_world.device_uuid(source))
    obs_world.open_settings_dialog(source)
    devices = lambda: {d["device"] for d in obs_world.ws.vendor("obs-ptz", "ptz_list_devices")["devices"]}
    expected_devices = devices()
    process = psutil.Process(obs_world.obs_process().pid)
    samples, presets = [], []
    started = time.monotonic()
    cpu_start = sum(process.cpu_times()[:2])
    try:
        for index in range(cycles):
            pan = 0.75 if index % 2 else -0.75
            move(obs_world, source, pan=pan, tilt=0.0, zoom=1.0)
            wait_for_position(obs_world, source, tmp_path, pan=pan, tilt=0.0, zoom=1.0)
            if kind == "image":
                wait_for_corners(obs_world, source, dict.fromkeys(("tl", "tr", "bl", "br"), GREEN if pan > 0 else RED))
            preset = obs_world.create_preset(source, str(index), store="local")
            obs_world.wait_for(lambda: thumbnail_image(obs_world, source, preset))
            presets.append(preset)
            obs_world.call_proc(source, "ptz_preset_recall", {"id": preset})
            if len(presets) > 8:
                obs_world.call_proc(source, "ptz_preset_delete", {"id": presets.pop(0)})
            assert all(thumbnail_image(obs_world, source, p) for p in presets)
            if index % 5 == 0:
                copy = source + "-copy"
                obs_world.ui.call("duplicate_source", name=source, copy=copy, scene=other_scene)
                obs_world.wait_for(lambda: obs_world.device_uuid(copy))
                assert thumbnail_image(obs_world, copy, preset)
                obs_world.ws.call("GetSourceScreenshot", {"sourceName": copy, "imageFormat": "png"})
                obs_world.call_proc(copy, "ptz_preset_delete", {"id": preset})
                assert thumbnail_image(obs_world, source, preset)
                obs_world.ws.call("RemoveInput", {"inputName": copy})
                obs_world.wait_for(lambda: devices() == expected_devices)
            obs_world.ws.call("SetCurrentPreviewScene", {
                "sceneName": camera_scene if index % 2 else other_scene,
            })
            obs_world.ws.call("TriggerStudioModeTransition")
            assert devices() == expected_devices
            samples.append({"rss": process.memory_info().rss,
                            "handles": process.num_handles() if os.name == "nt" else process.num_fds()})
        baseline = samples[10:20]
        final = samples[-10:]
        report = {
            "kind": kind, "cycles": cycles, "transitions": cycles, "presets_created": cycles,
            "source_copies": (cycles + 4) // 5, "duration_seconds": time.monotonic() - started,
            "cpu_seconds": sum(process.cpu_times()[:2]) - cpu_start,
            "rss_growth_bytes": statistics.median(s["rss"] for s in final) - statistics.median(s["rss"] for s in baseline),
            "handle_growth": statistics.median(s["handles"] for s in final) - statistics.median(s["handles"] for s in baseline),
            "samples": samples,
        }
        (tmp_path / "stress-metrics.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(json.dumps({k: v for k, v in report.items() if k != "samples"}))
        assert report["rss_growth_bytes"] < 128 * 1024 * 1024, report
        assert report["handle_growth"] < 64, report
    finally:
        obs_world.ws.call("RemoveInput", {"inputName": source})
