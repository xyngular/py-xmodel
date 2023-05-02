from typing import TypeVar, Generic, TYPE_CHECKING

from xmodel.base.model import BaseModel, Self
from xsentinels.default import Default


if TYPE_CHECKING:
    from xmodel.remote.api import RemoteApi

# Can't forward-ref the bound type here (ie: 'RemoteModel'), so put BaseModel in at least...
M = TypeVar("M", bound=BaseModel)


def _lazy_load_types(cls):
    """
    Lazy import BaseApi into module, helps resolve BaseApi forward-refs;
    ie: `api: "RemoteApi[T]"`

    We need to resolve these forward-refs due to use of `get_type_hints()` in
    BaseModel.__init_subclass__; so get_type_hints can find the correct type for the
    forward-ref string in out `RemoteModel` class below.

    Sets it in such a way so IDE's such as pycharm don't get confused + pydoc3
    can still find it and use the type forward-reference.

    See `xmodel.base.model.BaseModel.__init_subclass__` for more details.
    """
    if 'BaseApi' not in globals():
        from xmodel.remote.api import RemoteApi
        globals()['RemoteApi'] = RemoteApi


class RemoteModel(BaseModel, lazy_loader=_lazy_load_types):
    api: 'RemoteApi[Self]' = None

    # todo: I think we will want to make the type on the `id` field a TypeVar of some sort,
    #       sometimes we will want to use a `str` for it's type [etc].
    id: int = None
    """ Primary identifier for object, used with API endpoint. """

    def __init__(self, *args, id=Default, **initial_values):

        super().__init__(*args, **initial_values)

        if id is not Default:
            self.id = id

    def __repr__(self):
        message = super().__repr__().split("(")[1][:-1]

        response_state = self.api.response_state
        response_state_attrs = []

        if response_state.had_error is not None:
            response_state_attrs.append('had_error')

        if response_state.response_code is not None and response_state.response_code != 200:
            response_state_attrs.append('response_code')

        if response_state.errors is not None:
            response_state_attrs.append('errors')

        for attr in response_state_attrs:
            message += f', __{attr}={getattr(response_state, attr, None)}'

        return f"{self.__class__.__name__}({message})"
