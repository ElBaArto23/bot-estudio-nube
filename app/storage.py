"""Persistencia del avance en Azure Table Storage (y una versión en memoria).

Una sola tabla: PartitionKey = id de usuario; RowKey "perfil" para el avance
global y "q-<id>" para cada pregunta.
"""
from __future__ import annotations

import os
from datetime import date
from typing import Any

from study import Profile, Progress

TABLE_NAME = "estudio"
PROFILE_ROW = "perfil"
QUESTION_PREFIX = "q-"


def _to_text(value: date | None) -> str:
    return value.isoformat() if value else ""


def _from_text(value: str | None) -> date | None:
    return date.fromisoformat(value) if value else None


def profile_to_entity(user_id: int, profile: Profile) -> dict[str, Any]:
    return {
        "PartitionKey": str(user_id),
        "RowKey": PROFILE_ROW,
        "streak": profile.streak,
        "best_streak": profile.best_streak,
        "last_day": _to_text(profile.last_day),
        "total_ok": profile.total_ok,
        "total_bad": profile.total_bad,
    }


def profile_from_entity(entity: dict[str, Any]) -> Profile:
    return Profile(
        streak=int(entity.get("streak", 0)),
        best_streak=int(entity.get("best_streak", 0)),
        last_day=_from_text(entity.get("last_day")),
        total_ok=int(entity.get("total_ok", 0)),
        total_bad=int(entity.get("total_bad", 0)),
    )


def progress_to_entity(user_id: int, question_id: str, progress: Progress) -> dict[str, Any]:
    return {
        "PartitionKey": str(user_id),
        "RowKey": f"{QUESTION_PREFIX}{question_id}",
        "box": progress.box,
        "last_seen": _to_text(progress.last_seen),
        "ok": progress.ok,
        "bad": progress.bad,
    }


def progress_from_entity(entity: dict[str, Any]) -> Progress:
    return Progress(
        box=int(entity.get("box", 0)),
        last_seen=_from_text(entity.get("last_seen")),
        ok=int(entity.get("ok", 0)),
        bad=int(entity.get("bad", 0)),
    )


class MemoryStore:
    """Misma interfaz que TableStore, para pruebas y ejecuciones sin Azure."""

    def __init__(self) -> None:
        self._profiles: dict[int, Profile] = {}
        self._progress: dict[int, dict[str, Progress]] = {}

    def get_profile(self, user_id: int) -> Profile:
        return self._profiles.get(user_id, Profile())

    def save_profile(self, user_id: int, profile: Profile) -> None:
        self._profiles[user_id] = profile

    def get_progress(self, user_id: int) -> dict[str, Progress]:
        return dict(self._progress.get(user_id, {}))

    def save_progress(self, user_id: int, question_id: str, progress: Progress) -> None:
        self._progress.setdefault(user_id, {})[question_id] = progress


class TableStore:
    def __init__(self, table_client: Any) -> None:
        self._table = table_client

    def get_profile(self, user_id: int) -> Profile:
        from azure.core.exceptions import ResourceNotFoundError

        try:
            entity = self._table.get_entity(partition_key=str(user_id), row_key=PROFILE_ROW)
        except ResourceNotFoundError:
            return Profile()
        return profile_from_entity(entity)

    def save_profile(self, user_id: int, profile: Profile) -> None:
        self._table.upsert_entity(profile_to_entity(user_id, profile))

    def get_progress(self, user_id: int) -> dict[str, Progress]:
        rows = self._table.query_entities(
            "PartitionKey eq @pk", parameters={"pk": str(user_id)}
        )
        return {
            row["RowKey"][len(QUESTION_PREFIX):]: progress_from_entity(row)
            for row in rows
            if row["RowKey"].startswith(QUESTION_PREFIX)
        }

    def save_progress(self, user_id: int, question_id: str, progress: Progress) -> None:
        self._table.upsert_entity(progress_to_entity(user_id, question_id, progress))


def make_store() -> TableStore:
    """En Azure usa la identidad administrada; en local, la cadena de Azurite."""
    from azure.data.tables import TableServiceClient

    endpoint = os.environ.get("TABLES_ENDPOINT")
    if endpoint:
        from azure.identity import DefaultAzureCredential

        service = TableServiceClient(endpoint=endpoint, credential=DefaultAzureCredential())
        # La tabla la crea Terraform; la identidad solo tiene permisos sobre datos.
        return TableStore(service.get_table_client(TABLE_NAME))

    service = TableServiceClient.from_connection_string(os.environ["AzureWebJobsStorage"])
    return TableStore(service.create_table_if_not_exists(TABLE_NAME))
