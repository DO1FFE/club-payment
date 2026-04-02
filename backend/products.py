from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, Optional


@dataclass
class Product:
    id: int
    name: str
    price_cents: int
    active: bool


class ProductStore:
    def __init__(self) -> None:
        self._products: Dict[int, Product] = {}
        self._next_id = 1

    def list_products(self) -> Iterable[Product]:
        return list(self._products.values())

    def create_product(self, name: str, price_cents: int, active: bool = True) -> Product:
        product = Product(id=self._next_id, name=name, price_cents=price_cents, active=active)
        self._products[self._next_id] = product
        self._next_id += 1
        return product

    def update_product(
        self,
        product_id: int,
        name: Optional[str] = None,
        price_cents: Optional[int] = None,
        active: Optional[bool] = None,
    ) -> Optional[Product]:
        product = self._products.get(product_id)
        if not product:
            return None
        if name is not None:
            product.name = name
        if price_cents is not None:
            product.price_cents = price_cents
        if active is not None:
            product.active = active
        return product


_STORE: Optional[ProductStore] = None


def get_product_store() -> ProductStore:
    global _STORE  # noqa: PLW0603
    if _STORE is None:
        _STORE = ProductStore()
        _STORE.create_product(name="Cola/Bier", price_cents=150, active=True)
        _STORE.create_product(name="Wasser", price_cents=50, active=True)
    return _STORE
