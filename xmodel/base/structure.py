"""
See `BaseStructure` for more details; This lets you discover/kee-track/find structural details
of a `xmodel.base.model.BaseModel.api`.
"""

from xmodel.common.types import JsonDict
from xmodel.errors import XModelError
from xmodel.base.fields import Field
from xsentinels.default import Default
from typing import TypeVar, Optional, Dict, List, Type, Any, Generic
from typing import TYPE_CHECKING
import typing_inspect
import inspect
from types import MappingProxyType
from typing import Mapping

F = TypeVar("F", bound=Field)

supported_basic_types = {str, int, JsonDict, bool, float, list, dict}

if TYPE_CHECKING:
    from xmodel import BaseModel


class BaseStructure(Generic[F]):

    """
    BaseStructure class is meant to keep track of things that apply for all
    `xmodel.base.model.BaseModel`'s at the class-level.

    You can use `BaseStructure.fields` to get all fields for a particular
    `xmodel.base.model.BaseModel`
    as an example of the sort of information on the `BaseStructure` object.

    BaseStructure is lazily configured for a particular BaseModel the first time something
    attempts to get `xmodel.base.model.BaseModel.api` off the particular BaseModel subclass.

    You can get it via first getting api attribute for BaseModel via
    `xmodel.base.model.BaseModel.api` and then getting the structure attribute on that via
    `xmodel.base.api.BaseApi.structure`.

    Example getting the structure object for the Account model/api:

    >>> from some_lib.account import Account
    >>> structure = Account.api.structure
    """

    def __init__(
            self,
            *,
            parent: Optional['BaseStructure'],
            field_type: Type[F]
    ):
        super().__init__()

        # Set specific ones so I have my own 'instance' of them.
        self._name_to_type_hint_map = {}
        self._get_fields_cache = None

        # Copy all my attributes over from parent, for use as 'default' values.
        if parent:
            self.__dict__.update(parent.__dict__)
            # noinspection PyProtectedMember
            # This parent is my own type/class, so I am fine accessing it's private member.
            self._name_to_type_hint_map = parent._name_to_type_hint_map.copy()

        self._get_fields_cache = None
        self.field_type = field_type
        self.internal_shared_api_values = {}

    def configure_for_model_type(
            self,
            *,  # <-- means we don't support positional arguments
            model_type: Type['BaseModel'],
            type_hints: Dict[str, Any],
    ):
        """
        This EXPECTS to have passed-in the type-hints for my `BaseStructure.;
        see code inside `xmodel.base.model.BaseModel.__init_subclass__` for more details.
        There is no need to get the type-hints twice [it can be a bit expensive, trying to
        limit how may times I grab them]....

        See `xmodel.base.model.BaseModel` for more details on how Models work...
        This describes the options you
        can pass into a `xmodel.base.model.BaseModel` subclass at class-construction time.
        It allows you to customize how the Model class will work.

        This method will remember the options passed to it, but won't finish constructing the class
        until someone asks for it's `xmodel.base.model.BaseModel.api` attribute for the first
        time. This allows you
        to dynamically add more Field classes if needed. It also makes things import faster as
        we won't have to fully setup the class unless something tries to use it.

        Args:
            model_type (Type[xmodel.base.model.BaseModel]): The model we are associated with,
                this is what we are configuring ourselves against.
            type_hints (Dict[str, Any]): List of typehints via Python's `get_type_hints` method;
                Be aware that `get_type_hints` will try and resolve all type-hints, including
                ones that are forward references. Make sure these types are available at
                the module-level by the time `get_type_hints` runs.
        """
        # Prep model class, remove any class Field objects...
        # These objects have been "moved" into me via `self.fields`.
        self._name_to_type_hint_map = type_hints
        self.model_cls = model_type
        for field_obj in self.fields:
            field_name = field_obj.name

            # The default values are inside `field_obj.default` now.
            # We delete the class-vars, so that `__getattr__` is called when someone attempts
            # to grab a value from a BaseModel for an attribute that does not directly exist
            # on the BaseModel subclass so we can do our normal field_obj.default resolution.
            # If the class keeps the value, it prevents `__getattr__` from being called for
            # attributes that don't exist directly on the model instance/object;
            # Python will instead grab and return the value set on the class for that attribute.
            #
            # todo/thoughts/brain-storm:
            #    Consider just using __getattribute__ for BaseModel instead of __getattr_...
            #    It's slightly slower but then I could have more flexablity around this...
            #    Thinking of returning the associated field-object if you do
            #    `BaseModelSubClass.some_attr_field` for various purposes....
            #    Using `__getattribute__` would allow for this....
            #    just something I have been thinking about...
            #    For example: you could use that field object as a query-key instead of a string
            #    with the field-name...
            #    might be nicer, and get auto-completion that way... not sure, thinking about it.
            #
            if field_name in self.model_cls.__dict__:
                delattr(self.model_cls, field_name)

    # --------------------------------------
    # --------- Environmental Properties ---------

    model_cls: "Type[BaseModel]"
    """
    The model's class we are defining the structure for.
    This is typed as some sort of `xmodel.base.model.BaseModel`
    .
    This is NOT generically typed anymore, to get much better generically typed
    version you should use `xmodel.base.api.BaseApi.model_type` to get the BaseModel outside
    of the `xmodel.structure` module.
    Using that will give the IDE the correctly typed BaseModel class!
     """

    # --------------------------------------
    # --------- General Properties ---------
    #
    # Most of these will be set inside __init_subclass__() via associated BaseModel Class.

    field_type: Type[F]
    """
    Field type that this structure will use when auto-generating `xmodel.fields.Field`'s.
    User defined Fields on a model-class will keep whatever type the user used.
    When `xmodel.base.model.BaseModel` class is constructed, and the `BaseStructure` is
    created, we will check to ensure all user-defined fields inherit from this field_type.

    That way you can assume any fields you get off this structure object inherit from
    field_type.
    """

    internal_shared_api_values: Dict[Any, Any] = None
    """
    A place an `xmodel.base.api.BaseApi` object can use to share values BaseModel-class wide
    (ie: for all BaseModel's of a specific type).

    This should NOT be used outside of the BaseApi class.
    For example, ``xmodel.base.api.BaseApi.client` stores it's object lazily here.
    Users outside of BaseApi class should simply ask it for the client and not try
    to go behind it's back and get it here.

    Code/Users outside of `xmodel.base.api.BaseApi` and it's subclasses can't assume
    anything about what's in this dictionary.  This exists for pure-convenience of the
    `xmodel.base.api.BaseApi` class.
    """

    _name_to_type_hint_map: Dict[str, Any]
    """
        .. deprecated:: v0.2.33 Use `BaseStructure.fields` instead to get a list of
            the real fields to use. And `xmodel.fields.Field.type_hint` to get the type-hint
            [don't get it here, keeping this temporary for backwards compatibility].

        A map of  attribute-name to type-hint type.

        .. important:: This WILL NOT take into account field-names where the `Field.name` is
            different then the name of the field on BaseModel the type-hint was assigned to.
    """

    _get_fields_cache: Dict[str, F] = None

    @property
    def have_api_endpoint(self) -> bool:
        """ Right now, a ready-only property that tells you if this BaseModel has an API endpoint.
            That's determined right now via seeing if `BaseStructure.has_id_field_set()` is True.
        """
        if not self.has_id_field():
            return False
        else:
            return True

    def __copy__(self):
        obj = type(self)(parent=self, field_type=self.field_type)
        obj.__dict__.update(self.__dict__)
        obj._name_to_type_hint_map = self._name_to_type_hint_map.copy()
        obj._get_fields_cache = None
        return obj

    def field_exists(self, name: str) -> bool:
        """ Return `True` if the field with `name` exists on the model, otherwise `False`. """
        return name in self.field_map

    def has_id_field(self):
        """ Defaults to False, returns True for RemoteStructure,
            What this property is really saying is if you can do a foreign-key to the related
            object/model.

            It may be better at some point in the long-run to rename this field to more indicate
            that; perhaps the next time we have a breaking-change we need to do for xmodel.

            For now, we are leaving the name along and hard-coding this to
            return False in BaseStructure, and to return True in RemoteStructure.
        """
        return False

    def get_field(self, name: str) -> Optional[F]:
        """
        Args:
            name (str): Field name to query on.
        Returns:
            xmodel.fields.Field: If field object exists with `name`.

            None: If not field with `name` exists
        """
        if name is None:
            return None
        return self.field_map.get(name)

    @property
    def fields(self) -> List[F]:
        """ Returns:
                List[xmodel.fields.Field]: list of field objects.
        """
        return list(self.field_map.values())

    @property
    def field_map(self) -> Mapping[str, F]:
        """

        Returns:
           Dict[str, xmodel.fields.Field]: Map of `xmodel.fields.Field.name` to
                `xmodel.fields.Field` objects.
        """
        cached_content = self._get_fields_cache
        if cached_content is not None:
            # Mapping proxy is a read-only view of the passed in dict.
            # This will LIVE update the mapping if underlying dict changed.
            return MappingProxyType(cached_content)

        generated_fields = self._generate_fields()
        self._get_fields_cache = generated_fields
        return MappingProxyType(generated_fields)

    def excluded_field_map(self) -> Dict[str, F]:
        """
        Returns:
            Dict[str, xmodel.fields.Field]: Mapping of `xmodel.fields.Field.name` to
                field objects that are excluded (`xmodel.fields.Field.exclude` == `True`).
        """
        return {f.name: f for f in self.fields if f.exclude}

    def _generate_fields(self) -> Dict[str, F]:
        """ Goes though object and grabs/generated Field objects and caches them in self.
            Gives back the definitive list of Field objects.

            For now keeping this private, but may open it up in the future if sub-classes
            need to customize how fields are generated.
        """
        full_field_map = {}

        default_field_type: Type[Field] = self.field_type
        type_hint_map = self._name_to_type_hint_map
        model_cls = self.model_cls

        # todo: Figure out how to put this into/consolidate into
        #  `xmodel.base.api.BaseApi`; and simplify stuff!!!
        default_converters = getattr(self.model_cls.api, 'default_converters')

        # todo:  default_con ^^^^ make sure we are using it!!!!

        # Lazy-import BaseModel, we need to check to see if we have a sub-class or not...
        from xmodel import BaseModel

        # This will be a collection of any Fields that exist on the parent(s), merged together...
        base_fields: Dict[str, Field] = {}

        # go though parent and find any Field objects, grab latest version
        # which is the one closest to child on a per-field basis...
        # we exclude it's self [the model we are currently working with].
        for base in reversed(model_cls.__mro__[1:]):
            base: Type[BaseModel]
            if not inspect.isclass(base):
                continue
            if not issubclass(base, BaseModel):
                continue
            if not base.api:
                # `base` is likely xmodel.base.model.BaseModel; and that has no API allocated
                # to it
                # at the moment [mostly because the __init_subclasses is only executed on sub's].
                # todo: BaseModel is an abstract class... do we really need structure/fields on it?
                continue
            # todo:  ensure we later on use these and make a new field if needed...
            base_fields.update(base.api.structure.field_map)

        for name, type_hint in type_hint_map.items():
            # Ignore the 'api' attribute, it's special.
            if name == 'api':
                continue

            # Ignore anything the starts with '_'.
            if name.startswith("_"):
                continue

            # todo:
            #   1. Get Parent Field's, merge values.
            #   2. Map all type's and if not map then raise error.

            # noinspection PyArgumentList
            field_obj: Field
            field_value: Field = getattr(model_cls, name, Default)
            if isinstance(field_value, Field):
                field_obj = field_value
                field_value = Default
            elif field_value is not Default:
                if not inspect.isclass(field_value) and isinstance(field_value, property):
                    field_obj = default_field_type(fget=field_value.fget, fset=field_value.fset)
                else:
                    # noinspection PyArgumentList
                    field_obj = default_field_type(default=field_value)
            else:
                # noinspection PyArgumentList
                field_obj = default_field_type()

            # Name can be overridden, we want to use it to lookup parent field name....
            if field_obj.name:
                name = field_obj.name

            field_obj.resolve_defaults(
                name=name,
                type_hint=type_hint_map.get(name, None),
                default_converter_map=default_converters,
                parent_field=base_fields.get(name)
            )

            # Ensure all fields that still have `Default` as their value are resolved to None.
            field_obj.resolve_remaining_defaults_to_none()

            # field-object will unwrap the type-hint for us.
            type_hint = field_obj.type_hint

            # Name can be overridden, we want to use whatever it says we should be using.
            name = field_obj.name
            full_field_map[field_obj.name] = field_obj

            # If we have a converter, we can assume that will take care of things correctly
            # for whatever type we have.  If we don't have a converter, we only support specific
            # types; We check here for type-compatibility.
            from xmodel import BaseModel
            if (
                not field_obj.converter and
                type_hint not in supported_basic_types and
                (not inspect.isclass(type_hint) or not issubclass(type_hint, BaseModel)) and
                typing_inspect.get_origin(type_hint) not in (list, set)
            ):
                raise XModelError(
                    f"Unsupported type ({type_hint}) with field-name ({name}) "
                    f"for model-class ({model_cls}) in field-obj ({field_obj})."
                )

            if (
                field_obj.json_path and
                field_obj.json_path != field_obj.name and
                field_obj.related_type
            ):
                XModelError(
                    "Right now obj-relationships can't use the 'json_path' option "
                    "while at the same time being obj-relationships. Must use basic field "
                    "with api_path. "

                    # Copy/Paste from `BaseApi.json`:
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

        # todo: Provide a 'remove' option in the Field config class.
        if 'id' not in full_field_map:

            # Go though and populate the `Field.field_for_foreign_key_related_field` as needed...
            for k, f in full_field_map.items():
                # If there is a relate field name, and we have a field defined for it...
                # Set it's field_for_foreign_key_related_field so the correct field...
                # Otherwise generate a field object for this key-field.
                #
                # FYI: The `resolve_defaults` call above will always set
                #      field_for_foreign_key_related_field to None.
                #      We then set it to something here if needed.
                if f.related_field_name_for_id:
                    related_field = full_field_map.get(f.related_field_name_for_id)
                    if related_field:
                        related_field.field_for_foreign_key_related_field = f

        return full_field_map

    def id_cache_key(self, _id):
        """ Returns a proper key to use for `xmodel.base.client.BaseClient.cache_get`
            and other caching methods for id-based lookup of an object.
        """
        if type(_id) is dict:
            # todo: Put module name in this key.
            key = f"{self.model_cls.__name__}"
            try:
                sorted_keys = sorted(_id.keys())
            except TypeError:
                sorted_keys = _id.keys()
            for key_name in sorted_keys:
                key += f"-{key_name}-{_id[key_name]}"
            return key
        else:
            return f"{self.model_cls.__name__}-id-{_id}"

    # todo: Get rid of this [only used by Dynamo right now]. Need to use Field instead...
    def get_unwraped_typehint(self, field_name: str):
        """
        This is now done for you on `xmodel.fields.Field.type_hint`, so you can just grab it
        directly your self now.

        Gets typehint for field_name and calls `xmodel.types.unwrap_optional_type`
        on it to try and get the plain type-hint as best as we can.
        """
        field = self.get_field(field_name)
        if field is None:
            return None

        return field.type_hint

    def is_field_a_child(self, child_field_name, *, and_has_id=False):
        """
        True if the field is a child, otherwise False.  Will still return `False` if
        `and_has_id` argument is `True` and the related type is configured to not use id via class
        argument `has_id_field=False` (see `BaseStructure.configure_for_model_type` for more
        details on class arguments).

        Won't raise an exception if field does not exist.

        Args:
            child_field_name (str): Name of field to check.
            and_has_id (bool): If True, then return False if related type is not configured to
                use id.
        Returns:
            bool: `True` if this field is a child field, otherwise `False`.
        """
        field = self.get_field(child_field_name)
        if not field:
            return False

        related_type = field.related_type
        if not related_type:
            return False

        related_structure = related_type.api.structure
        if and_has_id and not related_structure.has_id_field():
            return False

        return True

    @property
    def endpoint_description(self):
        """ Gives some sort of basic descriptive string that contains the path/table-name/etc
            that basically indicates the api endpoint being used.

            This is meant for logging and other human readability/debugging purposes.
            Feel free to change the string to whatever is most useful to know.

            I expect this to be overridden by the concrete implementation, see examples here:

            - `xmodel.rest.RestStructure.endpoint_description`
            - `xmodel.dynamo.DynStructure.endpoint_description`
        """
        return "?"
