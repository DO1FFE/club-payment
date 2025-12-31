from dataclasses import dataclass
from typing import Dict, List, Optional


@dataclass(frozen=True)
class DeviceAssignment:
    device_id: str
    user_id: str
    role: str


_registry: Dict[str, DeviceAssignment] = {}


def register_device(device_id: str, user_id: str, role: str) -> DeviceAssignment:
    assignment = DeviceAssignment(device_id=device_id, user_id=user_id, role=role)
    _registry[device_id] = assignment
    return assignment


def get_device(device_id: str) -> Optional[DeviceAssignment]:
    return _registry.get(device_id)


def list_devices() -> List[DeviceAssignment]:
    return list(_registry.values())


def reset_registry() -> None:
    _registry.clear()
