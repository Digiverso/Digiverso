"""Caché en memoria del promedio por producto (HU-18)."""

from __future__ import annotations

from threading import RLock

from app.domain.reviews import Rating


class InMemoryRatingCache:
    """Guarda agregaciones ya calculadas y permite invalidarlas al publicar."""

    def __init__(self) -> None:
        self._ratings: dict[str, Rating] = {}
        self._lock = RLock()

    def get(self, product_id: str) -> Rating | None:
        with self._lock:
            return self._ratings.get(product_id)

    def set(self, product_id: str, rating: Rating) -> None:
        with self._lock:
            self._ratings[product_id] = rating

    def invalidate(self, product_id: str) -> None:
        with self._lock:
            self._ratings.pop(product_id, None)

    def clear(self) -> None:
        with self._lock:
            self._ratings.clear()
