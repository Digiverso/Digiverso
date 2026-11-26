"""Casos de uso FUN-17 a FUN-20 del submódulo SUB-08 (categorías)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Final

from app.cache.category_tree import CategoryTreeCache
from app.core.config import Settings
from app.domain.actor import Actor
from app.domain.audit import AuditEvent
from app.domain.category import (
    Category,
    build_path,
    is_self_or_descendant,
    normalize_name,
    validate_name,
    validate_order,
)
from app.domain.exceptions import (
    CategoryCycleError,
    CategoryHasActiveProductsError,
    CategoryNotFoundError,
    DuplicateCategoryNameError,
    ForbiddenError,
    InvalidCategoryError,
    InvalidParentError,
)
from app.repository.audit import SQLiteAuditRepository
from app.repository.categories import SQLiteCategoryRepository

_UNSET: Final = object()


class CategoryService:
    """Orquesta validación, persistencia, auditoría e invalidación de caché."""

    def __init__(
        self,
        repository: SQLiteCategoryRepository,
        audit_repository: SQLiteAuditRepository,
        cache: CategoryTreeCache,
        settings: Settings,
    ) -> None:
        self.repository = repository
        self.audit_repository = audit_repository
        self.cache = cache
        self.settings = settings

    # --------------------------------------------------------------- helpers
    def _ensure_admin(self, actor: Actor) -> None:
        if not actor.is_admin:
            raise ForbiddenError(
                "El actor no tiene permiso catalog.category.write para gestionar categorías.",
                details={"actorId": actor.id, "roles": list(actor.roles)},
            )

    def _validate_description(self, descripcion: str | None) -> str | None:
        if descripcion is None:
            return None
        cleaned = descripcion.strip() or None
        if cleaned and len(cleaned) > self.settings.category_description_max_length:
            raise InvalidCategoryError(
                "La descripción excede la longitud permitida.",
                details={
                    "longitud": len(cleaned),
                    "maximo": self.settings.category_description_max_length,
                },
            )
        return cleaned

    def _resolve_parent(self, padre_id: str | None) -> Category | None:
        if padre_id is None:
            return None
        parent = self.repository.get(padre_id)
        if parent is None:
            raise InvalidParentError(
                "La categoría padre no existe.", details={"padreId": padre_id}
            )
        if not parent.activa:
            raise InvalidParentError(
                "No se puede usar una categoría inactiva como padre.",
                details={"padreId": padre_id},
            )
        return parent

    def _assert_unique_name(
        self, nombre: str, parent_id: str | None, *, exclude_id: str | None = None
    ) -> None:
        if self.repository.exists_by_name(
            normalize_name(nombre),
            parent_id,
            exclude_id=exclude_id,
        ):
            raise DuplicateCategoryNameError(
                "Ya existe una categoría con ese nombre bajo el mismo padre.",
                details={"padreId": parent_id, "nombre": nombre},
            )

    def _record(
        self,
        *,
        category_id: str,
        action: str,
        actor: Actor,
        changes: dict[str, Any],
    ) -> None:
        self.audit_repository.record(
            AuditEvent(
                entidad="categoria",
                entidad_id=category_id,
                accion=action,
                actor_id=actor.id,
                actor_roles=actor.roles,
                fecha=datetime.now(timezone.utc),
                cambios=changes,
            )
        )

    @staticmethod
    def _snapshot(category: Category) -> dict[str, Any]:
        return {
            "id": category.id,
            "nombre": category.nombre,
            "descripcion": category.descripcion,
            "padreId": category.padre_id,
            "estado": category.estado,
            "orden": category.orden,
            "ruta": category.ruta,
        }

    # --------------------------------------------------------------- FUN-17
    def create(
        self,
        *,
        nombre: str,
        actor: Actor,
        padre_id: str | None = None,
        descripcion: str | None = None,
        orden: int = 0,
    ) -> Category:
        self._ensure_admin(actor)
        cleaned_name = validate_name(
            nombre,
            min_length=self.settings.category_name_min_length,
            max_length=self.settings.category_name_max_length,
        )
        cleaned_description = self._validate_description(descripcion)
        cleaned_order = validate_order(orden)
        parent = self._resolve_parent(padre_id)

        self._assert_unique_name(cleaned_name, padre_id)

        category_id = self.repository.next_id()
        category = Category(
            id=category_id,
            nombre=cleaned_name,
            padre_id=parent.id if parent else None,
            descripcion=cleaned_description,
            orden=cleaned_order,
            ruta=build_path(parent, category_id),
        )
        self.repository.save(category)
        self._record(
            category_id=category.id,
            action="crear",
            actor=actor,
            changes={"despues": self._snapshot(category)},
        )
        self.cache.invalidate()
        return category

    # --------------------------------------------------------------- FUN-18
    def update(
        self,
        category_id: str,
        *,
        actor: Actor,
        nombre: object = _UNSET,
        descripcion: object = _UNSET,
        padre_id: object = _UNSET,
        orden: object = _UNSET,
    ) -> Category:
        self._ensure_admin(actor)
        category = self.repository.get(category_id)
        if category is None:
            raise CategoryNotFoundError(
                "La categoría no existe.", details={"id": category_id}
            )

        before = self._snapshot(category)
        final_name = category.nombre
        final_description = category.descripcion
        final_order = category.orden
        final_parent_id = category.padre_id

        if nombre is not _UNSET:
            assert isinstance(nombre, str)
            final_name = validate_name(
                nombre,
                min_length=self.settings.category_name_min_length,
                max_length=self.settings.category_name_max_length,
            )
        if descripcion is not _UNSET:
            assert descripcion is None or isinstance(descripcion, str)
            final_description = self._validate_description(descripcion)
        if orden is not _UNSET:
            assert isinstance(orden, int)
            final_order = validate_order(orden)

        if padre_id is not _UNSET:
            assert padre_id is None or isinstance(padre_id, str)
            if padre_id == category_id:
                raise CategoryCycleError(
                    "Una categoría no puede ser su propio padre.",
                    details={"id": category_id, "padreId": padre_id},
                )
            parent = self._resolve_parent(padre_id)
            if parent is not None and is_self_or_descendant(parent, category):
                raise CategoryCycleError(
                    "No se puede mover una categoría debajo de su propio subárbol.",
                    details={"id": category_id, "padreId": padre_id},
                )
            final_parent_id = parent.id if parent else None

        self._assert_unique_name(final_name, final_parent_id, exclude_id=category_id)

        previous_path = category.ruta
        new_parent = self.repository.get(final_parent_id) if final_parent_id else None
        category.nombre = final_name
        category.descripcion = final_description
        category.orden = final_order
        category.padre_id = final_parent_id
        category.ruta = build_path(new_parent, category_id)

        self.repository.update(category, previous_path=previous_path)
        after = self._snapshot(category)
        changed_fields = [key for key in before if before[key] != after[key]]
        self._record(
            category_id=category_id,
            action="editar",
            actor=actor,
            changes={
                "campos": changed_fields,
                "antes": before,
                "despues": after,
            },
        )
        self.cache.invalidate()
        return category

    # --------------------------------------------------------------- FUN-19
    def deactivate(self, category_id: str, *, actor: Actor) -> Category:
        self._ensure_admin(actor)
        category = self.repository.get(category_id)
        if category is None:
            raise CategoryNotFoundError(
                "La categoría no existe.", details={"id": category_id}
            )
        if not category.activa:
            return category

        active_products = self.repository.count_active_products_in_subtree(category.ruta)
        if active_products:
            raise CategoryHasActiveProductsError(
                "La categoría tiene productos activos; reasígnalos antes de desactivarla.",
                details={
                    "productosActivos": active_products,
                    "accionRequerida": "Reasigna los productos a otra categoría activa.",
                },
            )

        before = self._snapshot(category)
        self.repository.deactivate(category)
        self._record(
            category_id=category_id,
            action="desactivar",
            actor=actor,
            changes={"antes": before, "despues": self._snapshot(category)},
        )
        self.cache.invalidate()
        return category

    # --------------------------------------------------------------- FUN-20
    def get_tree(self) -> list[dict[str, Any]]:
        cached = self.cache.get()
        if cached is not None:
            return cached

        categories = self.repository.list_active()
        nodes: dict[str, dict[str, Any]] = {}
        ordered = sorted(
            categories, key=lambda item: (item.orden, item.nombre_normalizado, item.id)
        )
        for category in ordered:
            nodes[category.id] = {
                "id": category.id,
                "nombre": category.nombre,
                "descripcion": category.descripcion,
                "padreId": category.padre_id,
                "estado": category.estado,
                "orden": category.orden,
                "hijos": [],
            }

        roots: list[dict[str, Any]] = []
        for category in ordered:
            node = nodes[category.id]
            parent_node = nodes.get(category.padre_id) if category.padre_id else None
            if parent_node is None:
                roots.append(node)
            else:
                parent_node["hijos"].append(node)

        tree = roots
        self.cache.set(tree)
        return tree
