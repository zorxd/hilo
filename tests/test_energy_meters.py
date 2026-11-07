"""Tests for the generated energy meters."""

from unittest.mock import MagicMock

from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.setup import async_setup_component
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.hilo.const import CONF_GENERATE_ENERGY_METERS, DOMAIN

from . import setup_with_selected_platforms


# utility_meter schedules its daily reset when its meters are added.
@pytest.mark.parametrize("expected_lingering_timers", [True])
@pytest.mark.parametrize(
    ("energy_unique_id", "energy_entity_id"),
    [
        pytest.param(
            "2a3b4c5d6e7f-energy", "sensor.living_room_plug_hilo_energy", id="device"
        ),
        pytest.param(
            "0x006baa0000000001-smart_meter-energy",
            "sensor.compteur_hilo_energy",
            id="smart_meter",
        ),
    ],
)
async def test_meters_follow_registered_energy_sensor(
    hass: HomeAssistant,
    entity_registry: er.EntityRegistry,
    mock_config_entry: MockConfigEntry,
    mock_api: MagicMock,
    energy_unique_id: str,
    energy_entity_id: str,
) -> None:
    """Test meters use the energy sensor's entity_id, not its current name."""
    # Home Assistant loads it before Hilo through after_dependencies.
    assert await async_setup_component(hass, "utility_meter", {})
    mock_config_entry.add_to_hass(hass)
    hass.config_entries.async_update_entry(
        mock_config_entry, options={CONF_GENERATE_ENERGY_METERS: True}
    )
    entity_registry.async_get_or_create(
        Platform.SENSOR,
        DOMAIN,
        energy_unique_id,
        config_entry=mock_config_entry,
        suggested_object_id=energy_entity_id.removeprefix("sensor."),
    )

    await setup_with_selected_platforms(
        hass, mock_config_entry, [Platform.SENSOR], mock_api
    )

    assert hass.states.get(f"{energy_entity_id}_low") is not None
