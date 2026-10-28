"""Opt-in release soak tests against a real, isolated OBS process.

Set PTZ_STRESS=1 and PTZ_STRESS_CYCLES=100 to exercise each source kind with
100 moves, preset captures/recalls and Studio Mode transitions, plus a public
source copy/deletion every five cycles. The image is 1920x1080 so texture
creation and destruction are tested at video resolution, not just icon size.

Samples measure the OBS process, not pytest or the camera simulator. Compare
steady-state medians after warm-up so allocator caches are not mistaken for a
leak. The bounds are regression tripwires, not a guarantee about every GPU:
RSS measures host memory, and process handles do not measure dedicated VRAM.
Metrics are written beside pytest's artifacts for independent review.
"""
import json
import os
import statistics
import struct
import time
import zlib

import psutil
import pytest
from test_onvif_position import onvif_device

from test_soft_ptz import (FILTER_KIND, GREEN, RED, duplicating_studio_mode, move,
                          thumbnail_image, wait_for_corners, wait_for_position)

pytestmark = pytest.mark.skipif(os.environ.get("PTZ_STRESS") != "1", reason="opt-in stress test")


def write_large_image(path):
    """Write a compressible, two-colour HD image without extra image libraries.

    Its known left/right colours let screenshots verify content after moving,
    instead of merely proving that a screenshot request returned some bytes.
    """
    width, height = 1920, 1080
    row = b"\0" + bytes(RED) * (width // 2) + bytes(GREEN) * (width // 2)

    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))

    path.write_bytes(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
                     + chunk(b"IDAT", zlib.compress(row * height)) + chunk(b"IEND", b""))


@pytest.mark.parametrize("kind", ["image", "text"])
def test_source_copy_preset_and_transition_soak(obs_world, duplicating_studio_mode, tmp_path, kind):
    """Keep eight live presets while cycling transient and persistent copies.

    Each cycle checks earlier thumbnails, and each public copy is rendered
    before deletion so its GPU resources actually need to be allocated/freed.
    The device-list invariant catches private-copy leaks independently of the
    memory thresholds. Both an HD image and a native OBS text source are used.
    """
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
                try:
                    obs_world.wait_for(lambda: devices() == expected_devices)
                except AssertionError:
                    print("Expected device UUIDs:", sorted(expected_devices), flush=True)
                    print("Actual device entries:", obs_world.ws.vendor("obs-ptz", "ptz_list_devices"), flush=True)
                    raise
            obs_world.ws.call("SetCurrentPreviewScene", {
                "sceneName": camera_scene if index % 2 else other_scene,
            })
            obs_world.ws.call("TriggerStudioModeTransition")
            assert devices() == expected_devices
            samples.append({"rss": process.memory_info().rss,
                            "handles": process.num_handles() if os.name == "nt" else process.num_fds()})
        # Ignore initial texture, font and Qt-cache allocation. Compare two
        # multi-sample windows so one background allocation does not dominate.
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


def test_onvif_request_soak(obs_world, onvif_device, tmp_path):
    """Exercise 1,200 real SOAP requests through the production ONVIF driver.

    The simulator's received-request counter prevents a burst of commands that
    was only queued or dropped from being mistaken for completed load. Early
    batches warm network pools and XML/Qt allocations before RSS is compared.
    This covers the completed-QNetworkReply lifetime during sustained use.
    """
    # Connected can be reported by the initial clock request. A reported PTZ
    # position additionally proves that service/profile discovery is complete,
    # so no early refresh is dropped for lack of an initialized service URL.
    obs_world.wait_for_device_state(onvif_device, tmp_path / "onvif-ready.json",
                                   lambda result: "pan" in result["state"], timeout=20)
    process = psutil.Process(obs_world.obs_process().pid)
    samples = []
    started = time.monotonic()
    count = obs_world.state()["onvif_requests"]
    for batch in range(12):
        for _ in range(100):
            obs_world.call_proc(onvif_device, "ptz_preset_refresh")
        count += 100
        obs_world.wait_for(lambda: obs_world.state()["onvif_requests"] >= count, timeout=30)
        time.sleep(0.25)
        samples.append(process.memory_info().rss)
    report = {
        "kind": "onvif", "requests_sent": 1200, "duration_seconds": time.monotonic() - started,
        "rss_growth_bytes": statistics.median(samples[-3:]) - statistics.median(samples[2:5]),
        "samples": samples,
    }
    (tmp_path / "stress-metrics.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report))
    assert report["rss_growth_bytes"] < 32 * 1024 * 1024, report
    assert obs_world.state()["onvif_invalid_nonce_encodings"] == 0
