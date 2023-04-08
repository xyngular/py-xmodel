import ciso8601

from xmodel.base.fields import Converter, Field
import datetime as dt
from typing import Union, TYPE_CHECKING, Type, TypeVar, Generic, Dict, Any
from xsentinels.null import Null, NullType, Nullable
from xmodel.errors import XModelError
from distutils.util import strtobool
from decimal import Decimal

_to_obj_directions = {Converter.Direction.from_json, Converter.Direction.to_model}
Direction = Converter.Direction

T = TypeVar("T")

if TYPE_CHECKING:
    # Allows IDE to get type reference without a circular import issue.
    from xmodel import BaseApi


def to_datetime(value):
    # Should pretty much always be a string, so check for that first.
    if isinstance(value, str):
        return ciso8601.parse_datetime(value)

    if isinstance(value, dt.datetime):
        return value

    if isinstance(value, dt.date):
        return dt.datetime(value.year, value.month, value.day, tzinfo=dt.timezone.utc)

    raise ValueError(
        f"Tried to convert a datetime from unsupported BaseSettings value ({value})."
    )


def convert_json_int(
        api: "BaseApi",
        direction: Direction,
        field: Field,
        value: Union[dt.date, str, None]
) -> int:
    return int(value)


class EnumConverter(Converter):
    def from_json(self, api: 'BaseApi', field: 'Field', value: Any):
        # todo: lists of enums, someday...
        if value in (Null, None):
            return value
        if isinstance(value, field.type_hint):
            return value
        return field.type_hint(value)

    def to_json(self, api: 'BaseApi', field: 'Field', value: Any):
        if value in (Null, None):
            return value
        return value.value

    def to_model(self, *args):
        return self.from_json(*args)


class ConvertBasicType(Converter, Generic[T]):
    """
    Implements the `xmodel.fields.Converter` converter field interface for a basic type.

    Whatever type you pass into my init method will be called when a type needs to be converted.

    As an example, say we had `ConvertBasicType(basic_type=int)` as a converter we are using.
    When this converter is passed a string to conver, such as `"1"` the `ConvertBasicType`
    object would just do this for you:

    >>> int("1")

    If the type is exactly the same, no conversion happens and the value is passed back unchanged.
    ie:

    >>> value: str
    >>> self: ConvertBasicType[str]
    >>>
    >>> if type(value) is self.basic_type:
    ...    return value
    """
    basic_type: Type[T]

    def __init__(self, basic_type: Type[T]):
        """
        Args:
            basic_type: Type to auto-convert to, in a basic fashion.
                See `ConvertBasicType` for more details.
        """
        self.basic_type = basic_type

    def convert_basic_value(self, value) -> Nullable[T]:
        if value is Null:
            return Null

        basic_type = self.basic_type

        if type(value) is basic_type:
            return value
        return basic_type(value)

    def __call__(
            self,
            api: "BaseApi",
            direction: Direction,
            field: Field,
            value: Union[dt.date, str, None]
    ) -> T:
        if value in (None, Null) and direction == Direction.from_json and field.nullable:
            return Null

        if value is None:
            return None

        if isinstance(value, list):
            return [self.convert_basic_value(x) for x in value]

        return self.convert_basic_value(value)


class ConvertBasicBool(ConvertBasicType[bool]):
    def convert_basic_value(self, value) -> T:
        if isinstance(value, str):
            return strtobool(value)
        return super().convert_basic_value(value)

    def __init__(self):
        super().__init__(basic_type=bool)


class ConvertBasicInt(ConvertBasicType[int]):
    def __init__(self):
        super().__init__(basic_type=int)

    def convert_basic_value(self, value) -> T:
        # Convert a blank-string into a zero-int.
        if isinstance(value, str) and not value:
            return 0
        # Otherwise do the normal thing...
        return super().convert_basic_value(value)


def convert_json_date(
        api: "BaseApi",
        direction: Converter.Direction,
        field: Field,
        value: Union[dt.date, str, None]
) -> Union[dt.date, str, None]:
    """ Default converter method used for converting date to/from json.
        See `xmodel.fields.Converter` for more details.
    """
    if value in (None, Null) and direction == Direction.from_json and field.nullable:
        return Null

    if value is None or value is Null:
        return value

    if direction in _to_obj_directions:
        return dt.datetime.strptime(value, '%Y-%m-%d').date()

    if isinstance(value, dt.datetime):
        value = value.date()

    return value.isoformat()


def convert_json_datetime(
        api: "BaseApi",
        direction: Direction,
        field: Field,
        value: Union[dt.datetime, str, None, NullType],
        as_time_zone: dt.datetime.tzinfo = dt.timezone.utc
) -> Union[dt.datetime, str, None]:
    """ Default converter method used for converting datetime to/from json.
        See `xmodel.fields.Converter` for more details.
    """
    if value in (None, Null) and direction == Direction.from_json and field.nullable:
        return Null

    if value is None or value is Null:
        return value

    if direction in _to_obj_directions:
        # Should pretty much always be a string, so check for that first.
        if isinstance(value, str):
            return to_datetime(value)

        if isinstance(value, dt.datetime):
            return value

        if isinstance(value, dt.date):
            return to_datetime(value)

        raise XModelError(
            f"Tried to convert a datetime from-json from an unknown value ({value})."
        )

    if isinstance(value, dt.date) and not isinstance(value, dt.datetime):
        value = to_datetime(value)

    if isinstance(value, str):
        if not value:
            return Null
        value = to_datetime(value)

    if not isinstance(value, dt.datetime):
        raise XModelError(f"Tried to convert to json a none date/datetime value ({value}).")

    # Always use UTC format.
    return value.astimezone(as_time_zone).isoformat()


def convert_decimal(
    api,
    direction: Direction,
    field: Field,
    value: Any,
):
    if value is None or value is Null:
        return value

    if direction is Direction.to_json:
        if isinstance(value, Decimal):
            # Prevents using exponents, ie: '1.234E-5'
            return "{0:f}".format(value)
        # If we don't have a decimal, try our best to get string value.
        return str(value)

    if direction not in (Direction.to_model, Direction.from_json):
        # We don't know the direction (new direct?)
        raise XModelError(
            f"Unknown direction ({direction}), can't convert value ({value}); "
            f"is this a new direction I need to handle?"
        )

    # Going into model, return a Decimal.
    # Decimal class
    if isinstance(value, float):
        # If we don't convert to string first, we could end up with an
        # undesirable binaryFloat --> Decimal conversion.
        # Converting it to a string first seems to preserve the original non-binary meaning better.
        value = str(value)

    return Decimal(value)


DEFAULT_CONVERTERS: Dict[Type, Converter] = {
    Decimal: convert_decimal,
    dt.date: convert_json_date,
    dt.datetime: convert_json_datetime,
    int: ConvertBasicInt(),
    float: ConvertBasicType(basic_type=float),
    str: ConvertBasicType(basic_type=str),
    bool: ConvertBasicBool(),
}
