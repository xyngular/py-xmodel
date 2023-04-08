"""
## Introduction

Used to weakly store model objects in a Dependency.
Dependency can be activated/enabled temporarily or permanently depending on desired behavior for
app.

The weak-cache is nice, because there are situations where various object will reference
the same object. Take for instance order and order-lines.  The order-lines would have a
one-to-one relationship back to the order object, and there is no need to lookup the same
order object over and over again if you ask each order-line for it's order-object.

This is where the weak-cache can shine. The ORM can store temporary references to objects
by 'id' and check this cache to retrieve them later instead of having to do an actual
fetch-request.

Another place this can be useful is when query objects that are in a tree.
And objects parent could be referenced by several children.

## Quick Start

To use, you can either simply allocate a `WeakCachePool` resource and activate it
via `@` function dectorator or `with` context-manager syntax:

>>> from xmodel.weak_cache_pool import WeakCachePool
>>> @WeakCachePool(enabled=True)
>>> def lambda_event_handler(event, context):
...    pass

While this WeakCachePool is enabled, it will store weakly-cached objects in it's self.
When the object is deactivated and thrown away after the `lambda_event_handler` is finished
the weak-cache is deallocated.

Next time the function `lambda_event_handler` is called, a brand-new WeakCachePool is allocated
and then activated.

If you wish to enable the `WeakCachePool` permently, you can enable the current
`WeakCachePool` instead of allocating and activating a new one:

>>> WeakCachePool.grab().enabled = True

When you allocate a new `WeakCachePool`, the previous one will not be used while the new one
is activated.  This means, any objects you fetch will not use the previous cache.
You are guaranteed to get brand-new fresh objects while the new `WeakCachePool` is active
vs what has been previously fetched (ie: parent should not be consulted).

"""

from xinject import Dependency
from typing import Type, Dict
import weakref


# Only reason we are using ThreadUsafeDependency is to be ultra-safe,
# for now don't share WeakCachePool cross-thread, associate pool with only one thread of now.
# We may relax this later. See class doc-comment below for more details.
class WeakCachePool(Dependency):
    """
    In general, used to enable the weak-cache for the ORM in general.

    By default, the weak cache is not enabled.

    It's an explicitly opt-in feature, because there may be reference-cycles for the Model
    object and so it may not be immediately deallocated.


    .. important:: For now, we are making this a ThreadUsafeDependency;
        we might relax this later... being ultra-safe.
        If some other thread is doing stuff with orm, weakly-cached objects are
        cached per-thread for now.
        It mostly likely is ok to share weak-cache across thread,
        for now I thought it prudent to not dive into that just yet.

    ## Python Memory Management Details

    Python has a referenced-counting system that can deallocate most objects immediately.
    However, reference-cycles can't be detected via the referenced-counting system.
    Objects in this situation are collected by the garbage collector process,  that goes though
    and detects reference-cycles that are not longer reachable by a strong-reference.
    """

    # Instead of inheriting from `ThreadUnsafeDependency`, we set flag directly ourselves.
    # This allows us to be compatible with both v2 and v3 of xinject.
    resource_thread_safe = False

    # If/when we get copied, we play it safe and don't copy `_obj_weak_cache` for now.
    # I might consider doing a shallow-copy of the weak cache (even if a deep-copy is requested)
    # at some point in the future. For now, keeping it conservative.
    attributes_to_skip_while_copying = {'_obj_weak_cache'}

    @property
    def enabled(self) -> bool:
        """ Enables the weak-cacher so when it's asked to weakly cache an object it will
            actually do it.

            If you enable us and we were previously disabled, the weak-cache will be cleared;
            and we also clear cache if we were previously enabled and get disabled.
        """
        return self._enabled

    @enabled.setter
    def enabled(self, value: bool):
        if self._enabled == value:
            return
        self._enabled = value
        self.clear_caches()

    _enabled = None
    _obj_weak_cache: Dict[Type, weakref.WeakValueDictionary] = None

    def __init__(self, enable=False):
        self.enabled = bool(enable)
        self.clear_caches()

    def clear_caches(self):

        self._obj_weak_cache = dict()

    def set(self, key: str, value):
        """
        Just like `xmodel.base.client.BaseClient.cache_set`,
        except it will weakly keep the value inside us as a Dependency subclass.

        Normally called from `xmodel.base.client.BaseClient.cache_weak_set`,
        we implement most of that methods functionality here.

        We also don't cache any values if `ModelCacher.enable_weak_cache` is `False`
        (the default).

        This means, while/if a `ModelCacher` `xinject.context.Dependency` is activated and
        enabled, when `xmodel.base.client.BaseClient` uses us to weakly cache something it will
        call us and we will weakly set them into into the cache.

        When we weakly cache something, we use the value's type + the key to identify it.
        You'll need the value's type + key to later retrieve the weakly cached value.

        See `xmodel.base.client.BaseClient.cache_weak_get` for more details.
        """
        if not self.enabled:
            return

        # Check to see if we have weak-dict for the value-type...
        value_type = type(value)
        if value_type not in self._obj_weak_cache:
            self._obj_weak_cache[value_type] = weakref.WeakValueDictionary()

        self._obj_weak_cache[value_type][key] = value

    def get(self, value_type: Type, key: str, default=None):
        """
        See `xmodel.base.client.BaseClient.cache_get` documentation for more details.
        This gets something out of the weak cache in self.

        Normally called from `xmodel.base.client.BaseClient.cache_get`,
        for weakly cached objects, we implement most of that methods functionality here.

        If key does not exist in cache, then return default [which defaults to None].

        The purpose of this is to provide a way to cache something a
        `xmodel.base.model.BaseModel` so that when
        all other references to it are gone it will automatically be removed out of the cache
        (ie: when `xmodel.base.model.BaseModel` object is not used anymore).

        A good way to get a key-by-id is via
        `xmodel.base.structure.BaseStructure.id_cache_key`.
        """
        if not self.enabled:
            return None

        type_weak_dict = self._obj_weak_cache.get(value_type, None)
        if type_weak_dict is None:
            return default

        return type_weak_dict.get(key, default)

    def remove(self, value_type: Type, key: str):
        # No need to check if not enabled (optimization).
        if not self.enabled:
            return

        type_weak_dict = self._obj_weak_cache.get(value_type, None)
        if type_weak_dict is None:
            return

        type_weak_dict.pop(key, None)

    # Whenever we are activated via a `with` or `@`,
    # clear the caches for now just to keep things simple.
    # Overriding __enter__ and __exit__ is the easiest way to do that.

    def __enter__(self) -> 'WeakCachePool':
        self.clear_caches()
        return super().__enter__()

    def __exit__(self, *args, **kwargs):
        self.clear_caches()
        return super().__exit__(*args, **kwargs)


def A():
    with WeakCachePool() as b:
        pass
