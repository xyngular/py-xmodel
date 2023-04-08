from typing import TYPE_CHECKING, TypeVar

M = TypeVar("M")

# noinspection PyUnreachableCode
if TYPE_CHECKING:
    # We only need this for the type-hint, and nothing else.
    # Use forward-refs 'BaseApi' [with the quotes].
    # Gives code from outside this module hints about some of the types.
    from .state import PrivateApiState
    from xmodel import BaseApi


def get_api_state(api: "BaseApi[M]") -> "PrivateApiState[M]":
    """ PRIVATE - Allows things in this module to get the private structure object
        via an BaseApi object and not generate any warnings [we are making 'Friends' here!].

        We here are in a private sub-module of the base module,
        and it is ok to use this private module anywhere under the `xmodel` module.
    """
    # noinspection PyProtectedMember
    return api._api_state
