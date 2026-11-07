"""Test component setup."""

from pathlib import Path
from unittest.mock import MagicMock

from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.setup import async_setup_component
from pyhilo.signalr import SignalREvent
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.typing import WebSocketGenerator

from custom_components.hilo.const import (
    ACCOUNT_FILES,
    CONF_ACCOUNT_LABEL,
    CONF_TRACK_UNKNOWN_SOURCES,
    DOMAIN,
)

from . import ACCOUNT_EMAIL, account_id, oauth_token, setup_with_selected_platforms


async def test_async_setup(hass):
    """Test the component gets setup."""
    assert await async_setup_component(hass, DOMAIN, {}) is True


@pytest.mark.parametrize(
    ("identifier", "expected_success"),
    [
        pytest.param("2a3b4c5d6e7f", False, id="device_still_reported"),
        pytest.param("stale-device", True, id="device_no_longer_reported"),
    ],
)
async def test_remove_config_entry_device(
    hass: HomeAssistant,
    hass_ws_client: WebSocketGenerator,
    mock_config_entry: MockConfigEntry,
    device_registry: dr.DeviceRegistry,
    mock_api: MagicMock,
    identifier: str,
    expected_success: bool,
) -> None:
    """Test only devices no longer reported by Hilo can be removed."""
    assert await async_setup_component(hass, "config", {})
    await setup_with_selected_platforms(
        hass, mock_config_entry, [Platform.SWITCH], mock_api
    )
    device_entry = device_registry.async_get_or_create(
        config_entry_id=mock_config_entry.entry_id,
        identifiers={(DOMAIN, identifier)},
    )

    client = await hass_ws_client(hass)
    await client.send_json_auto_id(
        {
            "type": "config/device_registry/remove_config_entry",
            "config_entry_id": mock_config_entry.entry_id,
            "device_id": device_entry.id,
        }
    )
    response = await client.receive_json()

    assert response["success"] is expected_success
    assert (device_registry.async_get(device_entry.id) is None) is expected_success


async def test_remove_config_entry_device_unknown_source_tracker(
    hass: HomeAssistant,
    hass_ws_client: WebSocketGenerator,
    mock_config_entry: MockConfigEntry,
    device_registry: dr.DeviceRegistry,
    mock_api: MagicMock,
) -> None:
    """Test the unknown source tracker device cannot be removed while tracked."""
    assert await async_setup_component(hass, "config", {})
    mock_config_entry.add_to_hass(hass)
    hass.config_entries.async_update_entry(
        mock_config_entry, options={CONF_TRACK_UNKNOWN_SOURCES: True}
    )
    await setup_with_selected_platforms(hass, mock_config_entry, [], mock_api)
    device_entry = next(
        device
        for device in dr.async_entries_for_config_entry(
            device_registry, mock_config_entry.entry_id
        )
        if (DOMAIN, "hass-hilo-unknown_source_tracker") in device.identifiers
    )

    client = await hass_ws_client(hass)
    await client.send_json_auto_id(
        {
            "type": "config/device_registry/remove_config_entry",
            "config_entry_id": mock_config_entry.entry_id,
            "device_id": device_entry.id,
        }
    )
    response = await client.receive_json()

    assert response["success"] is False
    assert device_registry.async_get(device_entry.id) is not None


async def test_signalr_device_values_update_entity_state(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_api: MagicMock,
) -> None:
    """SignalR device values are written to the entity state right away.

    Without the per-device signal, new values would only appear on the next
    coordinator refresh (scan_interval).
    """
    await setup_with_selected_platforms(
        hass, mock_config_entry, [Platform.SENSOR], mock_api
    )
    event = SignalREvent(
        event_type_id=1,
        target="DevicesValuesReceived",
        arguments=[
            [
                {
                    "deviceId": 111000,
                    "locationId": 123,
                    "timeStampUTC": "2026-11-01T12:00:00Z",
                    "attribute": "CurrentTemperature",
                    "valueType": "Celsius",
                    "value": 21.5,
                }
            ]
        ],
        invocation=None,
        error=None,
    )

    await mock_config_entry.runtime_data.on_signalr_event(event)
    await hass.async_block_till_done()

    state = hass.states.get("sensor.thermostat_1_temperature")
    assert state is not None
    assert state.state == "21.5"


@pytest.mark.usefixtures("mock_setup_entry")
@pytest.mark.parametrize(
    ("legacy_file", "entry_file"),
    [
        pytest.param("hilo_state.yaml", "hilo_state_{}.yaml", id="api_state"),
        pytest.param(
            "hilo_eventhistory_state.yaml",
            "hilo_eventhistory_state_{}.yaml",
            id="event_history",
        ),
    ],
)
async def test_migration_hands_files_to_account(
    hass: HomeAssistant, tmp_path: Path, legacy_file: str, entry_file: str
) -> None:
    """Test the single-account files become the migrated account's files."""
    hass.config.config_dir = str(tmp_path)
    (tmp_path / legacy_file).write_text("legacy: true\n")
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={"auth_implementation": DOMAIN, "token": oauth_token(ACCOUNT_EMAIL)},
        unique_id=DOMAIN,
        version=2,
        minor_version=1,
    )
    entry.add_to_hass(hass)

    await hass.config_entries.async_setup(entry.entry_id)

    assert entry.minor_version == 3
    assert not (tmp_path / legacy_file).exists()
    assert (tmp_path / entry_file.format(account_id(ACCOUNT_EMAIL))).read_text() == (
        "legacy: true\n"
    )


@pytest.mark.usefixtures("mock_setup_entry")
async def test_remove_entry_keeps_account_files(
    hass: HomeAssistant, tmp_path: Path, mock_config_entry: MockConfigEntry
) -> None:
    """Test an account's files outlive its entry so re-adding it resumes them."""
    hass.config.config_dir = str(tmp_path)
    mock_config_entry.add_to_hass(hass)
    account_files = sorted(
        account_file.format(mock_config_entry.unique_id)
        for account_file in ACCOUNT_FILES.values()
    )
    for account_file in account_files:
        (tmp_path / account_file).touch()

    await hass.config_entries.async_remove(mock_config_entry.entry_id)

    assert sorted(path.name for path in tmp_path.iterdir()) == account_files


@pytest.mark.usefixtures("mock_setup_entry")
@pytest.mark.parametrize(
    ("minor_version", "unique_id", "data", "expected_label"),
    [
        pytest.param(1, DOMAIN, {}, "", id="single_account"),
        pytest.param(
            2,
            ACCOUNT_EMAIL,
            {CONF_ACCOUNT_LABEL: "Chalet"},
            "Chalet",
            id="keyed_by_email",
        ),
    ],
)
async def test_migration_keys_entry_by_account_id(
    hass: HomeAssistant,
    minor_version: int,
    unique_id: str,
    data: dict[str, str],
    expected_label: str,
) -> None:
    """Test entries are keyed by the account ID and keep their label."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            "auth_implementation": DOMAIN,
            "token": oauth_token(ACCOUNT_EMAIL),
            **data,
        },
        unique_id=unique_id,
        version=2,
        minor_version=minor_version,
    )
    entry.add_to_hass(hass)

    await hass.config_entries.async_setup(entry.entry_id)

    assert entry.minor_version == 3
    assert entry.unique_id == account_id(ACCOUNT_EMAIL)
    assert entry.data[CONF_ACCOUNT_LABEL] == expected_label
