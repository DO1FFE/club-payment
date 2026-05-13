from __future__ import annotations

from datetime import datetime, timezone
from dataclasses import dataclass
from typing import Iterable, Optional

from database import DeviceAssignmentRecord, PendingDeviceRecord, SessionLocal, init_database


@dataclass(frozen=True)
class DeviceAssignment:
    device_id: str
    user_id: int


@dataclass(frozen=True)
class PendingDevice:
    device_id: str
    user_id: Optional[int]
    username: Optional[str]
    last_seen_at: datetime


class DeviceRegistry:
    @staticmethod
    def _to_assignment(record: DeviceAssignmentRecord) -> DeviceAssignment:
        return DeviceAssignment(device_id=record.device_id, user_id=record.user_id)

    @staticmethod
    def _to_pending_device(record: PendingDeviceRecord) -> PendingDevice:
        return PendingDevice(
            device_id=record.device_id,
            user_id=record.user_id,
            username=record.username,
            last_seen_at=record.last_seen_at,
        )

    def list_devices(self) -> Iterable[DeviceAssignment]:
        with SessionLocal() as session:
            records = session.query(DeviceAssignmentRecord).order_by(DeviceAssignmentRecord.device_id.asc()).all()
            return [self._to_assignment(record) for record in records]

    def assign_device(self, device_id: str, user_id: int) -> DeviceAssignment:
        normalized_device_id = device_id.strip()
        with SessionLocal() as session:
            record = session.get(DeviceAssignmentRecord, normalized_device_id)
            if not record:
                record = DeviceAssignmentRecord(device_id=normalized_device_id, user_id=user_id)
                session.add(record)
            else:
                record.user_id = user_id
            pending = session.get(PendingDeviceRecord, normalized_device_id)
            if pending:
                session.delete(pending)
            session.commit()
            session.refresh(record)
            return self._to_assignment(record)

    def get_device(self, device_id: str) -> Optional[DeviceAssignment]:
        with SessionLocal() as session:
            record = session.get(DeviceAssignmentRecord, device_id.strip())
            return self._to_assignment(record) if record else None

    def remember_pending_device(
        self,
        device_id: str,
        user_id: Optional[int] = None,
        username: Optional[str] = None,
    ) -> Optional[PendingDevice]:
        normalized_device_id = device_id.strip()
        if not normalized_device_id:
            return None
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        with SessionLocal() as session:
            if session.get(DeviceAssignmentRecord, normalized_device_id):
                pending = session.get(PendingDeviceRecord, normalized_device_id)
                if pending:
                    session.delete(pending)
                    session.commit()
                return None

            record = session.get(PendingDeviceRecord, normalized_device_id)
            if not record:
                record = PendingDeviceRecord(device_id=normalized_device_id)
                session.add(record)
            record.user_id = user_id
            record.username = username
            record.last_seen_at = now
            session.commit()
            session.refresh(record)
            return self._to_pending_device(record)

    def list_pending_devices(self) -> Iterable[PendingDevice]:
        with SessionLocal() as session:
            assigned_device_ids = {
                device_id
                for (device_id,) in session.query(DeviceAssignmentRecord.device_id).all()
            }
            records = (
                session.query(PendingDeviceRecord)
                .order_by(PendingDeviceRecord.last_seen_at.desc(), PendingDeviceRecord.device_id.asc())
                .all()
            )
            return [
                self._to_pending_device(record)
                for record in records
                if record.device_id not in assigned_device_ids
            ]

    def delete_device(self, device_id: str) -> bool:
        with SessionLocal() as session:
            record = session.get(DeviceAssignmentRecord, device_id.strip())
            if not record:
                return False
            session.delete(record)
            session.commit()
            return True

    def delete_devices_for_user(self, user_id: int) -> None:
        with SessionLocal() as session:
            for record in session.query(DeviceAssignmentRecord).filter(DeviceAssignmentRecord.user_id == user_id).all():
                session.delete(record)
            for record in session.query(PendingDeviceRecord).filter(PendingDeviceRecord.user_id == user_id).all():
                session.delete(record)
            session.commit()


_REGISTRY: Optional[DeviceRegistry] = None


def get_device_registry() -> DeviceRegistry:
    global _REGISTRY  # noqa: PLW0603
    if _REGISTRY is None:
        init_database()
        _REGISTRY = DeviceRegistry()
    return _REGISTRY
