import pytest

from mec_safety.config import Layer2Config, _required_setting


@pytest.mark.parametrize(
    "value",
    ["", "YOUR_AE_ORIGINATOR", "placeholder", "<set-this>"],
)
def test_required_setting_rejects_missing_or_placeholder_values(monkeypatch, value):
    monkeypatch.setenv("TEST_REQUIRED_SETTING", value)

    with pytest.raises(ValueError, match="TEST_REQUIRED_SETTING"):
        _required_setting("TEST_REQUIRED_SETTING")


def test_layer2_config_exposes_required_environment_settings():
    assert Layer2Config.CSE_BASE_URL
    assert Layer2Config.CSE_BASE_NAME
    assert Layer2Config.CSE_RVI
    assert Layer2Config.AE_NAME
    assert Layer2Config.AE_ID
    assert set(Layer2Config.FCNT_RI) == {
        "device1",
        "device2",
        "device3",
        "device4",
        "device5",
        "risk",
    }
    assert all(Layer2Config.FCNT_RI.values())
