# *********************************************************************************************
# It's VERY important that only basic types go in here, no real logic should be in this module.
#
# This file is meant to contain the very basic types that are used throughout the entire module.

# It's very common for other parts of the SDK to do `from .types import *`, to get all of the basic
# types.  I put more stuff from typing that is not strictly needed here; that way those modules
# will get these basic types just as easily.
from typing import TypeVar, Dict, Any, Sequence
from enum import Enum, auto as EnumAuto  # noqa

# Generic type-var, can be used as a place-holder for anything.

JsonDict = Dict[str, Any]
"""
`Dict[str, Any]`: This represents a JSON type of dict, with string keys and any value.
"""

# todo: Figure out if we can accept a dict instead [union?]
FieldNames = Sequence[str]
""" `Sequence[str]`: Represents a list of field names. """
