from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable, Optional

from database import DeviceAssignmentRecord, PendingDeviceRecord, SessionLocal, init_database
from organizations import get_organization_store


@dataclass(frozen=True)
class DeviceAssignment:
    device_id: str
    user_id: int
    organization_id: int


@dataclass(frozen=True)
class PendingDevice:
    device_id: str
    user_id: Optional[int]
    username: Optional[str]
    organization_id: Optional[int]
    last_seen_at: datetime


class DeviceRegistry:
    @staticmethod
    def _to_assignment(record: DeviceAssignmentRecord) -> DeviceAssignment:
        return DeviceAssignment(
            device_id=record.device_id,
            user_id=record.user_id,
            organization_id=record.organization_id,
        )

    @staticmethod
    def _to_pending_device(record: PendingDeviceRecord) -> PendingDevice:
        return PendingDevice(
            device_id=record.device_id,
            user_id=record.user_id,
            username=record.username,
            organization_id=record.organization_id,
            last_seen_at=record.last_seen_at,
        )

    def list_devices(self, organization_id: int | None = None) -> Iterable[DeviceAssignment]:
        with SessionLocal() as session:
            query = session.query(DeviceAssignmentRecord)
            if organization_id is not None:
                query = query.filter(DeviceAssignmentRecord.organization_id == organization_id)
            records = query.order_by(DeviceAssignmentRecord.device_id.asc()).all()
            return [self._to_assignment(record) for record in records]

    def assign_device(
        self,
        device_id: str,
        user_id: int,
        organization_id: int | None = None,
    ) -> DeviceAssignment:
        normalized_device_id = device_id.strip()
        organization_id = organization_id or get_organization_store().ensure_default_organization().id
        with SessionLocal() as session:
            record = session.get(DeviceAssignmentRecord, normalized_device_id)
            if not record:
                record = DeviceAssignmentRecord(
                    device_id=normalized_device_id,
                    user_id=user_id,
                    organization_id=organization_id,
                )
                session.add(record)
            else:
                record.user_id = user_id
                record.organization_id = organization_id
            pending = session.get(PendingDeviceRecord, normalized_device_id)
            if pending:
                session.delete(pending)
            session.commit()
            session.refresh(record)
            return self._to_assignment(record)

    def get_device(self, device_id: str, organization_id: int | None = None) -> Optional[DeviceAssignment]:
        with SessionLocal() as session:
            record = session.get(DeviceAssignmentRecord, device_id.strip())
            if not record:
                return None
            if organization_id is not None and record.organization_id != organization_id:
                return None
            return self._to_assignment(record)

    def remember_pending_device(
        self,
        device_id: str,
        user_id: Optional[int] = None,
        username: Optional[str] = None,
        organization_id: Optional[int] = None,
    ) -> Optional[PendingDevice]:
        normalized_device_id = device_id.strip()
        if not normalized_device_id:
            return None
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        with SessionLocal() as session:
            assignment = session.get(DeviceAssignmentRecord, normalized_device_id)
            if assignment and (organization_id is None or assignment.organization_id == organization_id):
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
            record.organization_id = organization_id
            record.last_seen_at = now
            session.commit()
            session.refresh(record)
            return self._to_pending_device(record)

    def list_pending_devices(self, organization_id: int | None = None) -> Iterable[PendingDevice]:
        with SessionLocal() as session:
            assigned_query = session.query(DeviceAssignmentRecord.device_id)
            if organization_id is not None:
                assigned_query = assigned_query.filter(DeviceAssignmentRecord.organization_id == organization_id)
            assigned_device_ids = {device_id for (device_id,) in assigned_query.all()}
            query = session.query(PendingDeviceRecord)
            if organization_id is not None:
                query = query.filter(PendingDeviceRecord.organization_id == organization_id)
            records = query.order_by(PendingDeviceRecord.last_seen_at.desc(), PendingDeviceRecord.device_id.asc()).all()
            return [
                self._to_pending_device(record)
                for record in records
                if record.device_id not in assigned_device_ids
            ]

    def delete_device(self, device_id: str, organization_id: int | None = None) -> bool:
        with SessionLocal() as session:
            record = session.get(DeviceAssignmentRecord, device_id.strip())
            if not record:
                return False
            if organization_id is not None and record.organization_id != organization_id:
                return False
            session.delete(record)
            session.commit()
            return True

    def delete_devices_for_user(self, user_id: int, organization_id: int | None = None) -> None:
        with SessionLocal() as session:
            assignment_query = session.query(DeviceAssignmentRecord).filter(DeviceAssignmentRecord.user_id == user_id)
            pending_query = session.query(PendingDeviceRecord).filter(PendingDeviceRecord.user_id == user_id)
            if organization_id is not None:
                assignment_query = assignment_query.filter(DeviceAssignmentRecord.organization_id == organization_id)
                pending_query = pending_query.filter(PendingDeviceRecord.organization_id == organization_id)
            for record in assignment_query.all():
                session.delete(record)
            for record in pending_query.all():
                session.delete(record)
            session.commit()


_REGISTRY: Optional[DeviceRegistry] = None


def get_device_registry() -> DeviceRegistry:
    global _REGISTRY  # noqa: PLW0603
    if _REGISTRY is None:
        init_database()
        _REGISTRY = DeviceRegistry()
    return _REGISTRY
