"""Tests for the SNCF Trains integration setup and config entry migration."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.config_entries import ConfigSubentryData
from homeassistant.const import EVENT_HOMEASSISTANT_STARTED
from homeassistant.core import CoreState
from homeassistant.exceptions import ConfigEntryNotReady
from pytest_homeassistant_custom_component.common import MockConfigEntry

import custom_components.sncf_trains as sncf
from custom_components.sncf_trains.const import (
    CONF_API_KEY,
    CONF_ARRIVAL_NAME,
    CONF_DEPARTURE_NAME,
    CONF_FROM,
    CONF_TIME_END,
    CONF_TIME_START,
    CONF_TO,
    CONF_TRAIN_COUNT,
    DOMAIN,
)


# --- async_setup: Lovelace card registration ---------------------------------


async def test_setup_registers_card_when_home_assistant_is_running(hass):
    hass.set_state(CoreState.running)
    hass.http = MagicMock(async_register_static_paths=AsyncMock())

    with patch.object(sncf, "add_extra_js_url") as add_js:
        assert await sncf.async_setup(hass, {})

    hass.http.async_register_static_paths.assert_awaited_once()
    (static_path,) = hass.http.async_register_static_paths.await_args.args[0]
    assert static_path.url_path == sncf.CARD_URL
    assert static_path.path == str(sncf.CARD_FILE)
    add_js.assert_called_once_with(hass, sncf.CARD_URL)


async def test_setup_defers_card_registration_until_started(hass):
    hass.set_state(CoreState.starting)
    hass.http = MagicMock(async_register_static_paths=AsyncMock())

    with patch.object(sncf, "add_extra_js_url") as add_js:
        assert await sncf.async_setup(hass, {})

        hass.http.async_register_static_paths.assert_not_awaited()
        add_js.assert_not_called()

        hass.bus.async_fire(EVENT_HOMEASSISTANT_STARTED)
        await hass.async_block_till_done()

    hass.http.async_register_static_paths.assert_awaited_once()
    add_js.assert_called_once_with(hass, sncf.CARD_URL)


def test_card_file_exists():
    assert sncf.CARD_FILE.is_file()


# --- async_setup_entry / unload / reload -------------------------------------


async def test_setup_entry_stores_coordinator_and_forwards_platforms(hass):
    entry = MagicMock()
    coordinator = MagicMock()
    coordinator.async_config_entry_first_refresh = AsyncMock()

    with (
        patch.object(sncf, "SncfUpdateCoordinator", return_value=coordinator) as cls,
        patch.object(
            hass.config_entries, "async_forward_entry_setups", AsyncMock()
        ) as forward,
    ):
        assert await sncf.async_setup_entry(hass, entry)

    cls.assert_called_once_with(hass, entry)
    coordinator.async_config_entry_first_refresh.assert_awaited_once()
    assert entry.runtime_data is coordinator
    forward.assert_awaited_once_with(entry, sncf.PLATFORMS)
    entry.add_update_listener.assert_called_once_with(sncf.async_reload_entry)
    entry.async_on_unload.assert_called_once()


async def test_setup_entry_propagates_first_refresh_failure(hass):
    entry = MagicMock()
    coordinator = MagicMock()
    coordinator.async_config_entry_first_refresh = AsyncMock(
        side_effect=ConfigEntryNotReady
    )

    with (
        patch.object(sncf, "SncfUpdateCoordinator", return_value=coordinator),
        patch.object(
            hass.config_entries, "async_forward_entry_setups", AsyncMock()
        ) as forward,
        pytest.raises(ConfigEntryNotReady),
    ):
        await sncf.async_setup_entry(hass, entry)

    forward.assert_not_awaited()


@pytest.mark.parametrize("unloaded", [True, False])
async def test_unload_entry_returns_platform_unload_result(hass, unloaded):
    entry = MagicMock()
    with patch.object(
        hass.config_entries, "async_unload_platforms", AsyncMock(return_value=unloaded)
    ) as unload:
        assert await sncf.async_unload_entry(hass, entry) is unloaded
    unload.assert_awaited_once_with(entry, sncf.PLATFORMS)


async def test_reload_entry_reloads_the_config_entry(hass):
    entry = MagicMock(entry_id="entry_1")
    with patch.object(hass.config_entries, "async_reload", AsyncMock()) as reload:
        await sncf.async_reload_entry(hass, entry)
    reload.assert_awaited_once_with("entry_1")


# --- async_migrate_entry -----------------------------------------------------


def _legacy_entry(*, data=None, options=None, **kwargs) -> MockConfigEntry:
    """Return an entry as created before subentries existed (version 1.1)."""
    return MockConfigEntry(
        domain=DOMAIN,
        version=1,
        minor_version=1,
        title="Trains SNCF",
        unique_id=None,
        data=data if data is not None else {},
        options=options if options is not None else {},
        **kwargs,
    )


async def test_migration_converts_legacy_journey_into_subentry(hass):
    entry = _legacy_entry(
        data={
            CONF_API_KEY: "key",
            CONF_FROM: "stop_area:A",
            CONF_TO: "stop_area:B",
            CONF_DEPARTURE_NAME: "Gare A",
            CONF_ARRIVAL_NAME: "Gare B",
        },
        options={
            CONF_TIME_START: "06:30",
            CONF_TIME_END: "09:00",
            CONF_TRAIN_COUNT: 3,
        },
    )
    entry.add_to_hass(hass)

    assert await sncf.async_migrate_entry(hass, entry)

    assert (entry.version, entry.minor_version) == (1, 2)
    assert entry.unique_id == "sncf_trains"
    # Legacy journey keys leave the entry itself
    assert dict(entry.data) == {CONF_API_KEY: "key"}
    assert dict(entry.options) == {}

    assert len(entry.subentries) == 1
    subentry = next(iter(entry.subentries.values()))
    assert subentry.subentry_type == "train"
    assert subentry.subentry_id == f"{entry.entry_id}_MIGRATE"
    assert subentry.title == "Trajet: Gare A → Gare B (06:30 - 09:00)"
    assert subentry.unique_id == "stop_area:A_stop_area:B_06:30_09:00"
    assert dict(subentry.data) == {
        CONF_FROM: "stop_area:A",
        CONF_TO: "stop_area:B",
        CONF_DEPARTURE_NAME: "Gare A",
        CONF_ARRIVAL_NAME: "Gare B",
        CONF_TIME_START: "06:30",
        CONF_TIME_END: "09:00",
        CONF_TRAIN_COUNT: 3,
    }


async def test_migration_uses_defaults_and_ids_as_names(hass):
    entry = _legacy_entry(
        data={CONF_API_KEY: "key", CONF_FROM: "stop_area:A", CONF_TO: "stop_area:B"}
    )
    entry.add_to_hass(hass)

    assert await sncf.async_migrate_entry(hass, entry)

    subentry = next(iter(entry.subentries.values()))
    assert subentry.title == "Trajet: stop_area:A → stop_area:B (07:00 - 10:00)"
    assert subentry.data[CONF_TIME_START] == "07:00"
    assert subentry.data[CONF_TIME_END] == "10:00"
    assert subentry.data[CONF_TRAIN_COUNT] == 5
    assert subentry.data[CONF_DEPARTURE_NAME] == "stop_area:A"
    assert subentry.data[CONF_ARRIVAL_NAME] == "stop_area:B"


async def test_migration_reads_journey_settings_from_data_when_not_in_options(hass):
    entry = _legacy_entry(
        data={
            CONF_API_KEY: "key",
            CONF_FROM: "A",
            CONF_TO: "B",
            CONF_TIME_START: "05:00",
            CONF_TIME_END: "06:00",
            CONF_TRAIN_COUNT: 2,
        }
    )
    entry.add_to_hass(hass)

    assert await sncf.async_migrate_entry(hass, entry)

    subentry = next(iter(entry.subentries.values()))
    assert subentry.data[CONF_TIME_START] == "05:00"
    assert subentry.data[CONF_TIME_END] == "06:00"
    assert subentry.data[CONF_TRAIN_COUNT] == 2
    assert CONF_TIME_START not in entry.data


async def test_migration_moves_api_key_from_options_to_data(hass):
    entry = _legacy_entry(options={CONF_API_KEY: "key"})
    entry.add_to_hass(hass)

    assert await sncf.async_migrate_entry(hass, entry)

    assert entry.data[CONF_API_KEY] == "key"
    assert CONF_API_KEY not in entry.options
    assert entry.minor_version == 2


async def test_migration_does_not_overwrite_existing_api_key(hass):
    entry = _legacy_entry(
        data={CONF_API_KEY: "from_data"}, options={CONF_API_KEY: "from_options"}
    )
    entry.add_to_hass(hass)

    assert await sncf.async_migrate_entry(hass, entry)

    assert entry.data[CONF_API_KEY] == "from_data"


async def test_migration_without_legacy_journey_creates_no_subentry(hass):
    entry = _legacy_entry(data={CONF_API_KEY: "key"})
    entry.add_to_hass(hass)

    assert await sncf.async_migrate_entry(hass, entry)

    assert not entry.subentries
    assert entry.minor_version == 2


async def test_migration_keeps_existing_subentries(hass):
    existing = ConfigSubentryData(
        data={CONF_FROM: "X", CONF_TO: "Y"},
        subentry_id="existing",
        subentry_type="train",
        title="Déjà là",
        unique_id="existing_unique_id",
    )
    entry = _legacy_entry(
        data={CONF_API_KEY: "key", CONF_FROM: "A", CONF_TO: "B"},
        subentries_data=[existing],
    )
    entry.add_to_hass(hass)

    assert await sncf.async_migrate_entry(hass, entry)

    assert list(entry.subentries) == ["existing"]


async def test_migration_is_idempotent(hass):
    entry = _legacy_entry(
        data={CONF_API_KEY: "key", CONF_FROM: "A", CONF_TO: "B"},
    )
    entry.add_to_hass(hass)

    assert await sncf.async_migrate_entry(hass, entry)
    first = {k: v.data for k, v in entry.subentries.items()}

    assert await sncf.async_migrate_entry(hass, entry)

    assert {k: v.data for k, v in entry.subentries.items()} == first
    assert dict(entry.data) == {CONF_API_KEY: "key"}


async def test_migration_leaves_up_to_date_entry_untouched(hass):
    entry = MockConfigEntry(
        domain=DOMAIN,
        version=1,
        minor_version=2,
        unique_id="sncf_trains",
        data={CONF_API_KEY: "key"},
    )
    entry.add_to_hass(hass)

    assert await sncf.async_migrate_entry(hass, entry)

    assert dict(entry.data) == {CONF_API_KEY: "key"}
    assert not entry.subentries


async def test_migration_refuses_entry_from_a_newer_version(hass):
    entry = MockConfigEntry(domain=DOMAIN, version=2, minor_version=0, data={})
    entry.add_to_hass(hass)

    assert await sncf.async_migrate_entry(hass, entry) is False
