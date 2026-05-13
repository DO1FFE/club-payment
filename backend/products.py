from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Optional

from database import ProductRecord, SessionLocal, init_database
from organizations import get_organization_store


@dataclass
class Product:
    id: int
    organization_id: int
    name: str
    price_cents: int
    active: bool


class ProductStore:
    @staticmethod
    def _to_product(record: ProductRecord) -> Product:
        return Product(
            id=record.id,
            organization_id=record.organization_id,
            name=record.name,
            price_cents=record.price_cents,
            active=record.active,
        )

    def list_products(self, organization_id: int | None = None) -> Iterable[Product]:
        with SessionLocal() as session:
            query = session.query(ProductRecord)
            if organization_id is not None:
                query = query.filter(ProductRecord.organization_id == organization_id)
            records = query.order_by(ProductRecord.id.asc()).all()
            return [self._to_product(record) for record in records]

    def create_product(
        self,
        name: str,
        price_cents: int,
        active: bool = True,
        organization_id: int | None = None,
    ) -> Product:
        organization_id = organization_id or get_organization_store().ensure_default_organization().id
        with SessionLocal() as session:
            record = ProductRecord(
                organization_id=organization_id,
                name=name,
                price_cents=price_cents,
                active=active,
            )
            session.add(record)
            session.commit()
            session.refresh(record)
            return self._to_product(record)

    def update_product(
        self,
        product_id: int,
        name: Optional[str] = None,
        price_cents: Optional[int] = None,
        active: Optional[bool] = None,
        organization_id: int | None = None,
    ) -> Optional[Product]:
        with SessionLocal() as session:
            record = session.get(ProductRecord, product_id)
            if not record:
                return None
            if organization_id is not None and record.organization_id != organization_id:
                return None
            if name is not None:
                record.name = name
            if price_cents is not None:
                record.price_cents = price_cents
            if active is not None:
                record.active = active
            session.commit()
            session.refresh(record)
            return self._to_product(record)

    def delete_product(self, product_id: int, organization_id: int | None = None) -> bool:
        with SessionLocal() as session:
            record = session.get(ProductRecord, product_id)
            if not record:
                return False
            if organization_id is not None and record.organization_id != organization_id:
                return False
            session.delete(record)
            session.commit()
            return True

    def has_products(self, organization_id: int | None = None) -> bool:
        with SessionLocal() as session:
            query = session.query(ProductRecord.id)
            if organization_id is not None:
                query = query.filter(ProductRecord.organization_id == organization_id)
            record = query.first()
            return record is not None


_STORE: Optional[ProductStore] = None


def get_product_store() -> ProductStore:
    global _STORE  # noqa: PLW0603
    if _STORE is None:
        init_database()
        _STORE = ProductStore()
        default_organization = get_organization_store().ensure_default_organization()
        if not _STORE.has_products(default_organization.id):
            _STORE.create_product(
                name="Cola/Bier",
                price_cents=150,
                active=True,
                organization_id=default_organization.id,
            )
            _STORE.create_product(
                name="Wasser",
                price_cents=50,
                active=True,
                organization_id=default_organization.id,
            )
    return _STORE
