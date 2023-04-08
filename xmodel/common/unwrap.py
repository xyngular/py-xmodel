import typing_inspect
from typing import Type, Union, Tuple
from xsentinels.null import NullType


def unwrap_optional_type(
        type_to_unwrap: Type,
        *,
        return_saw_null: bool = False
) -> Union[Type, Tuple[Type, bool]]:
    """
    Returns the first non-Null or non-None type inside the optional/Union type.
    If the type passed in is not an optional/union type, then return type_to_inspect
    unaltered.

    Args:
        type_to_unwrap: Type to inspect and unwrap the optionality/union from.
        return_saw_null: If this is True (default is False), return a Tuple with the Type
            and then a `bool` based on if we saw a `xsentinels.null.NullType` or not.
    Returns:
        Type: if `return_saw_null` is False (default), just return the Type.
        Tuple[Type, bool]: if `return_saw_null` is True; return Type + bool with if we saw
            `xsentinels.null.NullType` or not.
    """
    if not typing_inspect.is_union_type(type_to_unwrap):
        return (type_to_unwrap, False) if return_saw_null else type_to_unwrap

    hint_union_sub_types = typing_inspect.get_args(type_to_unwrap)
    saw_null = False
    types = []
    for sub_type in hint_union_sub_types:
        if sub_type is NullType:
            saw_null = True
        if sub_type not in [NullType, type(None)]:
            types.append(sub_type)

    if len(types) == 1:
        unwrapped_type = types[0]
    else:
        # Construct final Union type with the None/Null filtered out.
        unwrapped_type = Union[tuple(types)]

    if return_saw_null:
        return unwrapped_type, saw_null

    return unwrapped_type
