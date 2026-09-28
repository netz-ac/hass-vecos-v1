from __future__ import annotations

from datetime import timedelta
from typing import Optional
from unittest.mock import AsyncMock, call

from homeassistant.const import CONF_PORT
from homeassistant.core import State
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)

from custom_components.vecos_v1_hub.const import (
    DEFAULT_OPEN_DURATION,
    DOMAIN,
    RELOCK_RETRY_INTERVAL,
)
from custom_components.vecos_v1_hub.coordinator import VecosV1HubCoordinator
from custom_components.vecos_v1_hub.lock import VecosLockEntity, async_setup_entry


def _create_entry() -> MockConfigEntry:
    return MockConfigEntry(
        domain=DOMAIN,
        data={"host": "127.0.0.1", CONF_PORT: 5000},
        entry_id="test-entry",
    )


def _create_coordinator(
    hass, data: Optional[dict] = None
) -> VecosV1HubCoordinator:
    client = AsyncMock()
    client.get_status = AsyncMock(return_value=data)
    coordinator = VecosV1HubCoordinator(hass, client, "test-entry")
    coordinator.data = data
    coordinator.async_request_refresh = AsyncMock()
    return coordinator


def _create_entity(hass, coordinator, entry, lock_id: int = 1) -> VecosLockEntity:
    entity = VecosLockEntity(coordinator, entry, lock_id)
    entity.hass = hass
    entity.entity_id = f"lock.vecos_lock_{lock_id}"
    return entity


async def _advance(hass, seconds: float) -> None:
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=seconds))
    await hass.async_block_till_done()


async def test_async_setup_entry_adds_lock_entities(hass):
    entry = _create_entry()
    coordinator = _create_coordinator(hass, {"door_states": {}, "connection_states": {}})
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator

    entities = []

    def async_add_entities(new_entities):
        entities.extend(new_entities)

    await async_setup_entry(hass, entry, async_add_entities)

    assert len(entities) == 16
    assert isinstance(entities[0], VecosLockEntity)
    assert entities[0].unique_id == "test-entry_lock_1"
    assert entities[-1].unique_id == "test-entry_lock_16"


async def test_lock_entity_state_reflects_coordinator_data(hass):
    entry = _create_entry()
    coordinator = _create_coordinator(
        hass,
        {
            "door_states": {1: 1, 2: 0},
            "connection_states": {},
            "usb_power": 0,
            "usb_feedback": 0,
        },
    )

    locked = VecosLockEntity(coordinator, entry, 1)
    unlocked = VecosLockEntity(coordinator, entry, 2)

    assert locked.is_locked is True
    assert unlocked.is_locked is False


async def test_lock_entity_defaults_to_locked_without_data(hass):
    entry = _create_entry()
    coordinator = _create_coordinator(hass, None)

    entity = VecosLockEntity(coordinator, entry, 1)

    assert entity.is_locked is True


async def test_lock_entity_calls_client_and_refresh_on_lock_and_unlock(hass):
    entry = _create_entry()
    coordinator = _create_coordinator(hass, {"door_states": {1: 1}})
    coordinator.async_set_lock_state = AsyncMock()

    entity = _create_entity(hass, coordinator, entry)

    await entity.async_unlock()
    coordinator.async_set_lock_state.assert_awaited_once_with(1, 1)
    coordinator.async_request_refresh.assert_awaited_once()

    coordinator.async_set_lock_state.reset_mock()
    coordinator.async_request_refresh.reset_mock()

    await entity.async_lock()
    coordinator.async_set_lock_state.assert_awaited_once_with(1, 0)
    coordinator.async_request_refresh.assert_awaited_once()


async def test_lock_entity_sync_wrappers_delegate_to_async(hass):
    entry = _create_entry()
    coordinator = _create_coordinator(hass, {"door_states": {1: 1}})
    coordinator.async_set_lock_state = AsyncMock()

    entity = _create_entity(hass, coordinator, entry)

    entity.lock()
    entity.unlock()

    await hass.async_block_till_done()

    assert coordinator.async_set_lock_state.await_args_list == [
        call(1, 0),
        call(1, 1),
    ]
    assert coordinator.async_request_refresh.await_count == 2


async def test_lock_entity_keeps_optimistic_state_when_coordinator_is_stale(hass):
    entry = _create_entry()
    coordinator = _create_coordinator(hass, {"door_states": {1: 0}})

    entity = _create_entity(hass, coordinator, entry)

    await entity.async_lock()

    assert entity.is_locked is True


async def test_open_relocks_after_open_duration(hass):
    entry = _create_entry()
    coordinator = _create_coordinator(hass, {"door_states": {1: 1}})
    entity = _create_entity(hass, coordinator, entry)

    await entity.async_open()

    assert entity.is_locked is False
    assert entity.state == "open"
    coordinator.client.send_command.assert_awaited_once_with(0x80, 0, 0)

    await _advance(hass, DEFAULT_OPEN_DURATION - 1)
    assert entity.state == "open"

    await _advance(hass, DEFAULT_OPEN_DURATION + 1)
    assert entity.state == "locked"
    assert coordinator.client.send_command.await_args_list[-1] == call(0, 0, 0)
    assert coordinator._last_command_bytes == (0, 0, 0)


async def test_open_uses_configured_open_duration(hass):
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={"host": "127.0.0.1", CONF_PORT: 5000, "Open Duration (seconds)": 30},
        entry_id="test-entry",
    )
    coordinator = _create_coordinator(hass, {"door_states": {1: 1}})
    entity = _create_entity(hass, coordinator, entry)

    await entity.async_open()
    await _advance(hass, DEFAULT_OPEN_DURATION + 1)
    assert entity.state == "open"

    await _advance(hass, 31)
    assert entity.state == "locked"


async def test_explicit_unlock_cancels_pending_relock(hass):
    entry = _create_entry()
    coordinator = _create_coordinator(hass, {"door_states": {1: 1}})
    entity = _create_entity(hass, coordinator, entry)

    await entity.async_open()
    await entity.async_unlock()
    await _advance(hass, DEFAULT_OPEN_DURATION + 1)

    assert entity.state == "unlocked"
    assert coordinator.client.send_command.await_count == 2


async def test_relock_retries_when_hub_is_unreachable(hass):
    entry = _create_entry()
    coordinator = _create_coordinator(hass, {"door_states": {1: 1}})
    entity = _create_entity(hass, coordinator, entry)

    await entity.async_open()
    coordinator.client.send_command.side_effect = OSError("hub offline")
    await _advance(hass, DEFAULT_OPEN_DURATION + 1)
    assert entity.state == "open"

    coordinator.client.send_command.side_effect = None
    await _advance(hass, DEFAULT_OPEN_DURATION + RELOCK_RETRY_INTERVAL + 2)
    assert entity.state == "locked"
    assert coordinator.client.send_command.await_args_list[-1] == call(0, 0, 0)


async def test_removal_relocks_open_lock(hass):
    entry = _create_entry()
    coordinator = _create_coordinator(hass, {"door_states": {1: 1}})
    entity = _create_entity(hass, coordinator, entry)

    await entity.async_open()
    coordinator.async_set_lock_state = AsyncMock()
    await entity.async_will_remove_from_hass()

    coordinator.async_set_lock_state.assert_awaited_once_with(1, 0)
    await _advance(hass, DEFAULT_OPEN_DURATION + 1)
    coordinator.async_set_lock_state.assert_awaited_once()


async def test_restore_treats_open_as_locked(hass):
    entry = _create_entry()
    coordinator = _create_coordinator(hass, {"door_states": {}})

    for last_state, expected_locked in (
        ("open", True),
        ("opening", True),
        ("locked", True),
        ("unlocked", False),
    ):
        entity = _create_entity(hass, coordinator, entry)
        entity.async_get_last_state = AsyncMock(
            return_value=State(entity.entity_id, last_state)
        )
        await entity.async_added_to_hass()
        assert entity.is_locked is expected_locked, last_state