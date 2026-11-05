"""Observe WS-Security nonce encoding in the SOAP requests sent by OBS."""
from test_onvif_position import onvif_device


def test_nonce_encoding_identifies_base64_bytes(obs_world, onvif_device):
    """A tolerant camera must not hide a nonconforming encoding attribute.

    The emulator parses the wire XML independently of the plugin's writer.
    The digest algorithm belongs to Password/Type; Nonce/EncodingType must
    instead identify Base64Binary (WS-I Basic Security Profile rule R4221).
    """
    state = obs_world.state()
    assert state["onvif_requests"] > 0
    assert state["onvif_invalid_nonce_encodings"] == 0
