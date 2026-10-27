"""Test component setup."""

from unittest.mock import MagicMock

from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.hilo.const import CONF_LOG_TRACES, DOMAIN

from . import setup_with_selected_platforms


async def test_async_setup(hass):
    """Test the component gets setup."""
    assert await async_setup_component(hass, DOMAIN, {}) is True


async def test_unload_removes_debug_listener(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry, mock_api: MagicMock
) -> None:
    """Test unloading stops listening for hilo_debug events."""
    mock_config_entry.add_to_hass(hass)
    hass.config_entries.async_update_entry(
        mock_config_entry, options={CONF_LOG_TRACES: True}
    )
    await setup_with_selected_platforms(
        hass, mock_config_entry, [Platform.SWITCH], mock_api
    )
    assert "hilo_debug" in hass.bus.async_listeners()

    await hass.config_entries.async_unload(mock_config_entry.entry_id)

    assert "hilo_debug" not in hass.bus.async_listeners()
