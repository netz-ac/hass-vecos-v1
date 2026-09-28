# Vecos V1 Hub for Home Assistant

This custom component adds support for the Vecos V1 Hub controller to Home Assistant. It provides lock entities for each door, a USB‑power switch, binary sensors for connection status, and convenient services to open or close multiple locks at once.

NOTE: Since we don't have access to the original Vecos V1 Hub documentation, this integration requires the use of our custom Vecos V1 Hub firmware, which exposes a simple Serial interface for controlling the locks. We then use a Serial to TCP bridge to communicate with Home Assistant.

Please refer to the firmware repository: https://github.com/netz-ac/V1-Hub-Firmware


## Features
* Up to 16 locks (configurable via UI)
* Real‑time lock state synchronization (optimistic updates)
* USB power control as a switch entity
* Binary sensors for each lock’s connection status
* Services: vecos_v1_hub.open_locks & vecos_v1_hub.close_locks
* Restores last known state after Home Assistant restarts


## Installation
### HACS (recommended)

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=netz-ac&repository=hass-vecos-v1&category=integration)

* Open HACS → Integrations.
* Click the three‑dot menu → Custom repositories.
* Add the repository URL: https://github.com/netz-ac/hass-vecos-v1 and select Integration.
* Click Add → Install the integration.


#### Manual
* Clone or download the repository.
* Copy the custom_components/vecos_v1_hub folder into your Home Assistant custom_components directory.
* Restart Home Assistant.
* Configuration
* Add the integration via Settings → Devices & Services → Add Integration → Vecos V1 Hub.

Field    | Description | Default
---------|-------------|--------
host	 | IP address or hostname of the hub |–
port	 | TCP port  | 5000
lock_count	 | Number of locks to expose (1‑16) | 16
open_duration	 | Seconds a lock stays released after `lock.open` before it is locked again (1‑3600) | 5

The lock_count option makes the integration flexible for hubs with fewer than 16 doors.

## Entities
Entity type |	Entity ID pattern |	Description
-----------|--------------------|---------
Lock |	lock.vecos_lock_<n>	| Lock # n (locked/unlocked)
Switch |	switch.vecos_usb_power	| USB power on/off
Binary sensor |	binary_sensor.vecos_connection_<n>	| Connection status for lock n

`lock.open` releases the lock for `open_duration` seconds and then locks it again automatically, retrying if the hub is unreachable. `lock.unlock` keeps the lock unlocked until `lock.lock` is called. A lock that was open when Home Assistant restarted is restored as locked.


## Services
Service	| Description | Service data
--------|-------------|-------------
vecos_v1_hub.open_locks	| Unlock one or more locks|entry_id (string), lock_ids (list of ints)
vecos_v1_hub.close_locks	| Lock one or more locks|entry_id (string), lock_ids (list of ints)

## License
This project is licensed under the MIT License. See the LICENSE file for details.

# Disclaimer
Vecos is a registered trademark of Vecos IPCo B.V. This project is an independent development and is not affiliated with or endorsed by Vecos. The integration is provided as-is, without any guarantees or warranties. Use this firmware at your own risk.
