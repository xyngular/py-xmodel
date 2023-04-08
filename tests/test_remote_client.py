from typing import Iterable, TypeVar

from xsentinels import Default
from xurls.url import Query

from xmodel import JsonModel
from xmodel.common.types import FieldNames
from xmodel.remote import RemoteClient, RemoteModel, RemoteApi

M = TypeVar("M", bound=RemoteModel)


class TClient(RemoteClient):
    last_get_query = None

    def get(
        self,
        query: Query = None,
        *,
        top: int = None,
        fields: FieldNames = Default
    ) -> Iterable[M]:
        self.last_get_query = query
        return [self.api.model_type(query)]


class TApi(RemoteApi[M]):
    client: TClient


class RChild(RemoteModel['JModel']):
    # Use out TApi type for this object, which in turn will use our custom TClient
    api: TApi['RChild']

    id: int


class JParent(JsonModel['JParent']):
    embedded: RChild


def test_related_remote_lookup_attempted():
    # Ensure related model field id is of correct type.
    jp = JParent({'embedded_id': 20})

    # See if BaseModel correctly resolves the lazy lookup of it's `embedded` attribute,
    # that refers to a `RChild` type.
    assert jp.embedded.id == 20
    assert RChild.api.client.last_get_query == {'id': 20}


# todo: Test `RemoteApi.option_all_for_name` and `RemoteApi.option_for_name` someday.
