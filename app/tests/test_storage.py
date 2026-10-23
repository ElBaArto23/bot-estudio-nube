from datetime import date

from storage import (
    MemoryStore,
    TableStore,
    profile_from_entity,
    profile_to_entity,
    progress_from_entity,
    progress_to_entity,
)
from study import Profile, Progress

DAY = date(2026, 10, 23)


def test_profile_roundtrip():
    profile = Profile(streak=3, best_streak=5, last_day=DAY, total_ok=7, total_bad=2)
    entity = profile_to_entity(42, profile)
    assert entity["PartitionKey"] == "42" and entity["RowKey"] == "perfil"
    assert profile_from_entity(entity) == profile


def test_empty_profile_roundtrip_keeps_none_dates():
    assert profile_from_entity(profile_to_entity(1, Profile())) == Profile()


def test_progress_roundtrip():
    progress = Progress(box=3, last_seen=DAY, ok=4, bad=1)
    entity = progress_to_entity(42, "tf-estado", progress)
    assert entity["RowKey"] == "q-tf-estado"
    assert progress_from_entity(entity) == progress


def test_memory_store_isolates_users():
    store = MemoryStore()
    store.save_progress(1, "a", Progress(box=2))
    assert store.get_progress(2) == {}
    assert store.get_progress(1)["a"].box == 2
    assert store.get_profile(1) == Profile()


class FakeTable:
    """Imita lo mínimo de TableClient para probar TableStore sin Azure."""

    def __init__(self):
        self.rows = {}

    def upsert_entity(self, entity):
        self.rows[(entity["PartitionKey"], entity["RowKey"])] = dict(entity)

    def get_entity(self, partition_key, row_key):
        from azure.core.exceptions import ResourceNotFoundError

        try:
            return self.rows[(partition_key, row_key)]
        except KeyError:
            raise ResourceNotFoundError("no existe") from None

    def query_entities(self, query, parameters=None):
        assert "PartitionKey eq @pk" in query
        return [r for (pk, _), r in self.rows.items() if pk == parameters["pk"]]


def test_table_store_roundtrip_and_filtering():
    store = TableStore(FakeTable())
    assert store.get_profile(9) == Profile()  # no existe: perfil vacío, sin error
    store.save_profile(9, Profile(streak=2, last_day=DAY))
    store.save_progress(9, "a", Progress(box=1, last_seen=DAY, ok=1))
    store.save_progress(8, "b", Progress(box=5))
    assert store.get_profile(9).streak == 2
    progress = store.get_progress(9)
    assert list(progress) == ["a"]  # la fila "perfil" y los datos de otro usuario no se cuelan
    assert progress["a"].last_seen == DAY
