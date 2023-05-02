import weakref
from xurls.url import (
    URLStr, Query
)
from xinject import Dependency, XContext
from xmodel.common.types import FieldNames
from xsentinels.default import Default
from .weak_cache_pool import WeakCachePool
from .model import RemoteModel

# It's very common for other parts of the SDK to do `from .types import *`, to get all of the basic
# types.  I put more stuff from typing that is not strictly needed here; that way those modules
# will get these basic types just as easily.
from typing import (
    TypeVar, Dict, Any, Optional, Iterable, Generic, Sequence, TYPE_CHECKING
)

if TYPE_CHECKING:
    # Prevents circular imports, only needed for IDE type completion
    # (and static analyzers, if we end up using them in the future).
    from xmodel.remote.api import RemoteApi

M = TypeVar('M', bound=RemoteModel)
""" Generic TypeVar/placeholder for `xmodel.remote.model.RemoteModel`. """


class _ClientCacheDependency(Dependency):
    def __init__(self):
        self.clear_caches()

    def clear_caches(self):
        self.obj_cache = {}
        self.obj_weak_cache = weakref.WeakValueDictionary()

    obj_cache: Dict[str, Any] = None
    obj_weak_cache: weakref.WeakValueDictionary = None


class RemoteClient(Generic[M]):
    api: "RemoteApi[M]"

    """ Abstract type from which any client class is descended from.

            Most of the time, you'll want to use `xmodel.rest.RestClient` directly or as a
            subclass.

            It's rare that you'll need to inherit from this (ie: think something like
            `xmodel.dynamo.DynClient`, where your client is radically different on the inside
            but you want to look like a normal client class on the outside)
        """

    # -------------------------------
    # --------- Init Method ---------

    # noinspection PyMissingConstructor
    def __init__(self, api: "RemoteApi[M]"):
        """
        Args:
            api: The `xmodel.remote.api.RemoteApi` object that is creating this object.
        """
        super().__init__()
        self._api = api

    @property
    def api(self) -> "RemoteApi[M]":
        """
        Every RemoteModel has a class-based RemoteApi And RestClient instance, this will point to
        the class based RemoteApi instance, the same one you would get via
        `xmodel.remote.model.RemoteModel.api`.

        When `xmodel.remote.api.RemoteApi` creates us
        (it looks at type-hint on `xmodel.remote.api.RemoteApi.client`)
        it passes it's self to us here.

        Only ONE `RestClient` class is allocated per-`xmodel.remote.model.RemoteModel`
        class/type.
        The object instances of the RemoteModel all get a separate
        instance of `xmodel.remote.api.RemoteApi`; but all instances of that model type share
        the same `RemoteClient` instance via `xmodel.remote.api.RemoteApi.client`.

        The typehint on this var is only here to support the IDE, it allows the IDE to know what
        `xmodel.remote.model.RemoteModel` type this client is going to be using.
        IDE knows based on how you get the RestClient, when code uses the
        `xmodel.remote.model.RemoteModel.api` attribute; the IDE knows the concrete generic `M`
        type
        represents the real `xmodel.remote.model.RemoteModel` subclass type
        (for type completion).

        """
        return self._api

    # ----------------------------------------------------------
    # --------- Place To Put Cached Objects [from API] ---------
    # ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

    _obj_cache: Dict[str, Any] = None
    _obj_weak_cache: weakref.WeakValueDictionary = None

    def clear_caches(self) -> Any:
        """ Clears both the weak and strong caches.

            See `RemoteClient.cache_weak_get` for more details.
        """
        # Guaranteed we will only ever have one of these at a time, so no need to lookup chain.
        _ClientCacheDependency.grab().clear_caches()

        # Ensure every current cacher is cleared, down to the root-cacher.
        for obj in XContext.grab().dependency_chain(WeakCachePool):
            obj.clear_caches()

    def cache_weak_set(self, key, value):
        """ Just like `RemoteClient.cache_set, except it will weakly keep the value.

            See `RemoteClient.cache_weak_get` for more details.
        """
        WeakCachePool.grab().set(key, value)

    def cache_weak_get(self, key, default=None):
        """ See `RemoteClient.cache_set` documentation above for more details.
            This gets something out of the weak cache.
            If key does not exist in cache, then return default [which defaults to None].

            The purpose of this is to provide a way to cache something a
            `xmodel.remote.model.RemoteModel` so that when
            all other references to it are gone it will automatically be removed out of the cache
            (ie: when `xmodel.remote.model.RemoteModel` object is not used anymore).

            A good way to get a key-by-id is via
            `xmodel.remote.structure.RemoteStructure.id_cache_key`.
        """
        return WeakCachePool.grab().get(self.api.model_type, key, default)

    def cache_weak_remove(self, key):
        WeakCachePool.grab().remove(self.api.model_type, key)

    def cache_set(self, key, value):
        """ Right now this is a dictionary that you can set/retrieve keys from.
            It strongly caches the objects (ie: if they are unreferenced elsewhere, we still
            still keep them in the cache).

            See `RemoteClient.cache_weak_get` for more details.

            A good way to get a key-by-id is via
            `xmodel.remote.structure.RemoteStructure.id_cache_key`.
         """
        _ClientCacheDependency.grab().obj_cache[key] = value

    def cache_get(self, key, default=None):
        """ See cache_set documentation above for more details.
            This gets something out of cache.
            If key does not exist in cache, then return default [which defaults to None].

            See `RemoteClient.cache_weak_get` for more details.
        """
        weak_obj = self.cache_weak_get(key, default)
        if weak_obj:
            return weak_obj
        return _ClientCacheDependency.grab().obj_cache.get(key, default)

    def cache_remove(self, key):
        """ See cache_set documentation above for more details.
            This gets removes something out of the cache if it exists, or does nothing otherwise.

            See `RemoteClient.cache_weak_get` for more details.
        """
        _ClientCacheDependency.grab().obj_cache.pop(key, None)

    # ------------------------------------------------
    # --------- Send Requests to API Methods ---------

    def delete_obj(self, obj: M):
        raise NotImplementedError(f"Implement `delete_obj()` on ({type(self)}).")

    def delete_objs(self, objs: Sequence[M]):
        raise NotImplementedError(f"Implement `delete_objs()` on ({type(self)}).")

    def send_objs(
            self, objs: Sequence[M], *, url: URLStr = None, send_limit: int = None
    ):
        raise NotImplementedError(f"Implement `send_objs()` on ({type(self)}).")

    # ---------------------------------------
    # --------- GET via API Methods ---------

    def get(
            self,
            query: Query = None,
            *,
            top: int = None,
            fields: FieldNames = Default
    ) -> Iterable[M]:
        raise NotImplementedError(f"Implement `get()` on ({type(self)}).")

    def get_first(
        self, query: Query = None, *, fields: FieldNames = Default
    ) -> Optional[M]:
        result = self.get(query, top=1, fields=fields)
        if not result:
            return None

        return next(iter(result), None)
