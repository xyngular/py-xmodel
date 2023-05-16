import json
import sys
import typing

from xmodel.common.lazy import LazyClassAttr  # noqa - orm private module
from logging import getLogger
from typing import get_type_hints, TYPE_CHECKING, TypeVar, Generic, Type, Optional, Any, Mapping, \
    Callable
from abc import ABC
import inspect
import typing_inspect
from xmodel.common.types import JsonDict

from xsentinels.null import Null, NullType
from xsentinels.default import Default
from xmodel.util import loop

from xmodel.base.fields import Field, Converter
from xmodel import _private
from xmodel.errors import XModelError

if TYPE_CHECKING:
    # Allows IDE to get type reference without a circular import issue.
    from xmodel import BaseApi, ApiOptions

    # Just for type-completion of abstract interface,
    # for when we look up a remote sub-model.
    from xmodel.remote import RemoteModel
    # from typing import Self

log = getLogger(__name__)

M = TypeVar('M')

basic_type_hints_map = {
    int: lambda x: int(x),
    str: lambda x: str(x),
    bool: lambda x: bool(x),
    float: lambda x: float(x)
}

__pdoc__ = {
    # We want to pdoc3 to document this method [starts with `_`, so hidden by default].
    'BaseModel.__init_subclass__': True,
}


try:
    # If we are using Python 3.11, can use this new `Self` type that means current class/subclass
    # that is being used.
    # (it does appear that PyCharm >=2022.3 knows what `Self` is even if you use python < 3.11)
    # This is the only way I know to have a class-property/attribute that type-hints as the
    # subclass.
    from typing import Self

    # Attempt to use `dataclass_transform` on the `BaseModel` below.
    #
    # It happens to be that `Self` and `dataclass_transform` are both available in Python 3.11,
    # so the import-above is a good enough 'check' to prevent this from executing on Python < 3.11.
    model_auto_init = typing.dataclass_transform
except ImportError:
    # In regard to `Self`:
    #   In this case, we will set `Self` to `BaseModel` after the `BaseModel` class is defined.
    #   We need to have something defined for `Self` for Python < 3.11, since BaseModel and
    #   its subclasses have their type-hints resolved at runtime
    #   (also, `Self` is imported into modules that subclass `BaseModel` and redefine type-hint
    #    for `BaseModel.api`).

    # This here to support Python < 3.11 (ie: a decorator that does nothing).
    globals()['model_auto_init'] = lambda: lambda x: x


# Keeping the 'Generic[M]' part below temporarily for backwards compatibility;
# it's not needed anymore otherwise.
@model_auto_init()  # noqa - This will be defined.
class BaseModel(ABC):
    """
    Used as the abstract base-class for classes/object that communicate with our REST API.

    This is one of the main classes, and it's highly recommend you read the
    [SDK Library Overview](./#orm-library-overview) first, if you have not already.
    That document has many basic examples of using this class along with other related classes.

    Attributes that start with `_` or don't have a type-hint are not considered fields
    on the object that automatically get mapped to/from the JSON that is passed in.
    For more details see [Type Hints](./#type-hints).

    When you sub-class `BaseModel`, you can create your own Model class, with your own
    fields/attrs.
    You can pass class arguments/paramters in when you declare your sub-class.
    The Model-subclass can provide parameters to the super class during class construction.

    In the example below, notice the `base_url` part. That's a class argument, that is used by the
    super-class during the construction of the sub-class (before any instances are created).
    In this case it takes this and stores it on
    `xmodel.rest.RestStructure.base_model_url`
    as part of the structure information for the `BaseModel` subclass.

    See [Basic Model Example](./#basic-model-example) for an example of what class arguments
    are or look at this example below using a RestModel:

    >>> # 'base_url' part is a class argument:
    >>> from xmodel.rest import RestModel
    >>> class Account(RestModel["Account"], base_url='/account'):
    >>>    id: str
    >>>    name: str

    These class arguments are sent to a special method
    `xmodel.base.structure.BaseStructure.configure_for_model_type`. See that methods docs for
    a list of avaliable class-arguments.

    See `BaseModel.__init_subclass__` for more on the internal details of how this works exactly.

    .. note:: In the case of `base_url` example above, it's the base-url-endpoint for the model.
        If you want to know more about that see `xmodel.rest.RestClient.url_for_endpoint`.
        It has details on how the final request `xurls.url.URL` is constructed.

    This class also allows you to more easily with with JSON data via:

    - `xmodel.base.api.BaseApi.json`
    - `xmodel.base.api.BaseApi.update_from_json`
    - Or passing a JSON dict as the first arrument to `BaseModel.__init__`.

    Other important related classes are listed below.

    - `xmodel.base.api.BaseApi` Accessable via `BaseModel.api`.
    - `xmodel.rest.RestClient`: Accessable via `xmodel.base.api.BaseApi.client`.
    - `xmodel.rest.settings.RestSettings`: Accessable via
        `xmodel.base.api.BaseApi.settings`.
    - `xmodel.base.structure.BaseStructure`: Accessable via
        `xmodel.base.api.BaseApi.structure`
    - `xmodel.base.auth.BaseAuth`: Accessable via `xmodel.base.api.BaseApi.auth`

    .. tip:: For all of the above, you can change what class is allocated for each one
        by changing the type-hint on a subclass.

    """

    # -------------------------------------
    # --------- Public Properties ---------

    api: "BaseApi[Self]" = None
    """ Used to access the api class, which is used to retrieve/send objects to/from api.

        You can specify this as a type-hint in subclasses to change the class we use for this
        automatically, like so::
            from xmodel import BaseModel, BaseApi
            from xmodel.base.model import Self
            from typing import TypeVar

            M = TypeVar("M")

            class MyCoolApi(BaseApi[M]):
                pass

            class MyCoolModel(BaseModel):
                # The `Self` here is imported from xmodel
                # (to maintain backwards compatability with Python < 3.11)
                # It allows us to communicate our subclass-type to the `api` object,
                # allowing IDE to type-complete/hint better.
                api: MyCoolApi[Self] 

        The generic ``T`` type-var in this case refers to whatever model class that your using.
        In the example just above, ``T`` would be referring to ``MyCoolModel`` if you did this
        somewhere to get the BaseModel's api: ``MyCoolModel.api``.
    """

    # --------------------------------------------
    # --------- Config/Option Properties ---------

    def __init_subclass__(
        cls: Type[M],
        *,
        lazy_loader: Callable[[Type[M]], None] = None,
        **kwargs
    ):
        """
        We take all arguments (except `lazy_loader`) passed into here and send them to the method
        on our structure:
        `xmodel.base.structure.BaseStructure.configure_for_model_type`.
        This allows you to easily configure the BaseStructure via class arguments.

        For a list of class-arguments, see method parameters for
        `xmodel.base.structure.BaseStructure.configure_for_model_type`.

        See [Basic BaseModel Example](./#basic-model-example) for an example of what class
        arguments are for `BaseModel` classes and how to use them.

        We lazily configure BaseModel sub-classes. They are configured the first time that
        `BaseModel.api` is accessed under that subclass. At that point all parent + that specific
        subclass are configured and an `xmodel.base.api.BaseApi` object is created and set
        on the `BaseModel.api` attribute. From that point forward, that object is what is used.
        This only happens the first time that `BaseModel.api` is accessed.

        If you want to add support for additional BaseModel class arguments,
        you can do it by modifying the base-implementation
        `xmodel.base.structure.BaseStructure`.
        Or if you want it only for a specific sub-set of Models, you can make a custom
        `xmodel.base.structure.BaseStructure` subclass. You can configure your BaseModel to use
        this BaseStructure subclass via a type-hint on `xmodel.base.api.BaseApi.structure`.

        See `xdynamo.dynamo.DynStructure.configure_for_model_type` for a complete example of a
        custom BaseStructure subclass that adds extra class arguments that are specific to Dynamo.

        Args:
            lazy_loader: This is a callable where the first argument is `cls/self`.
                This is an optional param. If provided, we will call when we need to lazy-load
                but before we do our normal lazy-loading ourselves here.

                Most of the time, you'll want to import into the global/module space of where
                your class lives any imports you need to do lazily, such as circular imports.

                Right after we call your lazy_loader callable, we will be ourselves calling
                the method `get_type_hints` to get all of our type-hints.
                You'll want to be sure all of your forward-referenced type-hints on your
                model sub-class are resolvable.

                Forward-ref type hints are the ones that are string based type-hints,
                they get resolved lazily after your lazy_loader (if provided) is called.

                You can see in the code in our method below, look at the check for:

                >>> if "BaseApi" not in globals():

                Look at that for a real-world example of what I am talking about.
                This little piece of code lazily resolves the `BaseApi` type.
        """

        # We are taking all args and sending them to a xmodel.base.structure.BaseStructure
        # class object.
        super().__init_subclass__()

        def lazy_setup_api(cls_or_self):
            # If requested, before we do our own lazy-loading below, call passed in lazy-loader.
            if lazy_loader:
                lazy_loader(cls)

            for parent in cls.mro():
                if parent is not cls and issubclass(parent, BaseModel):
                    # Ensure that parent-class has a chance to lazy-load it's self
                    # before we try to examine our type-hints.
                    getattr(parent, 'api')

            # We potentially get called a lot (for every sub-class)
            # so check to see if we already loaded BaseApi type or not.
            if 'BaseApi' not in globals():
                # Lazy import BaseApi into module, helps resolve BaseApi forward-refs;
                # ie: `api: "BaseApi[T]"`
                # We need to resolve these due to use of `get_type_hints()` below.
                #
                # Sets it in such a way so IDE's such as pycharm don't get confused + pydoc3
                # can still find it and use the type forward-reference.
                #
                # todo: figure out why dynamic model attribute getter is having an issue with this.
                #   (see that near start of this file at top ^^^)
                from xmodel import BaseApi
                globals()['BaseApi'] = BaseApi
            try:
                all_type_hints = get_type_hints(cls)
            except (NameError, AttributeError) as e:
                from xmodel import XModelError
                raise XModelError(
                    f"Unable to construct model subclass ({cls}) due to error resolving "
                    f"type-hints on model class. They must be visible at the module-level that "
                    f"the class is defined in. Original error: ({e})."
                ) from None

            api_cls: Type["BaseApi"] = all_type_hints['api']

            base_cls = None
            for b in cls.__bases__:
                if b is BaseModel:
                    break
                if issubclass(b, BaseModel):
                    base_cls = b
                    break

            base_api = None
            if base_cls:
                base_api = base_cls.api

            api = api_cls(api=base_api)
            cls.api = api

            # Configure structure for our model type with the user supplied options + type-hints.
            structure = api.structure
            try:
                structure.configure_for_model_type(
                    model_type=cls,
                    type_hints=all_type_hints,
                    **kwargs
                )
            except TypeError as e:
                from xmodel import XModelError
                # Adding some more information to the exception.
                raise XModelError(
                    f"Unable to configure model structure for ({cls}) due to error ({e}) "
                    f"while calling ({structure}.configure_for_model_type)."
                )
            return api

        # The LazyClassAttr will turn into the proper type automatically when it's first accessed.
        lazy_api = LazyClassAttr(lazy_setup_api, name="api")

        # Avoids IDE from using this as type-hint for `self.api`, we want it to use the type-hint
        # defined on attribute.
        # Otherwise it will try to be too cleaver by trying to use the type in `lazy_api` instead.
        # The object in `lazy_api` will transform into what has been type-hinted
        # when it's first accessed by something.
        setattr(cls, "api", lazy_api)

    # -------------------------------
    # --------- Init Method ---------

    # todo: Python 3.8 has support for positional-arguments only, do that when we start using it.
    # See Doc-Comment for what *args is.
    def __init__(self, *args, **initial_values):
        """
        Creates a new model object. The first/second params need to be passed as positional
        arguments. The rest must be sent as key-word arguments. Everything is optional.

        Args:
            id: Specify the `BaseModel.id` attribute, if you know it. If left as Default, nothing
                will be set on it. It could be set to something via args[0] (ie: a JSON dict).
                If you do provide a value, it be set last after everything else has been set.

            *args: I don't want to take names from what you could put into 'initial_values',
                so I keep it as position-only *args. Once Python 3.8 comes out, we can use a
                new feature where you can specify some arguments as positional-only and not
                keyword-able.

                ## FirstArg - If Dict:
                If raw dictionary parsed from JSON string. It just calls
                `self.api.update_from_json(args[0])` for you.

                ## FirstArt - If BaseModel:
                If a `BaseModel`, will copy fields over that have the same name.
                You can use this to duplicate a Model object, if you want to copy it.
                Or can be used to copy fields from one model type into another,
                on fields that are the same name.

                Will ignore fields that are present on one but not the other.
                Only copy fields that are on both models types.

            **initial_values: Let's you specify other attribute values for convenience.
                They will be set into the object the same way you would normally doing it:
                ie: `model_obj.some_attr = v` is the same as `ModelClass(some_attr=v)`.
        """
        args_len = len(args)
        if args_len > 1:
            raise NotImplementedError(
                "Passing XContext via second positional argument is no longer supported."
            )

        cls_api_type = type(type(self).api)
        api = cls_api_type(model=self)
        setattr(self, "api", api)  # Avoids IDE from using this as type-hint for `self.api`.

        first_arg = args[0] if args_len > 0 else None

        if isinstance(first_arg, str):
            # We assume `str` is a json-string, parse json and import.
            json_objs = json.loads(first_arg)
            api.update_from_json(json_objs)
        elif isinstance(first_arg, BaseModel):
            # todo: Probably make this recursive, in that we copy sub-base-models as well???
            api.copy_from_model(first_arg)
        elif isinstance(first_arg, Mapping):
            api.update_from_json(first_arg)
        elif first_arg is not None:
            raise XModelError(
                f"When a first argument to BaseModel.__init__ is provided, it needs to be a "
                f"mapping/dict with the json values in it "
                f"OR a BaseModel instance to copy from "
                f"OR a str with a json dict/obj to parse inside of string; "
                f"I was given a type ({type(first_arg)}) with value ({first_arg}) instead."
            )

        for k, v in initial_values.items():
            if not self.api.structure.get_field(k):
                raise XModelError(
                    f"While constructing {self}, init method got a value for an "
                    f"unknown field ({k})."
                )

            setattr(self, k, v)

    def __repr__(self):
        msgs = []
        for attr in self.api.list_of_attrs_to_repr():
            msgs.append(f'{attr}={getattr(self, attr, None)}')

        full_message = ", ".join(msgs)
        return f"{self.__class__.__name__}({full_message})"

    def __setattr__(self, name, value):
        # This gets called for every attribute set.

        # DO NOT use hasattr() in here, because you could make every lazily loaded object load up
        # [ie: an API request to grab lazily loaded object properties] when the lazy object is set.

        api = self.api
        structure = api.structure
        field = structure.get_field(name)
        type_hint = None

        if inspect.isclass(self):
            # If we are a class, just pass it along
            pass
        elif name == "api":
            # Don't do anything special with the 'api' var.
            pass
        elif name.startswith("_"):
            # don't do anything with private vars
            pass
        elif name.endswith("_id") and structure.is_field_a_child(name[:-3], and_has_id=True):
            # We have a virtual field for a related field id, redirect to special setter.
            state = _private.api.get_api_state(api)
            state.set_related_field_id(name[:-3], value)
            return

        if not field:
            # We don't do anything more without a field object
            # (ie: just a normal python attribute of some sort, not tied with API).
            super().__setattr__(name, value)
            return

        try:
            # We have a value going to an attributed that has a type-hint, checking the type...
            # We will also support auto-converting to correct type if needed and possible,
            # otherwise an error will be thrown if we can't verify type or auto-convert it.
            type_hint = field.type_hint
            value_type = type(value)
            field_obj: Field = structure.get_field(name)

            # todo: idea: We could cache some of these details [perhaps even using closures]
            #       or use dict/set's someday for a speed improvement, if we ever need to.

            hint_union_sub_types = ()
            if typing_inspect.is_union_type(type_hint):
                # Gets all args in a union type, to see if one of them will match type_hint.
                hint_union_sub_types = typing_inspect.get_args(type_hint)
                # Get first type hint in untion, Field object (where we just got type-hint)
                # already unwraps the type hint, removing any Null/None types. It's a Union
                # only if there are other non-Null/None types in a union. For right now
                # lets only worry about the first one.
                type_hint = hint_union_sub_types[0]

            state = _private.api.get_api_state(api)
            if (
                # Check for nullability first, as an optimization.
                field.nullable and
                type_hint not in [str, None] and
                value_type is str and
                not value
            ):
                value = Null
            elif value is None:
                # By default, this is None [unless user specified something].
                value = _get_default_value_from_field(self, field)
            elif (
                value_type is type_hint
                or value_type in hint_union_sub_types
                or Optional[value_type] is type_hint
                or type_hint is NullType and field.nullable
            ):
                # Type is the same as type hint, no need to do anything else.
                # We check to reset any related field id info, just in case it exists,
                # since this field is either being set to Null or an actual object.
                state.reset_related_field_id_if_exists(name)
                pass
            elif value is Null:
                # If type_hint supported the Null type, then it would have been dealt with in
                # the previous if statement.
                XModelError(
                    f"Setting a Null value for field ({name}) when typehint ({type_hint}) "
                    f"does not support NullType, for object ({self})."
                )
            elif field_obj.converter:
                # todo: Someday map str/int/bool (basic conversions) to standard converter methods;
                #   kind of like I we do it for date/time... have some default converter methods.
                #
                # This handles datetime, date, etc...
                value = field_obj.converter(api, Converter.Direction.to_model, field_obj, value)
            elif type_hint in (dict, JsonDict) and value_type in (dict, JsonDict):
                # this is fine for now, keep it as-is!
                #
                # For now, we just assume things in the dict are ok.
                # in the future, we will support `Dict[str, int]` or some such and we will
                # check/convert/ensure the types as needed.
                pass
            elif type_hint in (dict, JsonDict) and value_type in (int, bool, str):
                # just passively convert bool/int/str into empty dict if type-hint is a dict.
                log.warning(
                    f"Converted a int/bool/str into an empty dict. Attr name ({name}),"
                    f"value ({value}) type-hint ({type_hint}) object ({self}). If you don't want"
                    f"to do this, then don't put a type-hint on the attribute."
                )
                value = {}
            elif typing_inspect.get_origin(type_hint) in (list, set):
                # See if we have a converter for this type in our default-converters....
                inside_type_hint = typing_inspect.get_args(type_hint)[0]
                basic_type_converter = self.api.default_converters.get(inside_type_hint)
                if basic_type_converter:
                    converted_values = [
                        basic_type_converter(
                            api,
                            Converter.Direction.to_model,
                            field_obj,
                            x
                        ) for x in loop(value)
                    ]

                    container_type = typing_inspect.get_origin(type_hint)
                    value = container_type(converted_values)
                # Else/Otherwise we just leave things as-is for now, no error and no conversion
                pass
            # Python 3.7 does not have GenericMeta anymore, not sure if we need it, we just need
            # to try using this for a bit and see what happens.
            #
            # If needed in Python 3.7, we can see if we can remove this loop-hole with the new
            # typing_inspect.* methods.
            #
            # elif type(type_hint) is GenericMeta:
            #     # This is a complex type (probably a Parameterized generic), not going to try and
            #     # check it out, don't want to throw and error as well, just pass it though.
            #     #
            #
            #     pass

            else:
                raise AttributeError(
                    f"Setting name ({name}) with value ({value}) with type ({value_type}) on "
                    f"API object ({self}) but type-hint is ({type_hint}), and I don't know how"
                    f" to auto-convert type ({value_type}) into ({type_hint})."
                )
        except ValueError:
            # We want to raise a more informative error than the base ValueError when there
            # is a problem parsing a value
            raise AttributeError(
                f"Parsing value ({value}) with type-hint ({type_hint}) resulted in an error "
                f"for attribute ({name}) on object ({self})"
            )

        if isinstance(value, str):
            # This value has caused me a lot of problems, it's time to ALWAYS treat them
            # as blank strings, exactly what they should have been set to in the first place.
            if value.startswith('#########'):
                value = ''

        if field_obj.post_filter:
            value = field_obj.post_filter(api=api, name=name, value=value)

        if field.fset:
            field.fset(self, value)
        elif field.fget:
            raise XModelError(
                f"We have a field ({field}) that does not have a Field.fset (setter function),"
                f"but has a Field.fget ({field.fget}) and someone is attempting to set a "
                f"value on the Model object ({self})... this is unsupported. "
                f"If you want to allow setting the value, you must provider a setter when a "
                f"getter is present/provided."
            )
        else:
            super().__setattr__(name, value)

    def __getattr__(self, name: str):
        # Reminder: This method only gets called if attribute is not currently defined in self.
        structure = self.api.structure
        state = _private.api.get_api_state(self.api)

        field = structure.get_field(name)

        if name.startswith("_"):
            return object.__getattribute__(self, name)

        if field and field.fget:
            # Use getter to get value, if we get a non-None value return it.
            # If we get a None back, then do the default thing we normally do
            # (ie: look for default value, related object, etc).
            value = field.fget(self)
            if value is not None:
                return value

        if name.endswith("_id") and structure.is_field_a_child(name[:-3], and_has_id=True):
            # We have a field that ends with _id, that when taken off is a child field that
            # uses and id. This means we should treat this field as virtually related field id.
            value = state.get_related_field_id(name[:-3])
            if value is not None:
                if field and field.fset:
                    field.fset(self, value)
                return value

        if not field:
            raise AttributeError(
                f"Getting ({name}) on ({self.__class__.__name__}), which does not exist on object "
                f"or in API. For API objects, you need to use already defined fields/attributes."
            )

        if (
            field.related_type is not None and
            field.related_type.api.structure.has_id_field()
        ):
            name_id_value = state.get_related_field_id(name)

            # RemoteModel is an abstract interface,
            # Let's us know how to lazily lookup remote objects by their id value.
            name_type: "RemoteModel" = field.related_type
            obj = None

            if name_id_value is Null:
                # Don't attempt to lookup object, we have it's primary id:
                obj = Null
            elif name_id_value is not None:
                # Attempt to lookup remote object, we have it's primary id:
                obj = name_type.api.get_via_id(name_id_value)
                # todo: consider raising an exception if we have an `id` but no related object?
                #   I'll think about it.

                # if we have an object, set it and return it
                if obj is not None:
                    if field.fset:
                        field.fset(self, obj)
                    else:
                        super().__setattr__(name, obj)
                    return obj
                # Otherwise, we continue, next thing to do is look for any default value.

        # We next look for a default value, if any set/return that.
        default = _get_default_value_from_field(self, field)

        # We set to default value and return it if we have a non-None value.
        if default is not None:
            # We have a value of some sort, call setter:
            if field.fset:
                field.fset(self, default)
            else:
                super().__setattr__(name, default)
            return default

        # We found no default value, return None.
        return None

    def __eq__(self, other):
        """ For BaseModel, by default our identity is based on object instance ID, not any values
            in our attributes.  Makes things simpler when trying to find object/self in a Set;
            which is useful when traversing relationships.
        """
        return self is other

    def __hash__(self):
        """ For BaseModel, by default our identity is based on object instance ID, not any values
            in our attributes.  Makes things simpler when trying to find object/self in a Set;
            which is useful when traversing relationships.
        """
        return id(self)


if 'Self' not in globals():
    # I need to have this set to something because `BaseModel` and it's subclasses get their
    # typehints resolved at run-time (to implement the needed dynamic behavior).
    #
    # This is the best we can do for a `Self` class-property when using python version < 3.11
    # without resorting to self-referential Generics (which are annoying, since you need to
    # define them at every model-leaf endpoint);
    #
    # Newer PyCharm >=2022.3 will see the above Self typing import and still work even if local project
    # is using an older version of Python!.
    #
    # Using `globals` here to hide this typing-info from PyCharm (and other IDEs).
    globals()['Self'] = BaseModel


def _get_default_value_from_field(model: BaseModel, field: Field = None) -> Any:
    if not field or field.default is None:
        return None

    default = field.default

    if default is Null:
        if not field.nullable:
            raise XModelError(f"Default for field {field} is Null but field is not Nullable.")
        return Null

    if default is Default:
        return None

    # If it's callable, we call it;
    # It could be a list or a dict type or a generator function of some sort.
    if callable(default):
        default = default()
    elif not inspect.isclass(default) and isinstance(default, BaseModel):
        # We should make a copy of the object, as using the same instance 'default' across multiple
        # instances is almost certainly not what the user wants.
        # if the user truly wants to share the same exact default BaseModel instance across multiple
        # other BaseModel attributes, they can wrap it in a lambda/method, like this:
        #
        # class M1(BaseModel):
        #     pass
        #
        # shared_default = M1()
        #
        # class M2(BaseModel):
        #     m1: M1 = lambda: shared_default

        # Make a copy via sending object to BaseModel init-method.
        default = type(default)(default)

    default_type = type(default)
    type_hint = field.type_hint
    if default_type is not type_hint and default_type is not typing_inspect.get_origin(type_hint):
        if not field.converter:
            raise XModelError(
                f"Default for field ({field.name}) for model_type ({type(model)}) is of type "
                f"({type(default)}), "
                f"but fields type-hint is ({field.type_hint}) which is not the same; "
                f"also, field has no converter function to convert to that type to attempt a "
                f"conversion with; model: {model}"
            )

        # Convert value, since we have a converter but the type is not the same.
        return field.converter(model.api, Converter.Direction.to_model, field, default)

    return default
