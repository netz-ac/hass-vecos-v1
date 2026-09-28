from __future__ import annotations

from typing import Optional

from homeassistant.components.lock import LockEntity, LockEntityFeature
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, NUMBER_OF_LOCKS
from .coordinator import VecosV1HubCoordinator

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
        if last_state.state == "locked":
            self._attr_is_locked = True
        elif last_state.state in {"unlocked", "open"}:
            self._attr_is_locked = False

    def lock(self, **kwargs) -> None:
        self.hass.async_create_task(self.async_lock(**kwargs))

    def unlock(self, **kwargs) -> None:
        self.hass.async_create_task(self.async_unlock(**kwargs))

    async def async_lock(self, **kwargs) -> None:
        await self.coordinator.async_set_lock_state(self.lock_id, 0)
        await self.coordinator.async_request_refresh()

    async def async_unlock(self, **kwargs) -> None:
        await self.coordinator.async_set_lock_state(self.lock_id, 1)
        await self.coordinator.async_request_refresh()

    async def async_open(self, **kwargs) -> None:
        await self.async_unlock(**kwargs)

    async def async_update(self) -> None:
        await self.coordinator.async_request_refresh()