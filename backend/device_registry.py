from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Optional

from database import DeviceAssignmentRecord, SessionLocal, init_database


@dataclass(frozen=True)
class DeviceAssignment:
    device_id: str
    user_id: int


class DeviceRegistry:
    @staticmethod
    def _to_assignment(record: DeviceAssignmentRecord) -> DeviceAssignment:
        return DeviceAssignment(device_id=record.device_id, user_id=record.user_id)

    def list_devices(self) -> Iterable[DeviceAssignment]:
        with SessionLocal() as session:
            records = session.query(DeviceAssignmentRecord).order_by(DeviceAssignmentRecord.device_id.asc()).all()
            return [self._to_assignment(record) for record in records]

    def assign_device(self, device_id: str, user_id: int) -> DeviceAssignment:
        with SessionLocal() as session:
            record = session.get(DeviceAssignmentRecord, device_id)
            if not record:
                record = DeviceAssignmentRecord(device_id=device_id, user_id=user_id)
                session.add(record)
            else:
                record.user_id = user_id
            session.commit()
            session.refresh(record)
            return self._to_assignment(record)

    def get_device(self, device_id: str) -> Optional[DeviceAssignment]:
        with SessionLocal() as session:
            record = session.get(DeviceAssignmentRecord, device_id)
            return self._to_assignment(record) if record else None


_REGISTRY: Optional[DeviceRegistry] = None


def get_device_registry() -> DeviceRegistry:
    global _REGISTRY  # noqa: PLW0603
    if _REGISTRY is None:
        init_database()
        _REGISTRY = DeviceRegistry()
    return _REGISTRY
