import dataclasses
from logging import getLogger
from typing import (
    TypeVar, Type, get_type_hints, Union, List, Dict, Iterable, Set, Optional, Generic, Mapping,
    Any
)

import typing_inspect

from xinject import Dependency
from xsentinels import Default
from xurls.url import Query
from xmodel.util import loop

from xmodel.errors import XModelError
from xmodel.base.api import BaseApi
from xmodel.remote.model import RemoteModel
from xmodel.common.types import FieldNames, JsonDict
from xmodel.remote.client import RemoteClient
from xmodel.remote.response_state import ResponseState
from .options import ApiOptions, ApiOptionsGroup
from .structure import RemoteStructure
from xmodel import Field

log = getLogger(__name__)
M = TypeVar("M", bound=RemoteModel)


class RemoteApi(BaseApi[M]):

    # The type-hints inform this class what type of objects to create
    # when `client` and `structure` are needed/asked-for.
    #
    # You can override the type by making your own type-hint on a sub-class.
    # See xmodel.base.api.BaseApi's for its various special type-hinted attributes
    # for more details, it has more detailed comments/documentation on it.
    client: RemoteClient[M]
    structure: RemoteStructure[Field]

    # This type-hint is only for IDE, `RemoteApi` does not use it
    # (self.model_type value is passed in when RemoteApi is allocated, in __init__ method).
    model: M

    @property
    def _client(self):
        """ Returns an appropriate concrete `xmodel.remote.client.RemoteClient` subclass.
            We figure out the proper client object to use based on the type-hint for "client"
            property on the sub-class.

            Example:

                >>> from typing import TypeVar
                >>> from xmodel import RestApi, RestClient
                >>> M = TypeVar("M")  # <-- This allows IDE to do better code completion.
                >>>
                >>> class MyClient(RestClient[M]):
                >>>     pass
                >>>
                >>> class MyApi(RestApi[M])
                >>>     client: MyClient[M]  # <-- Type hint on 'client' property.

            This is enough for `xmodel.base.BaseModel` subclasses that have this set as their
            api type-hint:

                >>> from xmodel.remote.model import RemoteModel
                >>>
                >>> class MyModel(RemoteModel):
                >>>     api: MyApi

            When you get MyModel's api like below, it will return a MyApi instance,
            MyApi will in turn return a MyClient:

                >>> print(MyModel.api)
                MyApi(...)
                >>> print(MyModel.api.client)
                MyClient(...)

            For a more concreate use/example, see `xmodel_rest.RestModel`;
            it's a RemoteModel subclass that implments a RestClient that can be used with it.
        """
        client = self.structure.internal_shared_api_values.get('client')
        if client:
            return client

        client_type = get_type_hints(type(self)).get('client', None)
        if client_type is None:
            raise XModelError(
                f"RemoteClient subclass type is undefined for model class ({self.model_type}), "
                f"a type-hint for 'client' on BaseApi class must be in place for me to know what "
                f"type to get."
            )

        client = client_type(api=self.model_type.api)
        self.structure.internal_shared_api_values['client'] = client
        return client

    # PyCharm has some sort of issue, if I provide property type-hint and then a property function
    # that implements it. For some reason, this makes it ignore the type-hint in subclasses
    # but NOT in the current class.  It's some sort of bug. This gets around it since pycharm
    # can't figure out what's going on here.
    client = _client

    _auth_type = None
    """ See `RelationApi.auth`.
    """

    _client = None
    """ See `RemoteApi.client`.
    """

    # ------------------------------
    # --------- Properties ---------

    @property
    def response_state(self) -> ResponseState[M]:
        """
        Returns the HTTP/Communication state of the api object.

        This will include if the last time it was sent [patch/post/whatever], if it had an error.
        It also lets you mark the object as needing to be retried.
        You can also discover if an attempt to send it was even made, and so on.
        """
        response_state = self._response_state
        if not response_state:
            self._generate_state_if_needed()
            response_state = self._response_state
        return response_state

    # @property
    # def cache_by_id(self) -> bool:
    #     """ Look self.structure options, and current context options on self, to determine if
    #         we should cache by id for this particular api/model-class combo....
    #
    #         todo: I am thinking perhaps I just simple return the current ApiOptions, filled out
    #            by merging it with everything instead of having seperate methods like this...
    #     """
    #     # todo: Josh: Finish this, see doc-comment above; I am not 100% sure what I want
    #     #   to do with this right now,
    #     raise NotImplementedError()

    # ---------------------------
    # --------- Methods ---------

    # noinspection PyShadowingBuiltins
    def get_via_id(
            self,
            id: Union[
                Union[int, str],
                List[Union[int, str]],
                Dict[str, Union[str, int]],
                List[Dict[str, Union[str, int]]],
            ],
            fields: FieldNames = Default,
            id_field: str = None,
            aux_query: Query = None
    ) -> Union[Iterable[M], M, None]:
        """
        This method would have probably been better named `get_via_key`.

        The idea with this method is you pass in an value that can be queried against and
        id/key type of field that should always and ONLY identify zero or one objects.
        We will be using this fact to assume we can cache/map the id to a value we get so
        future requests will just return the existing object.

        If you give us a list for `id` then we will return a list/generator.
        Important: Right now we return a list in this case.
        But it might be just a generator in the future,
        treat the return type as a true Iterable, something you can't call 'len(...)' on.

        Get object via it's ID or a composite-key from API.
        If you pass in a list instead of an int/str for id, then this will return a list
        for all objects for objects found for passed in id's.
        We will automatically split up the requests in this case so they don't get too big and
        combine the results later and return a list (or a generator in the future).

        If you pass in a dictionary it will formulate the query to include all fields and values
        included in the dict.

        If you pass in a list of Dict's it will process all of the dictionaries and group
        them together where the keys in the dictionary match each other such as:
        [{key: 1}, {key:2}, {key:3, value:1}]
        would be grouped into queries:
        query 1 = {key: [1,2]}
        query 2 = {key: [3], value: [1]}
        and then process each query individually.

        .. attention:: If we ever have an API that can't accept multiple values for a key
            like we show in the above example; we would need to send each item in the list
            in individual requests.  Need to add support for that when we need it.

        This method is nice to use vs doing a generic query with the id/key, due to the fact
        we will look for cached object if the sub-class has the cache ny id enabled.
        This will also chunk queries so that no url will be too long for an api to handle.

        See `RelationApi.get` for a description of how 'fields` param works.

        Args:
            id: The identifier(s) of object to get.
            fields: See `RelationApi.get` for more info on how fields work.
                Summary: Try to only retrieve named fields (by default, we get all fields).
            id_field: If None, uses default 'id' field name, otherwise uses one provided.
            aux_query: If not None: Adds these to the query that is sent to API.

                Whatever is in this `aux_query` is added to each request for each of the
                identifiers provided in the 'id' parameter.

                Sometimes we can query for several identifiers per-request, sometimes not.
                Regardless of how we decide to breakup multiple 'id' values we will always
                add this `aux_query` to it.

                Used to provide additional filtering criteria in addition to the 'id'.

                You might want to get a set of objects by id, that also have (as an example)
                their 'first_name' attribute set to 'Josh', for example.
                Consider that we could pass thousands up ID's into a request,
                this could be a much faster way to get specific objects back then grabbing
                all of them and checking the `first_name` attribute yourself if you expect
                only a few of these objects to actually match.

                These won't be split up into segments [to keep URL/Request smaller] like the
                id/keys are.
                We are not able to use the id-cache if these are provided, we may always have
                to go to the API. This may change at some point in the future [by executing the
                query ourselves and not via the API against the cached objects]. But for now
                that's not the case.

            .. important:: aux_query is also only currently used if you pass in a `list`
                as the `id`. At some point we support non-id-list based aux_query.

            .. todo:: Consider using 'aux_query' against previously cached items.
        """

        # todo: Thinking of moving the  functionality of splitting the get into
        #  multiple requests based on
        #  an identifier field, allow it to be a general feature of the `RemoteClient` class,
        #  so it's more generally available. That way it's more of an automatic feature.

        if id is None:
            return None

        structure = self.structure

        max_query_by_id = structure.max_query_by_id

        # todo: Someday, adjust this to only iterate on id as needed, ie: get the first
        #  100 or so, and then query the client for that, and then get the next 100, etc.
        #  this allows us to make better use of id if it's a generator, especially if we
        #  return a real generator someday in the future [limits memory use that way].

        disable_all_caching = bool(aux_query)
        id_cache_is_enabled = self.option_for_name('cache_by_id')
        if disable_all_caching:
            id_cache_is_enabled = False

        if id_field and id_field != 'id':
            # For now, don't cache by an alternate id keys.
            id_cache_is_enabled = False
        else:
            id_field = "id"

        # ||| NEW START |||

        # `field` may be None, if the BaseModel has no id field.
        # Some models have a concept of an `id` that is not a field
        # in the table/api (ie: a 'virtual' id).
        field = self.structure.get_field(id_field)
        # If field not defined, default to str.
        field_type = field.type_hint if field else str

        # Only deal with str/int types for the field-type for id/key-types.
        # If it's something else, lets not support that for now.
        if field_type not in (int, str):
            raise XModelError(
                f"Field ({id_field}) for model type ({self.model_type}) needs to be a str or int "
                f"in order to currently be used in `get_via_id` method at the moment."
            )

        value_type = type(id)
        result_is_list = False

        if typing_inspect.is_union_type(field_type):
            raise XModelError(
                f"Field `{id_field}` for model type {self.model_type} can't be a union-type"
                f"({field_type}), it needs to be a specific type like `int`, `str`, etc."
            )

        result_is_list = value_type not in (int, str, dict)

        # ^^^ NEW END ^^^

        if not result_is_list and aux_query:
            raise NotImplementedError("Must use a List with aux_query for the moment.")

        client = self.client

        # todo: Josh Comment: I wish we just always returned a list/generator....
        #   consider making a separate method for most of the rest of the method
        #   and doing this in this one, followed by calling the new one [when returning list].
        key_dicts = []
        for key_values in loop(id):
            if isinstance(key_values, dict):
                key_dicts.append(key_values)
            else:
                key_dicts.append({id_field: key_values})

        if not result_is_list:
            if not disable_all_caching:
                obj = client.cache_weak_get(structure.id_cache_key({id_field: id}))
                if obj:
                    return obj

            if id_cache_is_enabled:
                # When this/these object(s) are updated via update_from_json the cache will be set
                # automatically if the sub-class has the cache_by_id ApiOption on it.
                obj = client.cache_get(structure.id_cache_key(id))
                if obj is not None:
                    return obj

            # todo: raise_on_404
            if key_dicts:
                return client.get_first(query=key_dicts[0], fields=fields)
            else:
                return None

        # We can assume at this point a list of ID's to get and a list of objects to return.
        # We only want to do about 100 at a time [due to URL length limits in production].

        results = []
        id_list = []
        objs_with_no_id_field = []
        objs_with_id_field = []

        # Check weak cache for objs and remove them by index
        indexes_to_remove_in_key_dicts = set()
        cached_results = set()
        for index, key_dict in enumerate(key_dicts):
            if disable_all_caching:
                # We are not doing any cache lookups for now, this may change in the future
                # as we make this more sophisticated.
                continue

            cached_obj = client.cache_weak_get(structure.id_cache_key(key_dict))
            if cached_obj:
                cached_results.add(cached_obj)
                indexes_to_remove_in_key_dicts.add(index)
            if len(key_dict.keys()) == 1:
                # We want to check if there is only one key in key dict and then check if that
                # key is "id"
                obj_id: Union[list, int, str] = key_dict.get("id")
                if obj_id and type(obj_id) is int:
                    cached_obj = client.cache_get(structure.id_cache_key(obj_id))
                    if cached_obj:
                        cached_results.add(cached_obj)
                        indexes_to_remove_in_key_dicts.add(index)
                elif obj_id and type(obj_id) is str:
                    #   I think we can assume people using our method will NOT pass in comma
                    #   separated values, if there is a comma they would want it to be part
                    #   of the ID [ie: they are passing us lists/dicts here, and we let the URL
                    #   formatter deal with how to encode that into the URL [ie: by comma, etc]...
                    #
                    # todo: Talk to Kaden, see why he put this in here originally.
                    #   Probably remove the comma splitting...

                    # If obj_id is a str then there is the possibility that there were multiple
                    # ids in that string separated by a comma
                    obj_id_set: Union[Set[str], str] = set(obj_id.split(","))
                    if len(obj_id) > 0:
                        for _id in obj_id_set:
                            _id = _id.strip()
                            cached_obj = client.cache_get(structure.id_cache_key(_id))
                            if cached_obj:
                                cached_results.add(cached_obj)
                                obj_id_set.remove(_id)
                        if len(obj_id_set) > 0:
                            obj_ids = ""
                            for _id in obj_id_set:
                                obj_ids += _id + ","
                            obj_ids = obj_ids[:-1]
                            key_dict["id"] = obj_ids
                        else:
                            indexes_to_remove_in_key_dicts.add(index)
                    else:
                        cached_obj = client.cache_get(structure.id_cache_key(obj_id))
                        if cached_obj:
                            cached_results.add(cached_obj)
                            indexes_to_remove_in_key_dicts.add(index)

        for index in sorted(indexes_to_remove_in_key_dicts, reverse=True):
            del key_dicts[index]

        # Add objects found in cache to results
        for cached_obj in cached_results:
            results.append(cached_obj)

        # Check the rest of the objects in key_dicts after removing the ones found in the cache
        for obj in key_dicts:
            if obj.get(id_field) is not None:
                objs_with_id_field.append(obj)
            else:
                objs_with_no_id_field.append(obj)

        if id_cache_is_enabled:
            # If caching enabled, go though each id and check for cached version.
            indexes_to_remove = []
            for index, obj_with_id in enumerate(objs_with_id_field):
                # More Info: See previous comment for ctx.cache_get, just above ^ [in this method].
                #
                # But to summarize:
                # When this/these object(s) are updated via update_from_json, the cache will be set
                # automatically if the sub-class has the cache_by_id ApiOption set to True.
                obj = client.cache_get(structure.id_cache_key(obj_with_id.get(id_field)))
                if obj is not None:
                    results.append(obj)
                    indexes_to_remove.append(index)
                    continue

            # Remove any objects that were found in cache.
            for index in sorted(indexes_to_remove, reverse=True):
                del objs_with_id_field[index]

        log.info(
            f"Getting ({len(objs_with_id_field) + len(objs_with_no_id_field)}) objects via "
            f"endpoint ({structure.endpoint_description}) from API."
        )

        # Combine keys-groups that use the same combination of keys, we can get
        # them in one query....
        query_groups = {}
        for obj in loop(objs_with_id_field, objs_with_no_id_field):
            obj_keys = frozenset(obj.keys())
            obj_group = query_groups.setdefault(obj_keys, [])
            obj_group.append(obj)

        results = []
        for key in query_groups:
            obj_group = query_groups[key]
            query = {}
            items_in_query_fields_count = 0
            while len(obj_group) > 0:
                obj = obj_group.pop()
                obj_keys = obj.keys()
                if items_in_query_fields_count + len(obj_keys) > max_query_by_id:
                    obj_group.append(obj)
                    items_in_query_fields_count = max_query_by_id + 1
                else:
                    for obj_key in obj_keys:
                        query_field_group = query.setdefault(obj_key, [])
                        query_field_group.append(obj.get(obj_key))
                        items_in_query_fields_count += 1

                if (
                    items_in_query_fields_count >= max_query_by_id or
                    len(obj_group) == 0
                ):
                    # Apply any extra query user provided.
                    if aux_query:
                        query.update(aux_query)

                    # Execute query and append results.
                    results.append(self.get(query, fields=fields))
                    query = {}
                    items_in_query_fields_count = 0

        return loop(*results)

    def get(
            self,
            query: Query = None,
            *,
            top: int = None,
            fields: Optional[FieldNames] = Default,
    ) -> Optional[Iterable[M]]:
        """
        Important: Right now we return a list, but it might be just a generator in the future,
        treat the return type as a true Iterable, something you can't call 'len(...)' on.

        Gets and instance of the proper subclass for the class you call this on for the passed in
        date_range, api_type, and account id for context.

        In the future, we may make what's returned a generator, so it would allow us
        to make page requests as whatever calls me iterates though the results.

        :param fields:
            You can pass in a list of fields, which will be the only ones returned in the objects.
            The field 'id' will always be included, no need to add that one your self.

            If Default or Empty List: [Default] Then all fields will be retrieved except
            the ones ignored by default.

            If None: Nothing about what fields to include/exclude will be passed to API. It should
            grab everything.

        :param query: Other custom queries to pass on.
        :param top: First number of objects to get, defaults to None, which means get everything.

        :return: A list of accounts.
        """
        return self.client.get(query, top=top, fields=fields)

    # ----------------------------------------------------
    # --------- Things REQUIRING an Associated BaseModel -----

    def json(
            self, only_include_changes: bool = False, log_output: bool = False
    ) -> Optional[JsonDict]:
        """
        `xmodel.base.api.BaseApi.json` to see superclass's documentation for this method.

        The changes for RemoteApi are to always include everything if we have no ID value for the
        associated model regardless of the value of only_include_changes.
        """

        model = self.model
        have_id_value = model.id is not None

        # Negate only include changes if we do not have an id value as it has not been created in
        # the remote.
        if only_include_changes and not have_id_value:
            only_include_changes = False

        json = super().json(only_include_changes, log_output)

        if have_id_value and json:
            # todo: Check to see if we have 'id' already?  Also, use the 'id' field's converter!
            #       for now just leaving it as-is (normally this is a basic int/str value anyway).
            json['id'] = model.id

        if only_include_changes and json:
            fields_to_pop = self.fields_to_pop_for_json(json, self.structure.fields, log_output)

            have_usable_id = self.structure.has_id_field()
            id_is_same = False
            for f in fields_to_pop:
                if have_usable_id and f == 'id':
                    id_is_same = True
                else:
                    del json[f]

            if have_usable_id and id_is_same is True:
                if len(json) == 1 and json.get('id') is not None:
                    return None

        return json

    def update_from_json(self, json: Union[JsonDict, Mapping]):
        """
        `xmodel.base.api.BaseApi.update_from_json` to see superclass's documentation
        for this method.

        The changes for RemoteApi are to cache by id. This will automatically create a weak cache
        but will only create a hard cache if the option of `cache_by_id` is set to True.
        """
        super().update_from_json(json)

        structure = self.structure
        model = self.model

        have_id_field = structure.has_id_field()

        if have_id_field:
            # ID is special, get it before anything else
            # [if there is a problem, object can print out it's primary key, useful for debugging]
            id_value = json.get('id')
            model.id = id_value

            if id_value:
                self.client.cache_weak_set(structure.id_cache_key(id_value), model)

            if self.option_for_name('cache_by_id'):
                if id_value is None and model.id:
                    self.client.cache_remove(structure.id_cache_key(model.id))
                elif id_value:
                    self.client.cache_set(structure.id_cache_key(id_value), model)

    def list_of_attrs_to_repr(self) -> List[str]:
        names = set(super().list_of_attrs_to_repr())

        if self.structure.has_id_field() and self.model.id is not None:
            names.add('id')

        return list(names)

    def did_send(self):
        """ self.client will call us here after someone attempts to send us (a specific model),
            you and use `RelationApi.model` to grab the model that it happened with.

            Keep in mind, that this will be called after any attempt to send the object,
            even if there were no changes to send.

            In the future, I may pass in a flag to this method that says if it was actually
            updated or not.

            Right now, this does nothing. It's here more for subclasses to easily know when
            they are sent.

            This works even if multiple objects were sent at once, the client should call
            this method on each model independently.
        """
        # Nothing to do by default.
        pass

    def send(self):
        """ REQUIRES associated model object [see self.model].

        Convenience method to send this single object to API, it simply calls
        `self.client.send_objs()` with a single object in the list [via self.model].

        If you want to send multiple objects, call self.client.send_objs().
        """
        self.client.send_objs([self.model])

    def delete(self):
        """ REQUIRES associated model object [see self.model].

        Convenience method to delete this single object in API.
        """
        model = self.model
        if model.id is None:
            raise XModelError(
                f"A deleted was requested for an object that had no id for ({model})."
            )

        self.client.delete_obj(model)

    @property
    def options(self) -> ApiOptions[M]:
        """
        A set of options you can modify for the current context. If a particular option
        inside the options object is not set, Options object may look at the parent context
        and grab that options value.

        Moving to using this name `options` instead of the more verbose `self.options_for_context`.
        """
        return ApiOptionsGroup.grab().get(api=self)

    def option_for_name(self, option_attribute_name) -> Any:
        """ Returns the first option returned from self.option_all_for_name for the
            `option_attribute_name` that is passed in; otherwise None.

            See `BaseApi.option_all_for_name` for more details.
        """
        values = self.option_all_for_name(option_attribute_name=option_attribute_name)
        return values[0] if values else None

    def option_all_for_name(self, option_attribute_name) -> List[Any]:
        """
        Gets a particular option attribute by name in a particular prioritized order.

        It first looks in self.options to see if anything was explicitly set and uses
        that first in returned list.

        Next, we will add the value that was passed to `options=` during BaseModel class
        construction.

        .. todo::  At some point in the near future I want to revamp these options and put them
            in some sort of public resource, a resource that's behaviors sort of like
            how `xcon.config.Config` or `xmodel.fields.Field` works... in that you
            can set various options/attributes and ones that are unset are 'inherited' from any
            parent Config / Field. This would make it simpler to use in a temporary fashion
            Perhaps do something like this when we get to splitting the orm into separate library.
        """

        values = []
        # This gets the the context, and all parent context's options in order.
        context_option_list = self.context.dependency_chain(ApiOptionsGroup)

        options_to_check = []
        structure = self.structure
        for option_group in context_option_list:
            # Only grather options that have been previously created.
            options = option_group.get(api=self, create_if_needed=False)
            if options:
                options_to_check.append(options)

        options_to_check.append(structure.api_options)

        # If the option has been explicitly set on object, it's the first one.
        #
        # todo: See todo above xmodel.utils.SetUnsetValues: I may use a special 'Default'
        #       sentinel value in the future instead of looking directly in `__dict__`.
        #       |||
        #       Update (2021-03-26): Yes, want to change this; Look at `Field` class for better
        #       example of how to inhert values from parents.
        for options in options_to_check:
            if option_attribute_name in options.__dict__:
                values.append(getattr(options, option_attribute_name, None))

        # todo: Add values from options in parent context(s) somehow.
        #       Comments in our doc-comment [above].

        # If we have no values at this point, get what the default value is [ie: the one set
        # on the class and not directly on object] and if it's not None, put that into list.
        if not values:
            default_value = getattr(self.options, option_attribute_name, None)
            if default_value is not None:
                values.append(default_value)

        return values

    # ----------------------------
    # --------- Private ----------

    _response_state: ResponseState = None
    """ Contains details on what happened during the last http request. """

    _client_type: Type[RemoteClient] = None

    def _generate_state_if_needed(self):
        if not self._response_state:
            self._response_state = ResponseState()

