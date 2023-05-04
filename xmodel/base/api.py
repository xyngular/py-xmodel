"""
If you don't know much about the ORM, read [ORM Library Overview](./#orm-library-overview) first!

## API Class Overview
[api-class-overview]: #api-class-overview

This modules houses the `BaseApi` class, meant to bridge between the Client
(which executes requests) and the `xmodel.model.BaseModel` classes.

In order to reduce any name-collisions for other normal Model attributes, everything
related to the Api that the `xmodel.model.BaseModel` needs is gotten though via the
`BaseApi` class.

You can get the Api instance related to the model via `xmodel.model.BaseModel.api`.

>>> obj = BaseModel.api.get_via_id(1)

You can send a single object with any changes you make to the model attributes to API via:

>>> obj.api.send()

The `BaseApi` instance will be different based on how you access the api, either via the model
class or model instance.  That way the `BaseApi` instance you use will know the model it's
related too.  Also, the `BaseApi` can keep track of internal state. An example of this is
keeping track of the last error encounted for that model object (vs other model instances).

Some `BaseApi` methods require an associated model object
(examples: `BaseApi`.delete` and `BaseApi`.model`).
Calling methods that require a model using an Api object that does not have one will raise
an error.

This class is a sort of "Central Hub" that ties all intrested parties together.

### Use of type-hints for changing used type
[type-hints]: #type-hints

Based on the type-hint, `BaseApi` will create/use these types for the core classes that implment
most of the logic/settings.

- `BaseApi`.structure`: The structure of the Model/Api, which are the fields, url's and other
    options that control how it behaves with the Api service.
    This also determin the Field type to use via a Generic type-hint.

        >>> structure: MyStructure[M, MyField]

    In this case, `MyStructure` will be used and `MyStructure` will allocate
    `MyField` by default when creating field defintions from type-hints on Model attributes.

    `M` here informs the IDE of the Model type MyStructure will be used with when,
    this helps with type-completion.

    See `BaseApi`.structure` for more details.

- `BaseApi`.client`: This is code that does the work of sending requests and reciveing responses
    with the Api service for the Api/Model. The type-hint set here is allocated once-per
    `xmodel.model.BaseModel` class, which means once per-`xmodel.base.structure.Structure`
    instance.

- `BaseApi`.settings`: Basic environmental settings (ie: API token, base-url, etc)

- `BaseApi`.auth`: Manages getting any needed authorization and caching the tokens.
    The system will use the type-hint provided and treat it as a `xinject.resource.Dependency`.
    This allows the auth/token to be shared amoung various Model Api objects.

A sub-class of Api can (if desired) specify to use different client/config types by simply
declaring a type-annotation about it. Subclases inherit the type-hints from the super-class
like you would expect. The Api object when created will use the type-hints to allocate
the proper class. In this way, the type-hints act as a sort of 'template' and also inform
IDE's about what type the objects are.  Sort of a two-for-one deal!

Here is an example of how to customize/define/configure each part of the system:

>>>import xmodel.base.auth
>>>import xmodel
>>>
>>> # TODO: This example is WAY out of date, normalize with the modern `xsettings` lib.
>>> class MySettings(xmodel_test.base.settings.RestSettings):
...     my_custom_var: str = settings.ConfigVar("CUSTOM_ENV_VAR", "default")
>>>
>>> class MyAuth(auth.RelationAuth):
...     pass
>>>
>>> class MyClient(xmodel.BaseClient):
...     pass
>>>
>>> class MyField(xmodel.Field):
...     pass
>>>
>>> class MyStructure(xmodel.BaseStructure):
...     pass
>>>
>>> class MyApi(xmodel.BaseApi[M]):
...     # These type-hints will inform the system of what type to use for each
...     # part. You don't have to create them now, they will be created on
...     # demand as needed.
...     #
...     # Defining/Overriding one in a sub-class will make the system use that
...     # type. You only need to define/override the specific ones you want to
...     # change/use. Any unspecified ones will each inherit from the
...     # super-class as you would expect.
...     auth: MyAuth
...     client: MyClient
...     settings: MySettings
...     structure: MyStructure[Field]
>>>
>>> class MyModel(xmodel.BaseModel):
...     # Same as in MyApi, this will inherit from superclass if not specified.
...     api: MyApi


The settings is more about making it easy to get the relevant config most-used by that
particular Api subclass.  The client is what the Api will allocate to do requests.

To subclass any of these, you can subclass the conreate versions
(classes the `xmodel` module that are not in `xmodel.orm_types` module).
But if you don't do that you must at least inherit from the abstract versions in the
`xmodel.orm_types` module, such as `xmodel.base.auth.BaseAuth`
(and other classes named like `class *Type`).

.. warning:: I would HIGHLY recommend you inherit from the concrete versions, even if
    you don't fully need all the features the concrete class needs.  You can just ignore
    the parts you don't need.
"""
from xmodel.common.types import JsonDict
import typing_inspect
from typing import (
    TypeVar, Dict, List, Any, Optional, Type, Union, Generic, Set
)
from xmodel.base.fields import Field, Converter
from xmodel._private.api.state import PrivateApiState  # noqa - orm private module
from logging import getLogger
from xmodel.errors import XModelError
from xsentinels.null import Null, NullType
from typing import get_type_hints
from xinject.context import XContext
from collections.abc import Mapping
from xmodel.base.model import BaseModel
from xsentinels.default import Default
from xmodel.base.structure import BaseStructure
from xmodel.converters import DEFAULT_CONVERTERS

log = getLogger(__name__)

M = TypeVar("M", bound=BaseModel)


class BaseApi(Generic[M]):
    """
        This class is a sort of "Central Hub" that ties all intrested parties together.

        You can get the correct instance via `xmodel.base.model.BaseModel`.

        In order to reduce any name-collisions for other normal Model attributes, everything
        related to the BaseApi that the `xmodel.base.model.BaseModel` needs is gotten though via
        this class.

        You can get the BaseApi instance related to the model via
        `xmodel.base.model.BaseModel.api`.

        Example:

        >>> obj = BaseModel.api.get_via_id(1)

        For more information see [BaseApi Class Overview](#api-class-overview).
    """

    # Defaults Types to use. When you sub-class BaseApi, you can declare/override these type-hints
    # and specify a different type... The system will allocate and use that new type instead
    # for you automatically on any instances created of the class.
    #
    # The BaseAuth won't modify the request to add auth; so it's safe to use as the base default.
    #
    # These are implemented via `@property` methods further below, but these are the type-hints.
    #
    # The properties and the __init__ method all use these type-hints in order to use the correct
    # type for each one on-demand as needed. For details on each one, see the @property method(s).
    #
    # PyCharm has some sort of issue, if I provide property type-hint and then a property function
    # that implements it. For some reason, this makes it ignore the type-hint in subclasses
    # but NOT in the current class.  It's some sort of bug. I get around this bug by using a
    # different initial-name for the property by pre-pending a `_` to it,
    # and then setting it to the correct name later.
    #
    # Example: `structure = _structure` is done after `def _structure(...)` is defined.

    # See `_structure` method for docs and method that gets this value.
    structure: BaseStructure[Field]

    @property
    def _structure(self):
        """
        Contain things that don't vary among the model instances;
        ie: This is the same object and applies to all instances of a particular BaseModel class.

        This object has a list of `xmodel.fields.Field` that apply to the
        `xmodel.base.model.BaseModel` you can get via
        `xmodel.base.structure.Structure.fields`; for example.

        This is currently created in `BaseApi.__init__`.

        BaseApi instance for a BaseModel is only created when first asked for via
        `xmodel.base.model.BaseModel.api`.

        Returns:
            BaseStructure: Structure with correct field and model type in it.
        """
        return self._structure

    # PyCharm has some sort of issue, if I provide property type-hint and then a property function
    # that implements it. For some reason, this makes it ignore the type-hint in subclasses
    # but NOT in the current class.  It's some sort of bug. This gets around it since pycharm
    # can't figure out what's going on here.
    structure = _structure

    _structure = None
    """ See `BaseApi.structure`.
    """

    # ------------------------------
    # --------- Properties ---------

    default_converters: Dict[Type[Any], Converter] = None
    """
    For an overview of type-converts, see
    [Type Converters Overview](./#type-converters).

    The class attribute defaults to `None`, but an instance/object will always have
    some sort of dict in place (happens during init call).

    Notice the `todo` note in the [overview](./#type-converters). I want it to work that way in the
    future (so via `BaseApi.set_default_converter` and `BaseApi.get_default_converter`).
    It's something coming in the future. For now you'll need to override
    `default_converters` and/or change it directly.

    You can provide your own values for this directly in a sub-class,
    when an BaseApi or subclass is created, we will merge converters in this order,
    with things later in the order taking precedence and override it:

    1. `xmodel.converters.DEFAULT_CONVERTERS`
    2. `BaseApi.default_converters` from `xmodel.base.model.BaseModel.api` from parent model.
        The parent model is the one the model is directly inheriting from.
    3. Finally, `BaseApi.default_converters` from the BaseApi subclass's class attribute
       (only looks on type/class directly for `default_converters`).

    It takes this final mapping and sets it on `self.default_converters`,
    and will be inherited as explained on on line number `2` above in the future.

    Default converters we have defined at the moment:

    - `xmodel.converters.convert_json_date`
    - `xmodel.converters.convert_json_datetime`
    - And a set of basic converters via `xmodel.converters.ConvertBasicType`, supports:
        - float
        - bool
        - str
        - int

    See `xmodel.converters.DEFAULT_CONVERTERS` to see the default converters map/dict.

    Maps type-hint to a default converter.  This converter will be used for `TypeValue.convert`
    when the model BaseStructure is create if none is provided for it at field definition time
    for a particular type-hint. If a type-hint is not in this converter, no convert is
    called for it.

    You don't need to provide one of these for a `xmodel.base.model.BaseModel` type-hint,
    as the system knows to call json/update_from_json on those types of objects.

    The default value provides a way to convert to/from a dt.date/dt.datetime and a string.
    """

    # def set_default_converter(self, type, converter):
    #     """ NOT IMPLEMENTED YET -
    #     .. Todo:: Josh: These were here to look up a converter from a parent if a child does not
    #         have one  I have not figured out what I want to do here quite yet...
    #
    #         See todo at [Type Converters](./#type-converters) for an explanation of what this may
    #         be in the future.
    #
    #     """
    #     raise NotImplementedError()
    #
    # def get_default_converter(self, type) -> Optional[Converter]:
    #     """ NOT IMPLEMENTED YET -
    #     .. Todo:: Josh: These were here to look up a converter from a parent if a child does not
    #         have one  I have not figured out what I want to do here quite yet...
    #
    #         See todo at [Type Converters](./#type-converters) for an explanation of what this may
    #         be in the future.
    #     """
    #     raise NotImplementedError()

    # ------------------------------
    # --------- Properties ---------

    @property
    def model_type(self) -> Type[M]:
        """ The same BaseApi class is meant to be re-used for any number of Models,
            and so a BaseModel specifies it's BaseApi type as generic `BaseApi[M]`. In this case
            is the BaseModel it's self.  That way we can have the type-system aware that different
            instances of the same BaseApi class can specify different associated BaseModel classes.

            This property will return the BaseModel type/class associated with this BaseApi
            instance.
        """
        # noinspection PyTypeChecker
        return self.structure.model_cls

    # ---------------------------
    # --------- Methods ---------

    # noinspection PyMissingConstructor
    def __init__(self, *, api: "BaseApi[M]" = None, model: BaseModel = None):
        """

        .. warning:: You can probably skip the rest (below)
            Most of the time you don't create `BaseApi` objects your self, and so for most people
            you can skip the following unless you want to know more about internal details.

        # Init Method Specifics

        Normally you would not create an `BaseApi` object directly your self.
        `xmodel.base.model.BaseModel`'s know how to do this automatically.
        It happens in `xmodel.base.model.BaseModel.__init_subclass__`.

        Details about how the arguments you can pass are below.

        ## BaseModel Class Construction:

        If you provide an `api` arg without a `model` arg; we will copy the `BaseApi.structure`
        into new object, resetting the error status, and internal `BaseApi._state` to None.
        This `api` object is supposed to be the parent BaseModel's class api object.

        If both `api` arg + `model` arg are `None`, the BaseModel is the root/generic BaseModel
        (ie: it has no parent BaseModel).

        This is what is done by BaseModel classes while the class is lazily loading and
        creating/configuring the BaseModel class and it's associated `BaseApi` object
        (accessible via `xmodel.base.model.BaseModel.api`)

        ## BaseModel Instance Creation:

        If you also pass in a `model` arg; this get you a special copy of the api you passed in
        for use just with that BaseModel instance. The model `BaseApi._state` will be allocated
        internally in the init'd BaseApi object. This is how a `xmodel.base.model.BaseModel`
        instance get's it's own associated `BaseApi` object
        (that's a different instance vs the one set on BaseModel class when the BaseModel class
        was originally constructed).

        All params are optional.

        Args:
            api: The "parent" BaseApi obj to copy the basic structure from as a starting point,
                etc.
                The superclasses BaseApi class is passed via this arg.
                This is only used when allocating a new `BaseApi` object for a new
                `xmodel.base.model.BaseModel` class (not an instance, a model class/type).
                This BaseApi object is used for the class-level BaseModel api object;
                ie: via "ModelClass.api"

                See above "BaseModel Class Construction" for more details.

            model:  BaseModel to associate new BaseApi obj with.
                This is only used to create a new BaseApi object for a
                `xmodel.base.model.BaseModel`
                instance for an already-existing type. ie: for BaseModel object instances.

                See above "BaseModel Instance Creation" for more details.
        """
        if api and model:
            raise XModelError(
                f"You can't pass in an BaseApi {api} and BaseModel {model} simultaneously."
            )

        if model:
            api = type(model).api

        if not api:
            assert not model, "You can't pass in a model without an associated api/model obj."

        if model:
            # If we have a model, the structure should be exactly the same as it's BaseModel type.
            self._structure = api.structure
            self.default_converters = api.default_converters
            self._api_state = PrivateApiState(model=model)
            return

        # If We don't have a BaseModel, then we need to copy the structure, it could change
        # because we are being allocated for a new BaseModel type at the class/type level;
        # this means we are not associated with a specific BaseModel instance, only a BaseModel
        # type.

        # We lookup the structure type that our associated model-type/class wants to use.
        structure_type = get_type_hints(type(self)).get(
            'structure',
            BaseStructure[Field]
        )

        args = typing_inspect.get_args(structure_type)
        field_type = args[0] if args else Field

        # We have a root BaseModel with the abstract BaseModel as its super class,
        # in this case we need to allocate a blank structure object.
        # todo: allocate structure with new args
        existing_struct = api.structure if api else None
        self._structure = structure_type(
            parent=existing_struct,
            field_type=field_type
        )

        # default_converters is a mapping of type to convert too, and a converter callable.
        #
        # We want to inherit from the parent and converters they already have defined.
        #
        # Take any parent converters as they currently exist, and use them as a basis for our
        # converters. Then take any converters directly assigned to self and override the any
        # parent converters, when they both have a converter for the same key/type.
        self.default_converters = {
            **DEFAULT_CONVERTERS,
            **(api.default_converters or {} if api else {}),
            **(type(self).default_converters or {}),
        }

    # ----------------------------------------------------
    # --------- Things REQUIRING an Associated BaseModel -----

    @property
    def model(self) -> M:
        """ REQUIRES associated model object [see doc text below].

        Gives you back the model associated with this api. If this BaseApi obj is associated
        directly with the BaseModel class type and so there is no associated model, I will
        raise an exception.

        Some BaseApi methods are dependant on having an associated model, and when they ask for it
        and there is None, this will raise an exception for them. The first line of the doc
        comment tells you if it needs one.  Normally, it's pretty obvious if the method
        will need the model, due to what it will return to you (ie: if it would need model attrs).

        The methods that are dependant on a model are ones, like 'json', where it returns the
        JSON for a model.  It needs a model to get this data.

        If you access an object api via a BaseModel object, that will be the associated model.
        If you access it via a BaseModel type/class, it will be directly associated with the model
        class.

        Examples:
        >>> # Grab Account model from some_lib (as an example).
        >>> from some_lib.account import Account
        >>>
        >>> # api object is associated with MyModelClass class, not model obj.
        >>> Account.api
        >>>
        >>> account_obj = Account.api.get_via_id(3)
        >>> # api is associated with the account_obj model object.
        >>> account_obj.api
        >>>
        >>> # This sends object attributes to API, so it needs an associated
        >>> # BaseModel object, so this works:
        >>> account_obj.api.send()
        >>>
        >>> # This would produce an exception, since it would try to get BaseModel
        >>> # attributes to send. But there is no associated model.
        >>> Account.api.send()

        """
        api_state = self._api_state
        assert api_state, "BaseApi needs an attached model obj and there is no associated " \
                          "model api state."
        model = api_state.model
        assert model, "BaseApi needs an attached model obj and there is none."
        return model

    def get_child_without_lazy_lookup(
            self,
            child_field_name,
            *,
            false_if_not_set=False,
    ) -> Union[M, None, bool, NullType]:
        """ REQUIRES associated model object [see self.model].

        If the child is current set to Null, or an object, returns that value.
        Will NOT lazily lookup child, even if its possible to do so.

        :param child_field_name: The field name of the child object.
        :param false_if_not_set:
            Possible Values [Default: False]:
                * False: Return None if nothing is currently set.
                * True:  Return False if nothing is currently set. This lets you distinguish
                  between having a None value set on field vs nothing set at all.
                  Normally this distinction is only useful internally in this class,
                  external users probably don't need this option.
        """

        model = self.model

        if not self.structure.is_field_a_child(child_field_name):
            raise XModelError(
                f"Called get_child_without_lazy_lookup('{child_field_name}') but "
                f"field ({child_field_name}) is NOT a child field on model ({model}).")

        if child_field_name in model.__dict__:
            return getattr(model, child_field_name)

        if false_if_not_set:
            return False

        return None

    @property
    def have_changes(self) -> bool:
        """ Is True if `self.json(only_include_changes=True)` is not None;
            see json() method for more details.
        """
        log.debug(f"Checking Obj {self.model} to see if I have any changes [have_changes]")
        return self.json(only_include_changes=True) is not None

    def json(
        self, only_include_changes: bool = False, log_output: bool = False
    ) -> Optional[JsonDict]:
        """ REQUIRES associated model object (see `BaseApi.model` for details on this).

        Return associated model object as a JsonDict (str keys, any value), ready to be encoded
        via JSON encoder and sent to the API.

        Args:
            only_include_changes: If True, will only include what changed in the JsonDict result.
                Defaults to False.
                This is normally set to True if system is sending this object via PATCH, which is
                the  normal way the system sends objects to API.

                If only_include_changes is False (default), we always include everything that
                is not 'None'.
                When a `xmodel.base.client.BaseClient` subclass
                (such as `xmodel.rest.RestClient`)
                calls this method, it will pass in a value based on it's own
                `xmodel.rest.RestClient.enable_send_changes_only` is set to
                (defaults to False there too).
                You can override the RestClient.enable_send_changes_only at the BaseModel class
                level by making a RestClient subclass and setting `enable_send_changes_only` to
                default to `True`.

                There is a situations where we have to include all attributes, regardless:
                    1. If the 'id' field is set to a 'None' value. This indicates we need to create
                       a new object, and we are not partially updating an existing one, even if we
                       got updated via json at some point in the past.

                As always, properties set to None will *NOT* be included in returned JsonDict,
                regardless of what options have been set.

            log_output (bool): If False (default): won't log anything.
                If True: Logs what method returns at debug level.


        Returns:
            JsonDict: Will the needed attributes that should be sent to API.
                If returned value is None, that means only_include_changes is True
                and there were no changes.

                The returned dict is a copy and so can be mutated be the caller.
        """

        # todo: Refactor _get_fields() to return getter/setter closures for each field, and we
        #       can make this whole method more generic that way. We also can 'cache' the logic
        #       needed that way instead of having to figure it out each time, every time.

        structure = self.structure
        model = self.model
        api_state = self._api_state

        json: JsonDict = {}

        field_objs = structure.fields

        # Negate only_include_changes if we don't have any original update json to compare against.
        if only_include_changes and api_state.last_original_update_json is None:
            only_include_changes = False

        # noinspection PyDefaultArgument
        def set_value_into_json_dict(value, field_name, *, json=json):
            # Sets field value directly on json dict or passed in dict...
            if value is not None:
                # Convert Null into None (that's how JSON converter represents a Null).
                json[field_name] = value if value is not Null else None

        for field_obj in field_objs:
            # If we are read-only, no need to do anything more.
            if field_obj.read_only:
                continue

            # We deal with non-related types later.
            related_type = field_obj.related_type
            if not related_type:
                continue

            f = field_obj.name
            if field_obj.read_only:
                continue

            # todo: For now, the 'api-field-path' option can't be used at the same time as obj-r.
            if field_obj.json_path != field_obj.name:
                # I've put in some initial support for this below, but it's has not been tested
                # for now, keep raising an exception for this like we have been.
                # There is a work-around, see bottom part of the message in the below error:
                raise NotImplementedError(
                    f"Can't have xmodel.Field on BaseModel with related-type and a json_path "
                    f"that differ at the moment, for field ({field_obj}). "
                    f"It is something I want to support someday; the support is mostly in place "
                    f"already, but it needs some more careful thought, attention and testing "
                    f"before we should allow it. "
                    "Workaround:  Make an `{field.name}_id` field next to related field on the "
                    "model. Then, set `json_path` for that `{field.name}_id` field, set it to "
                    "what you want it to be. Finally, set the `{related_field.name}` to "
                    "read_only=True. This allows you to rename the `_id` field used to/from api "
                    "in the JSON input/output, but the Model can have an alternate name for the "
                    "related field. You can see a real-example of this at "
                    "`bigcommerce.api.orders._BcCommonOrderMetafield.order"
                )

            obj_type_structure = related_type.api.structure
            obj_type_has_id = obj_type_structure.has_id_field()

            if obj_type_has_id:
                # If the obj uses an 'id', then we have a {field_name}_id we want to
                # send instead of the full object as a json dict.
                #
                # This will grab the id from child obj if it exists, or from a defined field
                # of f"{f}_id" or finally from related id storage.

                # todo: If there is an object with no 'id' value, do we ignore it?
                #   or should we embed full object anyway?

                child_obj_id = api_state.get_related_field_id(f)

                # Method below should deal with None vs Null.
                set_value_into_json_dict(child_obj_id, f"{f}_id")
            else:
                obj: 'M' = getattr(model, f)

                # Related-object has no 'id', so get it's json dict and set that into the output.
                v = obj
                if obj is not Null and obj is not None:
                    # todo: a Field option to override this and always provide all
                    #   values (if object always needs to be fully embedded).
                    v = obj.api.json(only_include_changes=only_include_changes)

                # if it returns None (ie: no changes) and only_include_changes is enabled,
                # don't include the sub-object as a change.
                if v is not None or not only_include_changes:
                    # Method below should deal with None vs Null.
                    set_value_into_json_dict(v, f)

        for field_obj in field_objs:
            # If we are read-only, no need to do anything more.
            if field_obj.read_only:
                continue

            # We don't deal with related-types here.
            if field_obj.related_type:
                continue

            f = field_obj.name
            v = getattr(model, f)
            if v is not None and field_obj.converter:
                # Convert the value....
                v = field_obj.converter(
                    api=self,
                    direction=Converter.Direction.to_json,
                    field=field_obj,
                    value=v
                )

            path = field_obj.json_path
            if not path:
                set_value_into_json_dict(v, f)
                continue

            path_list = path.split(field_obj.json_path_separator)
            d = json
            for name in path_list[:-1]:
                d = d.setdefault(name, {})
            name = path_list[-1]

            # Sets field value into a sub-dictionary of the original `json` dict.
            set_value_into_json_dict(v, name, json=d)

        # If the `last_original_update_json` is None, then we never got update via JSON
        # so there is nothing to compare, include everything!
        if only_include_changes:
            log.debug(f"Checking Obj {model} for changes to include.")
            fields_to_pop = self.fields_to_pop_for_json(json, field_objs, log_output)

            for f in fields_to_pop:
                del json[f]

            if not json:
                # If nothing in JSON, then return None.
                return None
        else:
            due_to_msg = "unknown"
            if not only_include_changes:
                due_to_msg = "only_include_changes is False"
            if api_state.last_original_update_json is None:
                due_to_msg = "no original json value"

            if log_output:
                log.debug(f"Including everything for obj {model} due to {due_to_msg}.")

                # Log out at debug level what we are including in the JSON.
                for field, new_value in json.items():
                    log.debug(
                        f"   Included field ({field}) value ({new_value})"
                    )

        for k, v in json.items():
            # Must use list of JSON, convert any sets to a list.
            if type(v) is set:
                v = list(v)
                json[k] = v

        return json

    def fields_to_pop_for_json(
            self, json: dict, field_objs: List[Field], log_output: bool
    ) -> Set[Any]:
        """
        Goes through the list of fields (field_objs) to determine which ones have not changed in
        order to pop them out of the json representation. This method is used when we only want to
        include the changes in the json.

        :param json: dict representation of a model's fields and field values as they are currently
            set on the model.
        :param field_objs: List of fields and their values for a model
        :param log_output: boolean to determine if we should log the output or not
        :return: The field keys to remove from the json representation of the model.
        """
        fields_to_pop = set()
        for field, new_value in json.items():

            # json has simple strings, numbers, lists, dict;
            # so makes general comparison simpler.
            old_value = self._get_old_json_value(field=field, as_type=type(new_value))

            if old_value is Default:
                if log_output:
                    log.debug(
                        f"   Included field ({field}) with value "
                        f"({new_value}) because there is no original json value for it."
                    )
            elif self.should_include_field_in_json(
                    new_value=new_value,
                    old_value=old_value,
                    field=field
            ):
                if log_output:
                    log.debug(
                        f"   Included field ({field}) due to new value "
                        f"({new_value}) != old value ({old_value})."
                    )
            else:
                # We don't want to mutate dict while traversing it, remember this for later.
                fields_to_pop.add(field)

        # Map a field-key to what other fields should be included if field-key value is used.
        # For now we are NOT supporting `Field.json_path` to keep things simpler
        # when used in conjunction with `Field.include_with_fields`.
        # `Field` will raise an exception if json_path != field name and include_with_fields
        # is used at the same time.
        # It's something I would like to support in the future, but for now it's not needed.
        # We can assume that `field_obj.name == field_obj.json_path`
        for field_obj in field_objs:
            if not field_obj.include_with_fields:
                continue
            if field_obj.name not in fields_to_pop:
                continue
            if not (field_obj.include_with_fields <= fields_to_pop):
                fields_to_pop.remove(field_obj.name)

        return fields_to_pop

    def should_include_field_in_json(self, new_value: Any, old_value: Any, field: str) -> bool:
        """
        Returns True if the the value for field should be included in the JSON.
        This only gets called if only_include_changes is True when passed to self.json::

            # Passed in like so:
            self.json(only_include_changes=True)

        This method is an easy way to change the comparison logic.

        :param new_value: New value that will be put into JSON.
        :param old_value:
            Old value originals in original JSON [normalized if possible to the same type as
            new_value.
        :param field: Field name.
        :return:
            If True: Will include the fields value in an update.
            If False: Won't include the fields value in an update.
        """
        # Convert old value to set if new value is set and old value is list (from original JSON).
        # If I was really cool :)... I would find out the inner type in case of int/str
        # and to a conversion to compare Apples to Apples.....
        # But trying to minimize changes so I don't conflict as much with soon to be
        # xdynamo feature.
        if type(new_value) is set and type(old_value) is list:
            old_value = set(old_value)

        return new_value != old_value

    def _get_old_json_value(self, *, field: str, as_type: Type = None) -> Optional[Any]:
        """ Returns the old field-values; Will return `Default` if there is no original value.  """
        original_json = self._api_state.last_original_update_json
        if original_json is None:
            # todo: Is there another value we could return here to indicate that we
            #       never got an original value in the first place?
            #
            # todo: Also, think about how we could do above todo ^ per-field
            #       [ie: if field was requested in the first place].
            return Default

        old_value = original_json.get(field, Default)
        if old_value is Default:
            # None is a valid value in JSON,
            # this indicates to do the Default thing/value with this field since we don't have any
            # original value for it.
            return Default

        # json has simple strings, numbers, lists, dict;
        # so makes general comparison simpler.
        old_type = type(old_value)
        if as_type != old_type:
            str_compatible_types = {str, int, float}
            if as_type in str_compatible_types and old_type in str_compatible_types:
                try:
                    # The 'id' field is a string and not an int [for example], so in
                    # general, we want to try and convert the old value into the new
                    # values type before comparison, if possible, for the basic types
                    # of str, int, float.
                    old_value = as_type(old_value)
                except ValueError:
                    # Just be sure it's the same value/type, should be but just in case.
                    old_value = original_json.get(field, None)
                    pass
        return old_value

    def copy_from_model(self, model: BaseModel):
        their_fields = model.api.structure.field_map
        my_fields = self.structure.field_map
        keys = [k for k in their_fields if k in my_fields]

        # Assume we have a model, and are not the class-based `MyModel.api....` version.
        # todo: have `self.model` raise an exception if called on the class api version
        #   (which does not have a related model, just knows about model-type.).
        my_model = self.model
        for k in keys:
            their_value = getattr(model, k)
            if their_value is not None:
                setattr(my_model, k, their_value)

    def update_from_json(self, json: Union[JsonDict, Mapping]):
        """ REQUIRES associated model object [see self.model].

        todo: Needs more documentation

        We update the dict per-key, with what we got passed in [via 'json' parameter]
        overriding anything we got previously. This also makes a copy of the dict, which is
        want we want [no change to modify the incoming dict parameter].
        """

        structure = self.structure
        model = self.model
        api_state = self._api_state

        if not isinstance(json, Mapping):
            raise XModelError(
                f"update_from_json(...) was given a non-mapping parameter ({json})."
            )

        # Merge the old values with the new values.
        api_state.last_original_update_json = {
            **(api_state.last_original_update_json or {}),
            **json
        }

        fields = structure.fields

        values = {}
        for field_obj in fields:
            path_list = field_obj.json_path.split(field_obj.json_path_separator)
            v = json
            got_value = True
            for name in path_list:
                if name not in v:
                    # We don't even have a 'None' value so we assume we just did not get the value
                    # from the api, and therefore we just skip doing anything with it.
                    got_value = False
                    break

                v = v.get(name)
                if v is None:
                    break

            # We map the value we got from JSON into a flat-dict with the BaseModel name as the
            # key...
            if got_value:
                values[field_obj.name] = v if v is not None else Null

        def set_attr_on_model(field, value, model=model):
            """ Closure to set attr on self unless value is None.
            """
            if value is None:
                return
            setattr(model, field, value)

        # Merge in the outer json, keeping the values we mapped [via Field.json_path] for conflicts
        values = {**json, **values}

        # todo: If the json does not have a value [not even a 'None' value], don't update?
        #       We may have gotten a partial update?  For now, always update [even to None]
        #       all defined fields regardless if they are inside the json or not.

        for field_obj in fields:
            # We deal with related types later....
            if field_obj.related_type:
                continue

            f = field_obj.name
            v = values.get(f, Default)

            # A None from JSON means a Null for us.
            # If JSON does not include anything, that's a None for us.
            if v is None:
                v = Null
            elif v is Default:
                v = None

            # Run the converter if needed.
            # If we have a None value, we don't need to convert that, there was no value to
            # convert.
            if field_obj.converter and v is not None:
                v = field_obj.converter(
                    self,
                    Converter.Direction.from_json,
                    field_obj,
                    v
                )

            set_attr_on_model(f, v)

        for field_obj in fields:
            # Ok, now we deal with related types...
            related_type = field_obj.related_type
            if not related_type:
                continue

            f = field_obj.name

            # todo: at some point, allow customization of this via Field class
            #   Also, s tore the id
            f_id_name = f"{f}_id"
            if typing_inspect.get_origin(field_obj.type_hint) is list:
                # todo: This code is not complete [Kaden never finished it up]
                #   for now, just comment out.

                raise NotImplementedError(
                    "Type-hints for xmodel models in this format: `attr: List[SomeType]` "
                    "are not currently supported. We want to support it someday. For now you "
                    "must use lower-cased non-generic `list`. At some point the idea is to "
                    "allow one to do `List[ChildModel]` and then we know it's a list of "
                    "other BaseModel objects and automatically handle that in some way."
                )

                # child_type: 'Type[M]'
                # child_type = typing_inspect.get_args(obj_type)
                # # __args__ returns a tuple of all arguments passed into List[] so we need to
                # # pull the class out of the tuple
                # if child_type:
                #     child_type = child_type[0]
                #
                # child_api: BaseApi
                # child_api = child_type.api
                # if not child_api and child_api.structure.has_id_field:
                #     # TODO: add a non generic Exception for this
                #     raise XModelError(
                #         f"{model} has an attribute with name ({f}) with type-hint List that "
                #         f"doesn't contain an API BaseModel Type as the only argument"
                #     )
                # parent_name = model.__class__.__name__.lower()
                # state.set_related_field_id(f, parent_name)
                # continue

            v = None
            if f in values:
                v = values.get(f, Null)
                if v is not Null:
                    v = related_type(v)

            # Check to see if we have an api/json field for object relation name with "_id" on
            # end.
            if v is None and related_type.api.structure.has_id_field():
                # If we don't have a defined field for this value, check JSON for it and store it.
                #
                # If we have a defined None value for the id field, meaning the field exists
                # in the json, and is set directly to None, then we have a Null relationship.
                # We set that as the value, since there is no need to 'lookup' a null value.
                f_id_value = json.get(f_id_name)
                id_field = structure.get_field(f_id_name)

                if not id_field:
                    id_field = field_obj.related_type.api.structure.get_field('id')

                # Run the converter if needed.
                # If we have a None value, we don't need to convert that, there was no value to
                # convert.
                if id_field and id_field.converter and f_id_value is not None:
                    f_id_value = id_field.converter(
                        self,
                        Converter.Direction.from_json,
                        id_field,
                        f_id_value
                    )

                if f_id_value is None and f_id_name in json:
                    # We have a Null situation.
                    f_id_value = Null

                if f_id_value is not None:
                    # We have an id!
                    # Set the value to support automatic lookup of value, lazily.
                    # This method also takes care to set child object to Null or delete it
                    # as needed depending on the f_id_value and what the child's id field value is.
                    api_state.set_related_field_id(f, f_id_value)
            else:
                # 'v' is either going to be None, Null or an BaseModel object.
                set_attr_on_model(f, v)

    def list_of_attrs_to_repr(self) -> List[str]:
        """" REQUIRES associated model object [see self.model].

        A list of attribute names to put into the __repr__/string representation
        of the associated model object. This is consulted when the BaseModel has __repr__
        called on it.
        """
        names = set()
        model = self.model

        # todo: Move this into pres-club override of list_of_attrs_to_repr in an BaseApi subclass.
        if hasattr(model, 'account_id'):
            names.add('account_id')

        # todo: Consider adding others here, perhaps all defined fields on model that have
        # todo: a non-None value?

        for f in self.structure.fields:
            if f.include_in_repr:
                names.add(f.name)
        return list(names)

    def forget_original_json_state(self):
        """ If called, we forget/reset the orginal json state, which is a combination
            of all the json that this object has been updated with over it's lifetime.

            The json state is what allows the object to decide what has changed,
            when it's requested to only include changes via the `BaseApi.json` method.

            If forgotten, it's as-if we never got the json in the first place to compare against.
            Therefore, all attributes that have values will be returned for this object
            when it's only requested to include changes
            (the RestClient in xmodel-rest can request it to do this, as an example).

            Resetting the state here only effects this object, not any child objects.
            You'll have to ask child objects directly to forget t heir original json, if desired.
        """
        self._api_state.last_original_update_json = None

    # ----------------------------
    # --------- Private ----------
    #
    # I want to make the state and structure private for now, because it might change a bit later.
    # Want to give this some opportunity to be used for a while to see where the areas for
    # improvement are before potentially opening it up publicly to things outside of the sdk.

    _api_state: PrivateApiState[M] = None
    """ This object will vary from BaseModel class instance-to-instance, and is the area we keep
        api state that is Private for the BaseModel instance.

        Will be None if we are directly associated with BaseModel class, otherwise this will be the
        BaseModel's instance state, methods in this object need the BaseModel instance.
    """

    @property
    def context(self) -> XContext:
        """ BaseApi context to use when asking this object to send/delete/etc its self to/from
            service.

            This is an old hold-over from when we used to keep a XContext reference.
            This is the same as calling `xinject.context.XContext.current`.
        """
        return XContext.grab()
