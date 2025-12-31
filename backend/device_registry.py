from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, Optional


@dataclass(frozen=True)
class DeviceAssignment:
    device_id: str
    user_id: int


class DeviceRegistry:
    def __init__(self) -> None:
        self._devices: Dict[str, DeviceAssignment] = {}

    def list_devices(self) -> Iterable[DeviceAssignment]:
        return list(self._devices.values())

    def assign_device(self, device_id: str, user_id: int) -> DeviceAssignment:
        assignment = DeviceAssignment(device_id=device_id, user_id=user_id)
        self._devices[device_id] = assignment
        return assignment

    def get_device(self, device_id: str) -> Optional[DeviceAssignment]:
        return self._devices.get(device_id)


_REGISTRY: Optional[DeviceRegistry] = None


def get_device_registry() -> DeviceRegistry:
    global _REGISTRY  # noqa: PLW0603
    if _REGISTRY is None:
        _REGISTRY = DeviceRegistry()
    return _REGISTRY
