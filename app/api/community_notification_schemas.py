"""Esquemas de la bandeja de comunidad (HU-20)."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.services.community_notifications import CommunityNotificationData


class CommunityNotificationItem(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str
    tipo: str
    emisor: str
    mensaje: str
    leida: bool
    fecha: datetime

    @classmethod
    def from_data(cls, data: CommunityNotificationData) -> CommunityNotificationItem:
        return cls(
            id=data.id,
            tipo=data.tipo,
            emisor=data.emisor,
            mensaje=data.mensaje,
            leida=data.leida,
            fecha=data.fecha,
        )


class CommunityNotificationListData(BaseModel):
    items: list[CommunityNotificationItem]
    pagina: int
    total: int
