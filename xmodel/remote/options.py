from xmodel.common.utils import SetUnsetValues
from typing import TypeVar, Generic, TYPE_CHECKING, Dict, Type
from xmodel.remote.response_state import ErrorHandler
from .model import RemoteModel
from xinject import Dependency

if TYPE_CHECKING:
    from .api import RemoteApi


T = TypeVar("T")


# todo: I think I want to have an ability to more directly use this, and simplify this a bit...
#  I look at our I did the `Field` object, that was a better way in part for what this needs....
#  See RestClient._get_objects for a place where I need to temporary alter options
#  to disable `auto_get_child_objects`.
#  I don't have time to figure it right now, but hope I will soon....
class ApiOptions(Generic[T], SetUnsetValues):
    cache_by_id: bool = False
    """ If value is:

        - `True`: Overrides what model class was constructed with and cache's by id.
        - `False`: Overrides what model class was constructed with and does not cache by id.
    """

    error_handler: ErrorHandler[T] = None
    """
    The system first consults the objects 'obj.api.response_state.error_handler'
    (`xmodel.remote.response_state.ResponseState.error_handler`).

    If that's `None` it next checks the ApiOptions at `ObjType.api.options` for error_handler.
    If it's not set there, then checks the ObjType.api.options in the each parent XContext.
    Finally, we check the options passed in when ObjType class was defined.

    If this is still None, then the standard error handler will happen.

    The first error handler that returns True

    Check `base.client.RestClient` for other error handling options I have now, and will add in
    the future. Thinking about adding something there to 'catch' all the errors that happen
    from any BaseModel/Type.
    """

    auto_get_child_objects: bool = False
    """ When retrieving objects it will retrieve all of the child objects at the same time.
        It can do this in-bulk, if retrieved parent-objects in bulk at the same time
        (ie: fetches a full page and then auto-bulk-fetches child objects associated with
        parent objects in that page that was fetched).
    """

    def __init__(self, cache_by_id: bool = None):
        if cache_by_id is not None:
            self.cache_by_id = cache_by_id

    def __repr__(self):
        return (
            'ApiOptions('
            f'cache_by_id={self.cache_by_id!r}, error_handler={self.error_handler}'
            ')'
        )


class ApiOptionsGroup(Dependency):
    """ Keeps track of a collection of current options for specific Api's/Model types.
    """
    _api_structure_to_options_map: Dict[Type[RemoteModel], ApiOptions]

    def __init__(self):
        self._api_structure_to_options_map = {}

    def get(self, *, api: 'RemoteApi', create_if_needed=True) -> ApiOptions:
        options = self._api_structure_to_options_map.get(api.model_type)
        if options:
            return options

        if not create_if_needed:
            return None

        options = ApiOptions()
        self._api_structure_to_options_map[api.model_type] = options
        return options

