from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable, Optional

from database import (
    DEFAULT_ORGANIZATION_DOK,
    DEFAULT_ORGANIZATION_NAME,
    DEFAULT_ORGANIZATION_SLUG,
    DEFAULT_PLATFORM_FEE_BASIS_POINTS,
    OrganizationRecord,
    SessionLocal,
    init_database,
)


@dataclass(frozen=True)
class Organization:
    id: int
    name: str
    dok: str
    slug: str
    active: bool
    stripe_connect_account_id: Optional[str]
    stripe_connect_onboarding_complete: bool
    stripe_location_id: Optional[str]
    platform_fee_basis_points: int
    address_line1: Optional[str]
    address_postal_code: Optional[str]
    address_city: Optional[str]
    address_country: str
    created_at: datetime
    updated_at: datetime


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def normalize_slug(value: str) -> str:
    slug = re.sub(r"[^a-z0-9-]+", "-", value.lower().strip())
    slug = re.sub(r"-+", "-", slug).strip("-")
    return slug or DEFAULT_ORGANIZATION_SLUG


class OrganizationStore:
    @staticmethod
    def _to_organization(record: OrganizationRecord) -> Organization:
        return Organization(
            id=record.id,
            name=record.name,
            dok=record.dok,
            slug=record.slug,
            active=record.active,
            stripe_connect_account_id=record.stripe_connect_account_id,
            stripe_connect_onboarding_complete=record.stripe_connect_onboarding_complete,
            stripe_location_id=record.stripe_location_id,
            platform_fee_basis_points=record.platform_fee_basis_points,
            address_line1=record.address_line1,
            address_postal_code=record.address_postal_code,
            address_city=record.address_city,
            address_country=record.address_country or "DE",
            created_at=record.created_at,
            updated_at=record.updated_at,
        )

    def list_organizations(self, include_inactive: bool = True) -> Iterable[Organization]:
        with SessionLocal() as session:
            query = session.query(OrganizationRecord)
            if not include_inactive:
                query = query.filter(OrganizationRecord.active.is_(True))
            records = query.order_by(OrganizationRecord.dok.asc(), OrganizationRecord.name.asc()).all()
            return [self._to_organization(record) for record in records]

    def get_by_id(self, organization_id: int | None) -> Optional[Organization]:
        if organization_id is None:
            return None
        with SessionLocal() as session:
            record = session.get(OrganizationRecord, organization_id)
            return self._to_organization(record) if record else None

    def get_by_slug(self, slug: str | None) -> Optional[Organization]:
        if not isinstance(slug, str) or not slug.strip():
            return None
        with SessionLocal() as session:
            record = session.query(OrganizationRecord).filter(OrganizationRecord.slug == slug.strip()).first()
            return self._to_organization(record) if record else None

    def create_organization(
        self,
        name: str,
        dok: str,
        slug: str | None = None,
        active: bool = True,
        platform_fee_basis_points: int = DEFAULT_PLATFORM_FEE_BASIS_POINTS,
        address_line1: str | None = None,
        address_postal_code: str | None = None,
        address_city: str | None = None,
        address_country: str = "DE",
    ) -> Organization:
        now = _utcnow()
        normalized_slug = normalize_slug(slug or dok or name)
        with SessionLocal() as session:
            record = OrganizationRecord(
                name=name.strip(),
                dok=dok.strip().upper(),
                slug=normalized_slug,
                active=active,
                stripe_connect_onboarding_complete=False,
                platform_fee_basis_points=platform_fee_basis_points,
                address_line1=address_line1.strip() if isinstance(address_line1, str) and address_line1.strip() else None,
                address_postal_code=address_postal_code.strip()
                if isinstance(address_postal_code, str) and address_postal_code.strip()
                else None,
                address_city=address_city.strip() if isinstance(address_city, str) and address_city.strip() else None,
                address_country=(address_country or "DE").strip().upper()[:2],
                created_at=now,
                updated_at=now,
            )
            session.add(record)
            session.commit()
            session.refresh(record)
            return self._to_organization(record)

    def update_organization(
        self,
        organization_id: int,
        name: str | None = None,
        dok: str | None = None,
        slug: str | None = None,
        active: bool | None = None,
        stripe_connect_account_id: str | None = None,
        stripe_connect_onboarding_complete: bool | None = None,
        stripe_location_id: str | None = None,
        platform_fee_basis_points: int | None = None,
        address_line1: str | None = None,
        address_postal_code: str | None = None,
        address_city: str | None = None,
        address_country: str | None = None,
    ) -> Optional[Organization]:
        with SessionLocal() as session:
            record = session.get(OrganizationRecord, organization_id)
            if not record:
                return None
            if name is not None:
                record.name = name.strip()
            if dok is not None:
                record.dok = dok.strip().upper()
            if slug is not None:
                record.slug = normalize_slug(slug)
            if active is not None:
                record.active = active
            if stripe_connect_account_id is not None:
                record.stripe_connect_account_id = stripe_connect_account_id.strip() or None
            if stripe_connect_onboarding_complete is not None:
                record.stripe_connect_onboarding_complete = stripe_connect_onboarding_complete
            if stripe_location_id is not None:
                record.stripe_location_id = stripe_location_id.strip() or None
            if platform_fee_basis_points is not None:
                record.platform_fee_basis_points = platform_fee_basis_points
            if address_line1 is not None:
                record.address_line1 = address_line1.strip() or None
            if address_postal_code is not None:
                record.address_postal_code = address_postal_code.strip() or None
            if address_city is not None:
                record.address_city = address_city.strip() or None
            if address_country is not None:
                record.address_country = (address_country.strip().upper() or "DE")[:2]
            record.updated_at = _utcnow()
            session.commit()
            session.refresh(record)
            return self._to_organization(record)

    def set_active(self, organization_id: int, active: bool) -> Optional[Organization]:
        return self.update_organization(organization_id=organization_id, active=active)

    def set_stripe_account(
        self,
        organization_id: int,
        account_id: str,
        onboarding_complete: bool | None = None,
    ) -> Optional[Organization]:
        return self.update_organization(
            organization_id=organization_id,
            stripe_connect_account_id=account_id,
            stripe_connect_onboarding_complete=onboarding_complete,
        )

    def set_terminal_location(self, organization_id: int, location_id: str) -> Optional[Organization]:
        return self.update_organization(organization_id=organization_id, stripe_location_id=location_id)

    def ensure_default_organization(self) -> Organization:
        existing = self.get_by_slug(DEFAULT_ORGANIZATION_SLUG)
        if existing:
            return existing
        return self.create_organization(
            name=DEFAULT_ORGANIZATION_NAME,
            dok=DEFAULT_ORGANIZATION_DOK,
            slug=DEFAULT_ORGANIZATION_SLUG,
            platform_fee_basis_points=DEFAULT_PLATFORM_FEE_BASIS_POINTS,
        )


_STORE: Optional[OrganizationStore] = None


def get_organization_store() -> OrganizationStore:
    global _STORE  # noqa: PLW0603
    if _STORE is None:
        init_database()
        _STORE = OrganizationStore()
        _STORE.ensure_default_organization()
    return _STORE

