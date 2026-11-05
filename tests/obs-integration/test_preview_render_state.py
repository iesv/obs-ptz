"""Check preview pixels and state with a preceding pass's graphics settings."""
import json
import struct
import zlib

import pytest


@pytest.mark.parametrize("mode", ["matrix", "blend"])
def test_preview_ignores_and_restores_inherited_graphics_state(obs_world, tmp_path, mode):
    """Run the actual renderer over green with a transparent image source.

    White in the middle proves that an inherited translation was ignored.
    Green in a transparent corner proves alpha compositing was enabled.
    The final marker and matrix comparison check both state restores.
    """
    width, height = 128, 72

    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))

    rows = bytearray()
    for y in range(height):
        rows.append(0)
        for x in range(width):
            alpha = 255 if 32 <= x < 96 and 18 <= y < 54 else 0
            rows.extend((255, 255, 255, alpha))
    image = tmp_path / "transparent.png"
    image.write_bytes(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0))
                      + chunk(b"IDAT", zlib.compress(rows)) + chunk(b"IEND", b""))
    source = "preview-render-" + mode
    scene = obs_world.create_scene()
    obs_world.ws.call("CreateInput", {
        "sceneName": scene, "inputName": source, "inputKind": "image_source",
        "inputSettings": {"file": str(image)},
    })
    try:
        # A normal screenshot first lets the source initialize its texture.
        obs_world.wait_for(lambda: obs_world.ws.call("GetSourceScreenshot", {
            "sourceName": source, "imageFormat": "png"}))
        start = len(obs_world.obs_log().read_text(errors="replace"))
        obs_world.run_ui_test("preview_render", source=source, mode=mode)
        result = {}

        def logged():
            text = obs_world.obs_log().read_text(errors="replace")[start:]
            marker = "[ptz-ui-test] preview_render: "
            line = next((line for line in text.splitlines() if marker in line), None)
            if line:
                result.update(json.loads(line.split(marker, 1)[1]))
            return bool(result)

        obs_world.wait_for(logged)
        assert result["center"] == [255, 255, 255], result
        assert result["corner"] == [0, 255, 0], result
        assert result["matrix_restored"], result
        assert result["caller_pixel"] == [0, 0, 0], result
    finally:
        obs_world.ws.call("RemoveInput", {"inputName": source})
