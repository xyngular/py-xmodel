"""
.. todo:: Write this module doc-comment, here is a link that might be useful;
    it links back to the the overview doc for field objects at xmodel.__init__.py
For more details see [Field Objects](../#field-objects)
"""
from typing import TypeVar, Any, Type, Optional, TYPE_CHECKING, Dict, Set

from xmodel.common.unwrap import unwrap_optional_type
from abc import ABC, abstractmethod
from xsentinels.default import Default
import dataclasses
from enum import Enum, auto as EnumAuto  # noqa
from xmodel.errors import XModelError
from copy import copy
import typing_inspect
import inspect
from xmodel.util import loop

if TYPE_CHECKING:
    from xmodel import BaseModel
    from xmodel import BaseApi

T = TypeVar("T")

# We want these special methods in the documentation.
__pdoc__ = {
    'Converter.__call__': True,
    'Filter.__call__': True
}


class Converter:
    """ This is meant to be a Callable that converts to/from a type when a value is assigned
        to a `xmodel.base.model.BaseModel`.

        See `Converter.__call__` for the calling interface.

        You can set these on `Field.converter` or `xmodel.base.api.BaseApi.default_converters`.
    """
    class Direction(Enum):
        """ Possible values for field option keys. """
        to_json = EnumAuto()
        """ We are converting from BaseModel into JSON. """
        from_json = EnumAuto()
        """ We are converting from JSON and need value to set on BaseModel. """
        to_model = EnumAuto()
        """ We are setting a value on the BaseModel [could be coming from anywhere]. """

    def __call__(
            self,
            api: "BaseApi",
            direction: Direction,  # todo: Used to be 'to_json', need to fix it everywhere...
            field: "Field",  # todo: this is a new param, use to be 'field_name'...
            value: Any,
    ) -> Any:
        """
        Gets called when something needs to be converted.

        By default, this will call one of these depending on the direction:

        - `Converter.to_json`
        - `Converter.from_json`
        - `Converter.to_model`

        Args:
            api (xmodel.base.api.BaseApi): This has the associated
                `xmodel.base.model.BaseModel.api` object, from which we need a value converted.
            direction (Converter.Direction): Look at `Converter.Direction` for details.
            field (str): Field information, this contains the name, types, etc...
            value (Any): The value that needs to be converted.
        """
        Direction = Converter.Direction  # noqa
        if direction == Direction.to_json:
            return self.to_json(api, field, value)

        if direction == Direction.from_json:
            return self.from_json(api, field, value)

        if direction == Direction.to_model:
            return self.to_model(api, field, value)

    # Instead of implementing `__call__`, you can implement of these instead if that's easier.
    def to_json(self, api: 'BaseApi', field: 'Field', value: Any):
        """ todo """
        raise NotImplementedError(
            f"Converter ({self}) has no __call__ or to_json method which does the conversion."
        )

    def from_json(self, api: 'BaseApi', field: 'Field', value: Any):
        """ todo """
        raise NotImplementedError(
            f"Converter ({self}) has no __call__ or from_json method which does the conversion."
        )

    def to_model(self, api: 'BaseApi', field: 'Field', value: Any):
        """ todo """
        raise NotImplementedError(
            f"Converter ({self}) has no __call__ or to_model method which does the conversion."
        )


class Filter(ABC):
    """ A method or callable object signature.

        See `Filter.__call__` for details.
    """

    @abstractmethod
    def __call__(self, api: "BaseApi", name: str, value: T) -> T:
        """
        A method signature for filter-callback, allows one to filter/change values.

        For a real-world example, see `LowerFilter`.

        Args:
            api: This has the associated `xmodel.base.model.BaseModel.api` object,
                from which we need a value converted.
            name: name of field.
            value: value of field.
        """
        return value


class LowerFilter(Filter):
    """ Lower-cases a value on a `xmodel.base.model.BaseModel` field.

        You can see a real-world example of using this filter on:
        `hubspot.api.Contact.email`

        Example of setting it on a field:

        >>> from xmodel.base.model import BaseModel
        >>> from xmodel.fields import Field, LowerFilter
        >>> class MyModel(BaseModel):
        ...     filtered_attr: Field(post_filter=LowerFilter())
        >>>
        >>> obj = MyModel()
        >>> obj.filtered_attr = "HELLO"
        >>> assert obj.filtered_attr == "hello"
    """
    def __call__(self, api: "BaseApi", name: str, value: str) -> str:
        return value.lower()


@dataclasses.dataclass(eq=False)
class Field:
    """
    If this is not used on a model field/attribute, the field will get the default set of
    options automatically if the field has a type-hint; see topic
    [BaseModel Fields](./#model-fields).

    Preferred way going forward to provide additional options/configuration to BaseModel fields.

    If you don't specify a value for a particular attribute, it will have the
    `xsentinels.default.Default` value. When a Default value is encountered while constructing a
    `xmodel.base.model.BaseModel`, it will resolve these Default values and assign the final
    value for the field.

    To resolve these Defaults, it will look at field on the parent BaseModel class.
    If a non-Default value is defined there, it will use that for the child.
    If not, then it looks at the next parent. If no non-Default value is found we then use
    a value that makes sense. You can see what this is in the first line of each doc-comment.
    In the future, when we start using Python 3.9 we can use type annotations (typing.Annotated)
    to annotate a specific value to the Default type generically. For now it's hard-coded.

    ## Side Notes

    Keep in mind that after the `.api` is accessed for the first time on a particular model
    class, the sdk will construct the rest of the class (lazily)...
    it will read and then remove/delete from the BaseModel class any type-hinted json fields
    with a Field object assigned to the class. It moves these Field objects into a special
    internal structure.  The class gets `None` values set on all fields after this is done.

    ## Details on why we remove them:

    Doing this helps with __getattr__, as it will still be executed for fields without a value
    when we create an object instance. __getattr__ is used to support lazy lookups [via API] of
    related objects. Using __getattr__ is much faster than using the __getattribute__ version.
    So I want to keep using the __getattr__ version if possible.
    """

    _options_explicitly_set_by_user: Set[str] = dataclasses.field(default=None, repr=False)

    def was_option_explicitly_set_by_user(self, option_name: str) -> bool:
        """ Given an option / field-attribute name, if the option was explicitly set by
            the user then we return True.

            If not we return False.

            We determine this while `Field.resolve_defaults` is called, it checks to see
            what is still set to `Default`.

            If an option is not `Default` anymore when `resolve_defaults` is first called, we
            consider it set by the user.

            This is important, as it informs subclasses of BaseModel if their parent model's
            field's value was resolved automatically or if it was set by user.

            Generally, if it was resolved automatically, we continue to resolve it automatically.

            If it was set by the user we tend to use what the user set it to and not resolve
            it automatically.
        """
        return option_name in self._options_explicitly_set_by_user

    def resolve_defaults(
            self,
            *,  # Keyword args only after this point
            name,
            type_hint: Type,
            default_converter_map: Optional[Dict[Type, Converter]] = None,
            parent_field: "Field" = None
    ):
        """
        Resolves all dataclass attributes/fields on self that are still set to `Default`.
        The only exception is `type_hint`. We will always use what is passed in, regardless
        of if there is a parent-field with one set. This allows one on a BaseModel to easily
        override the type-hint without having to create a field with an explicitly set
        type_hint set on it (ie: let normal python annotated type-hint override any parent type).

        This includes ones on subclasses [dataclass will generically tell us about all of them].
        System calls this when a BaseModel class is being lazily constructed
        [ie: when gets the `xmodel.base.model.BaseModel.api` attribute for the first time or
        attempts to create an instance of the BaseModel for the fist time].

        When the BaseModel class is being constructed, this method is called to resolve all
        the Default values still on the instance. We do this by:

        1. We first look at parent_field object if one has been given.
            - If ask that parent field which options where explicitly set by user and which
                ones were set by resolving a `xsentinels.default.Default`. Field objects have an
                internal/private var that keeps track of this.
        2. Next, figure out standard default value for option if option's current value is
            current at `xsentinels.default.Default` (a default sentential value, used to detect
            which values were left unset by user).


        ## More Details

        I have Field objects keep track of which fields were not at
        Default when they are resolved. This allows child Field objects
        to know which values to copy into themselves and which ones
        should be resolved normally via Default.

        The goal here is to avoid copying value from Parent that
        were originally resolved via Default mechanism
        (and were not set explicitly by user).

        An example of why this is handy:

        If we have a parent model with a field of a different type vs the one on the child.
        Unless the converter was explicitly set by the user we want to just use the default
        converter for the different type on the child (and not use the wrong converter by default).
        """

        # Get pycharm to go to class-level var/typehint with the attribute docs we have written
        # instead of going into this method where it gets assigned.
        # Using different var-name for self seems to be able to do that.
        _self = self

        if parent_field:
            options_explicitly_set_by_user = parent_field._options_explicitly_set_by_user
        else:
            options_explicitly_set_by_user = set()

        # Keep track of what was Default before resolving with parent
        # [ie: was not explicitly set by user].
        was_default_before_parent = set()

        for data_field in dataclasses.fields(self):
            data_field_name = data_field.name
            child_value = getattr(self, data_field_name)
            if child_value is Default:
                was_default_before_parent.add(data_field_name)
            else:
                options_explicitly_set_by_user.add(data_field_name)

        # Store for future child-fields.
        self._options_explicitly_set_by_user = options_explicitly_set_by_user

        if parent_field:
            if not isinstance(self, type(parent_field)):
                raise XModelError(
                    f"Child field {self} must be same or subclass of parent ({parent_field})."
                )

            # Go though each dataclass Field in parent, take it's value and copy it to child if:
            #   1. The child still has it set to `Default`.
            #   2. The parent's value is not `Default`.
            #   3. The parent's value was set by the user (options_explicitly_set_by_user).
            #       - If the value was not set by user, we just leave us at `Default` and resolve
            #           them normally.
            for parent_data_field in dataclasses.fields(parent_field):
                p_attr_field: dataclasses.Field
                data_field_name = parent_data_field.name
                parent_value = getattr(parent_field, data_field_name)
                child_value = getattr(self, data_field_name)

                if parent_value is Default:
                    continue

                if data_field_name not in options_explicitly_set_by_user:
                    continue

                if child_value is Default:
                    # Child has Default and parent is not-Default, copy value onto child
                    setattr(self, data_field_name, copy(parent_value))

        # We always set the type-hint, Python will automatically surface the most recent
        # type-hint for us. We want to have it easily overridable without having to use a
        # Field class explicitly.
        _self.type_hint = type_hint

        # Resolve the special-case non-None Default's...
        if self.name is Default:
            # todo: figure out if we should always set name...
            #   ...i'm inclined to not do that.
            _self.name = name

        if self.json_path is Default:
            _self.json_path = self.name

        if self.include_with_fields is Default:
            _self.include_with_fields = set()
        else:
            # Ensure it's a set, not a list or some other thing the user provided.
            _self.include_with_fields = set(loop(self.include_with_fields))

        if self.include_with_fields and self.name != self.json_path:
            raise XModelError(
                f"Can't have a Field with `name != json_path` "
                f"('{self.name}' != '{self.json_path}')"
                f"and that also uses include_with_fields "
                f"({self.include_with_fields})"
            )

        if self.json_path_separator is Default:
            _self.json_path_separator = '.'

        if self.include_in_repr is Default:
            _self.include_in_repr = False

        if self.exclude is Default:
            _self.exclude = False

        if self.read_only is Default:
            _self.read_only = False

        # If converter is None, but we do have a default one, use it...
        if (
            default_converter_map and
            self.type_hint in default_converter_map and
            'converter' in was_default_before_parent and
            self.converter in (None, Default)
        ):
            _self.converter = default_converter_map.get(self.type_hint)

        if (
            self.converter is Default and
            inspect.isclass(self.type_hint) and
            issubclass(self.type_hint, Enum)
        ):
            from xmodel.converters import EnumConverter
            _self.converter = EnumConverter()

        if self.related_type is Default:
            # By Default, we look at type-hint to see if it had a related-type or not...
            type_hint = self.type_hint
            related_type = type_hint
            if typing_inspect.get_origin(type_hint) is list:
                # Check to see if related_type is from typing
                # list and pull out first argument for List[]...
                related_type = typing_inspect.get_args(type_hint)[0]

            # Check if related type is a BaseModel or some other thing....
            from xmodel import BaseModel
            if inspect.isclass(related_type) and issubclass(related_type, BaseModel):
                _self.related_type = related_type

        # If we have a related type, and that related type has a usable id then we generate
        # a default related_field_name_for_id value if needed.
        if (
            self.related_field_name_for_id is Default
            and self.related_type
            and self.related_type.api.structure.has_id_field()
        ):
            _self.related_field_name_for_id = f'{self.name}_id'

        # Always base-line this field to None, we set a value for this if needed
        # in `xmodel.base.structure.BaseStructure._generate_fields`.
        # Because we need to cross-examine fields to set this correctly...
        # This field should never be set manually, it's always set automatically
        # as part of the BaseModel class setup process.
        # See `field_for_foreign_key_related_field` doc-comment for more details.
        _self.field_for_foreign_key_related_field = None

    def resolve_remaining_defaults_to_none(self):
        """ Called by `xmodel.base.structure.BaseStructure` after it calls
            `Field.resolve_defaults`.

            It used to be part of `Field.resolve_defaults`, but it was nicer to seperate
            it so that `Field` subclasses could call `super().resolve_defaults()` and
            still see what fields have defaults needing to be resolved, in case they wanted
            to do some special logic after the super/base classes default's were resolve but
            before they get set to None by Default.
        """
        # Resolve all other fields still at Default to None
        for attr_field in dataclasses.fields(self):
            name = attr_field.name
            child_value = getattr(self, name)
            if child_value is Default:
                setattr(self, name, None)

    def __post_init__(self):
        # Ensure we unwrap the type-hint from any optional.
        type = self.type_hint
        if type is Default:
            return
        unwraped = unwrap_optional_type(type)
        object.__setattr__(self, 'type_hint', unwraped)

    name: str = Default
    """ (Default: Parent, Name of field on BaseModel)

        This is set automatically after the BaseModel class associated with Field is constructed.
        This construction is lazy and happens the first time the
        `xmodel.base.model.BaseModel.api` property is accessed by something.
    """

    # See documentation under type_hint setter, this is only here to give type-hint to dataclass.
    # We have value set on it so IDE knows it's not required in __init__ and won't give warning.
    type_hint: Type = Default

    original_type_hint: Type = dataclasses.field(init=False, default=None, repr=False)
    """ This is set to whatever type_hint was originally set with, un-modified.
        `Field.type_hint` modifies what it's set with by filtering out None/Null types
        so the type is simpler.  It then sets `Field.nullable` to True/False if it's value is
        currently still at `xsentinels.default.Default` based on if NullType was seen or not as one
        of the types.

        In case something wants access to the original unmodified type, it's stored here.
    """

    _type_hint = Default  # No type-hint means data-class ignores it.

    # noinspection PyRedeclaration
    @property
    def type_hint(self) -> Type:
        """ (Default: Parent, The type-hint of the field)

            This is set automatically after the BaseModel class associated with Field is
            constructed. This construction is lazy and happens the first time the
            `xmodel.base.model.BaseModel.api` property is accessed by something.
        """
        return self._type_hint

    @type_hint.setter
    def type_hint(self, value: Type):
        if value is Field.type_hint:
            # This means we were not initialized with a value, so just continue to use Default.
            # When data-class is not given an attr-value in __init__, it does a GET on the class
            # and passes that to us here, so we just ignore it since it's the property setter it's
            # self.
            return
        self.original_type_hint = value
        result = unwrap_optional_type(value, return_saw_null=True)
        self._type_hint = result[0]
        if self.nullable is Default:
            self.nullable = bool(result[1])

    nullable: bool = Default
    """ (Default: Nullable in type-hint, ie: `some_var: Union[int, NullType]`; `False`)

        If `True`, we are a nullable field and can have `xmodel.null.Null` set on us.

        When left as Default, when the type-hint is set on us we will examine to see if it
        is a Union type with NullType in it.  If it does have that, this will be set to True
        otherwise to False.
    """

    read_only: bool = Default
    """ (Default: Parent, False)

        If `True`, we will NEVER send any values for this field to API.
    """

    exclude: bool = Default
    """ (Default: `Parent`, `False`)

        If `True`, by default will will try and exclude this field if the api supports doing this.
        This means that we will request API not send it to us by default.

        This could make the API return results in a more efficient manner if it does not have
        to output fields when most of the time we don't care about it's value.
    """

    default: Any = Default
    """ (Default: `Parent`, `None`)

        Default value for a field that we don't currently or did not previously retrieve a value
        for.

        If this default value is callable, like a function, type or an object that has a
        `__call__()` function defined on it; the system will call it without arguments to get
        a value back for the default value whenever a default value is needed for the model field.

        If you set a Non-Field value on a `xmodel.base.model.BaseModel`, it will be used as the
        value for this the `Field` object is created automatically (ie: if you don't set a
        `Field` object the the BaseModel class attribute/field, but something else, then it gets
        set here for you automatically).
    """

    post_filter: Optional[Filter] = Default
    """ (Default: `Parent`, `None`)

        Called when something set the field after it's been type verified and changed if needed.
        You can use this to alter the value if needed.

        An example would be lower-casing all strings set on property.

        You can also return None to indicate the value is unset, or Null to indicate null value.
        Be sure to only do this with fields that expect a Null value, since whatever the
        post_filter returns is used without verifying it's type against what the field expects.
    """

    converter: Optional[Converter] = Default
    """ (Default: `Parent` if set explicit by user;
        otherwise default converter for `Field.type_hint`)

        .. todo:: Implement this in BaseStructure/BaseApi.

        If set, this is used to convert value to/from api/json.
        You can see a real example of a converter at
        `xmodel.base.api.BaseApi.default_converters`.
    """

    # def __call__(self, fget_func: Callable[[], T]) -> T:
    #     if callable(fget_func):
    #         self.fget = fget_func
    #         return self
    #
    #     raise XModelError(
    #         f"Attempt to calling a Field ({self}) as a callable function without "
    #         f"providing a function as the first parameter, "
    #         f"I got this parameter instead: ({func})... "
    #         f"When a Field is used as a decorator (ie: `@Field()`), it needs to be "
    #         f"places right before a function. This function will be used as the fields "
    #         f"property getter function. "
    #     )

    @property
    def getter(self):
        """
        Like the built-in `@property` of python, except you can also place a Field and set
        any field-options you like, so it lets you make a field that will read/write to JSON
        out of a propety function.

        Basically, used to easily set a `fget` (getter) function on self via the standard
        property decorator syntax.

        See `Field.fget` for more details. But in summary, it works like normal python properties
        except that when a value is set on you, `BaseModel` will first convert it if needed
        before invoking your property setter (if you provide a property setter).

        If you don't provide a property setter, then you can only grab values from the property
        and it will be an error to attempt to set a value on one.

        >>> class MyModel(BaseModel):
        ...
        ...    # You can easily setup a field like normal, and then use getter/setter to setup
        ...    # the getter/setter for the field. Note: You MUST allocate a Field object of some
        ...    # sort your-self, otherwise there would be no object (yet) to use for the decorator.
        ...
        ...    my_field: str = Field()
        ...
        ...    @my_field.getter
        ...    def my_field(self):
        ...         return self._my_field_backing_store
        ...
        ...    # In either case, you can do the setter just like how normal properties work:
        ...    @my_field.setter
        ...    def my_field(self, value):
        ...        self._my_field_backing_store = value
        ...
        ...    _my_field_backing_store = None
        """

        def set_setter_on_field_with(func):
            self.fget = func
            return self

        return set_setter_on_field_with

    @property
    def setter(self):
        """
        Used to easily set a `set_func` setter function on self via the standard
        property decorator syntax, ie:

        >>> class MyModel(BaseModel):
        ...    _my_field_backing_store = None
        ...    my_field: str = Field()
        ...    def my_field(self):
        ...         return self._my_field_backing_store
        ...    @my_field.setter
        ...    def my_field(self, value):
        ...        self._my_field_backing_store = value

        """

        def set_setter_on_field_with(func):
            self.fset = func
            return self

        return set_setter_on_field_with

    fget: 'Optional[Callable[[M], Any]]' = Default
    """ (Default: `Parent`; otherwise `None`)

        Function to use to get the value of a property, instead of getting it directly from object,
        BaseModel will use this.

        Callable Args:

        1. The model (ie: `self`)
        2. Is associated Field object
    """

    fset: 'Optional[Callable[[BaseModel, Any], None]]' = Default
    """ (Default: `Parent`; otherwise `None`)

        Function to use to set the value of a property, instead of setting it directly on object,
        BaseModel will use this.

        Callable Args:

        1. The model (ie: `self`)
        2. Is associated Field object
        3. Finally, the value to set.

        The value will be passed into function AFTER it's been verified, and converted if needed.
        If you need to adjust how the converter aspect works, look at `Field.converter`.

        Also, if someone attempts get the value, and the value is None...
        And if there is a `Field.default` set, the BaseModel needs to create a default value
        and return it.

        The created value will be set onto object before the getter returns.
        because no value is there... then it will be created and this function will be called.
    """

    include_with_fields: Set[str] = Default
    """
    (Default: `Parent`, `[]`)

    List of field names that, if they are included in the JSON, this one should too;
    even if our value has not changed.

    Defaults to blank set (ie: nothing).

    .. important:: Can use `include_with_fields` only when `Field.name` and `Field.json_path`
        are the same value (ie: have not customized `field.json_path` to be different.
        It's something that we have chosen not  to support to keep the implementation of this
        simpler. It's something that could be support in the future if the need ever arises.

    .. todo:: in the future, consider also allowing to pass in field-object,
        (which we would convert to the fields name, for the user as a convenience).
    """

    json_path: str = Default
    """
    (Default: `Field.name` at time of BaseModel-class construction [when defaults are resolved])

    Key/name used when mapping field to/from json/api request.

    If you include a `.`, it will go one level deeper in the JSON. That way you can
    map from/to a sub-property....

    Defaults to the Field.name.
    """

    json_path_separator: str = Default
    """ (Default: `Parent`, ".")

        Path separator to use in json_path.  Defaults to a period (".").
    """

    # todo: Would like to rename this to just `repr`, just like in dataclasses.
    include_in_repr: bool = Default
    """ (Default: `Parent`, `False`)

        .. todo:: Would like to rename this to just `repr`, just like in dataclasses.

        Used in `xmodel.base.api.BaseApi.list_of_attrs_to_repr` to return a list of field-names
        that `xmodel.base.model.BaseModel.__repr__` uses to determine if the field should be
        included in the string it returns.

        This string is what get's used when the `xmodel.base.model.BaseModel` gets converted to
        a string, such as when logging the object out or printing it via the debugger.
    """

    related_type: 'Optional[Type[BaseModel]]' = Default
    """
    (Default: `Parent`, `Field.type_hint` if subclass of `xmodel.base.model.BaseModel`, None)

    If not None, this is a type that is as subclass of `xmodel.base.model.BaseModel`.

    If `xsentinels.default.Default`, and we have not Parent field,
    we grab this from type-hints, examples:

    >>> from xmodel.base.model. import BaseModel
    >>> class MyModel(BaseModel):
    ...     # Needs 'my_attr_id' via JSON, will do lazy lookup:
    ...     my_attr: SomeOtherModel
    ...
    ...     # 'List' Not fully supported yet:
    ...     my_attr_list: List[SomeOtherModel]
    ...
    ...     # This works (for basic types, inside list/set)
    ...     # BaseModel-types inside list will come in future.
    ...     my_attr_list: Set[int]

    .. todo:: Right now we only support a one-to-one. In the future, we will support
        one-to-many via the generic `List[SomeModel]` type-hint syntax.

    Generally, when you ask for the value of a field with this set you get back an Instance
    of the type set into this field (as a value in this field).

    By convention, the primary-key value for this is the field name from the api when a
    "_id" appended to the end of the name; ie: "`Field.json_key`_id"

    .. todo:: At some point, I would like to make the `_id` customizable, perhaps with
        a `Field.related_type_id_key` or some such....
    """

    related_field_name_for_id: Optional[str] = Default
    """
    .. important:: Not currently used, will be used when one-to-many support is fully
        added. However, this should still be populated and return correct information.


    (Default: `Parent`;
              If `Field.related_type` is set to something with
              `xmodel.base.structure.BaseStructure.have_usable_id` is True,
              then `_id` is appended on end of`Field.json_path`.

              If the related_field uses no id field, then the object should be a sub-object
              and fully embedded into tje JSON instead of only embedding it's id value.
    )

    When getting Default value (if parent does not have this set) we use `self.json_path` and
    append an `_id` to the end. You can override this if you need to via the usual way:
    `Field(related_field_name_for_id='...xyz...')`.

    When resolve the Default value, we will only do so if the `Field.related_type` has it's
    `api.structure.have_usable_id` set to True (meaning that the related-type uses an `id` field).

    If a related type does not use an `id` field, by default the related type will be an
    embedded object (ie: fully embedded into the produced JSON, as needed).

    .. note:: The below statement is for when one_to_many is supported, someday...

    ~~if related_is_one_to_many is False, otherwise we find the a one-to-one link back to us
    from related_type, and use that field's `Field.json_path`.~~
    """

    field_for_foreign_key_related_field: 'Optional[Field]' = dataclasses.field(
        default=Default, init=False
    )
    """
    .. important:: Not currently used, will be used when one-to-many support is fully
        added. However, this should still be populated and return correct information.


    (Default: If another field on Model has a `Field.related_field_name_for_id` that is equal
              to self.name, then we set this attribute with that other field object.

              Otherwise this is None
    )


    .. important:: this is always automatically generated, and should not be set manually.
        Keep reading for details.

    By Default, if this field represents the value of an 'id' or key, for a one-to-one related
    foreign-key field  then this will be set to that related field.

    This is the other field on the same Model that is the related object for this key field.
    In other-words, the field this points to the field that represents the object for the value
    of this id/key field IF the related field is a one-to-one relationship.

    This can't be set via the `__init__` method for Field, it's always set when
    the `xmodel.base.structure.BaseStructure` generates fields via
    it's `_generate_fields` method.
    """

    @property
    def is_foreign_key(self):
        """
            .. important:: Not currently used, will be used when one-to-many support is fully
                added. However, this should still be populated and return correct information.

            If we have a `field_for_foreign_key_related_field`, then we are a foreign key field.

            This checks `Field.field_for_foreign_key_related_field` and returns True or False
            depending on if that has a field value or not.

            This property just makes it clear and documents on how one knows if we are a
            foreign key field or not.
        """
        return bool(self.field_for_foreign_key_related_field)

    related_to_many: bool = Default
    """
    .. important:: Not currently used, will be used when one-to-many support is fully added.
        Right now this will by Default always be `None`.

    (Default: `Parent`, If type-hint is `List[Model]` and other model has a one-to-one type-hint
    back to myself)

    If True, this field is a one-to-many relationship with another model.

    We use `Field.related_field_name_for_id` a the key for a query on the relationship via
    `BaseApi.get`. We will query `Field.related_type`'s `api`, call get on it and use our model's
    `xmodel.base.model.BaseModel.id` as the query value.

    We will do our best to weak-cache the result, if weak-cache is currently enabled;
    see `xmodel.weak_cache_pool.WeakCachePool` for weak-cache details.
    """

    model: 'BaseModel' = Default

    @property
    def related_field(self) -> 'Field':
        """ Set to the Field for the `Field.related_field_name_for_id`. """
        api = self.related_type.api if self.related_to_many else self.model.api
        return api.structure.get_field(self.related_field_name_for_id)

