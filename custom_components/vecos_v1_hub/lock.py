from __future__ import annotations

from datetime import datetime
import logging
from typing import Optional

from homeassistant.components.lock import LockEntity, LockEntityFeature
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST
from homeassistant.core import CALLBACK_TYPE, HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_call_later
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    DEFAULT_OPEN_DURATION,
    DOMAIN,
    NUMBER_OF_LOCKS,
    OPEN_DURATION,
    RELOCK_RETRY_INTERVAL,
)
from .coordinator import VecosV1HubCoordinator

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: VecosV1HubCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        [VecosLockEntity(coordinator, entry, lock_id) for lock_id in range(1, entry.data[NUMBER_OF_LOCKS] + 1)]
    )


class VecosLockEntity(CoordinatorEntity, RestoreEntity, LockEntity):
    _attr_supported_features = LockEntityFeature.OPEN

    def __init__(
        self, coordinator: VecosV1HubCoordinator, entry: ConfigEntry, lock_id: int
    ) -> None:
        super().__init__(coordinator)
        self.entry = entry
        self.lock_id = lock_id
        self._attr_is_locked = True
        self._attr_is_open = False
        self._open_duration = entry.data.get(OPEN_DURATION, DEFAULT_OPEN_DURATION)
        self._cancel_relock: CALLBACK_TYPE | None = None
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=f"Vecos V1 Hub ({entry.data[CONF_HOST]})",
            manufacturer="Vecos",
            model="V1 Hub",
        )
        coordinator.register_lock_entity(lock_id, self)

    @property
    def name(self) -> str:
        return f"Vecos Lock {self.lock_id}"

    @property
    def unique_id(self) -> str:
        return f"{self.entry.entry_id}_lock_{self.lock_id}"

    @property
    def is_locked(self) -> Optional[bool]:
        if getattr(self, "_attr_is_locked", None) is not None:
            return self._attr_is_locked
        data = self.coordinator.data
        if not data:
            return getattr(self, "_attr_is_locked", True)
        door_states = data.get("door_states")
        if not door_states:
            return getattr(self, "_attr_is_locked", True)
        return bool(door_states.get(self.lock_id))

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last_state = await self.async_get_last_state()
        if last_state is None:
            return
        # An open lock is only released for a short time, so a restart during
        # that window must not restore it as unlocked and drive it open again.
        if last_state.state in {"locked", "open", "opening"}:
            self._attr_is_locked = True
        elif last_state.state == "unlocked":
            self._attr_is_locked = False

    async def async_will_remove_from_hass(self) -> None:
        if self._cancel_relock is not None:
            self._cancel_pending_relock()
            try:
                await self.coordinator.async_set_lock_state(self.lock_id, 0)
            except OSError:
                _LOGGER.warning(
                    "Could not relock Vecos lock %s while unloading", self.lock_id
                )
        await super().async_will_remove_from_hass()

    def lock(self, **kwargs) -> None:
        self.hass.async_create_task(self.async_lock(**kwargs))

    def unlock(self, **kwargs) -> None:
        self.hass.async_create_task(self.async_unlock(**kwargs))

    async def async_lock(self, **kwargs) -> None:
        self._cancel_pending_relock()
        await self._async_set_state(0)

    async def async_unlock(self, **kwargs) -> None:
        self._cancel_pending_relock()
        await self._async_set_state(1)

    async def async_open(self, **kwargs) -> None:
        """Release the lock for the configured duration, then lock it again."""
        self._cancel_pending_relock()
        await self._async_set_state(1, is_open=True)
        self._schedule_relock(self._open_duration)

    async def _async_set_state(self, state: int, is_open: bool = False) -> None:
        await self.coordinator.async_set_lock_state(self.lock_id, state)
        self._attr_is_open = is_open
        self.async_write_ha_state()
        await self.coordinator.async_request_refresh()

    def _schedule_relock(self, delay: float) -> None:
        self._cancel_relock = async_call_later(self.hass, delay, self._async_relock)

    async def _async_relock(self, _now: datetime) -> None:
        self._cancel_relock = None
        try:
            await self._async_set_state(0)
        except OSError:
            # The hub keeps whatever it was last told, so keep trying until the
            # lock is actually closed again.
            _LOGGER.warning(
                "Could not relock Vecos lock %s, retrying in %s seconds",
                self.lock_id,
                RELOCK_RETRY_INTERVAL,
            )
            self._schedule_relock(RELOCK_RETRY_INTERVAL)

    def _cancel_pending_relock(self) -> None:
        if self._cancel_relock is not None:
            self._cancel_relock()
            self._cancel_relock = None

    async def async_update(self) -> None:
        await self.coordinator.async_request_refresh()