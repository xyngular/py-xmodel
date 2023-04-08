from copy import copy
from typing import TypeVar, Optional, Type

from xmodel import BaseStructure
from xmodel import Field
from xmodel.remote.options import ApiOptions

F = TypeVar('F', bound=Field)


class RemoteStructure(BaseStructure[F]):
    max_query_by_id = 100
    """
    You can easily change this per-model via model class argument `max_query_by_id`
    (see `RemoteStructure.configure_for_model_type` for more details).

    Example of easily setting this per-model-class
    (using a more concrete class RestModel, which inherits from RemoteModel):

    >>> from xmodel_rest import RestModel
    >>> class MyRemote(RestModel, max_query_by_id=500)
    ...     pass


    ### More Details

    This is used as a hint to `xmodel.remote.model.RemoteModel.get_via_id`
    on how much to query at a time. It uses this method to split up into chunks
    a list of ID's as needed automatically.

    That way the outside user can just pass in a list or generator function,
    that has many ID's. They will be chunked automatically into
    correct number to query for at a time.

    If you use a `1` for this, that means can only grab an object
    by it's id one at a time instead of in bulk.
    """

    api_options: ApiOptions = None
    """
    ## When defined at class (in a subclass) level:

    Set of default ApiOptions to apply to everything using the same structure class.
    These will be inherited. Anything directly set on ApiOptions will be inherited.

    If the Model class pass in an ApiOptions object as one of it's
    class parameters, anything specifically set on that object will override any defaults
    set on the BaseStructure subclass.

    Any subclasses of a particular structure class will also inherit any set api_options
    as you would expect.

    You can also change this on an already allocated BaseStructure or subclass.
    The class/parent inheritance only happens right when the object is constructued.
    Any already constructed BaseStructure or subclass, when an api_option is set,
    would only apply to the specific model-class the BaseStructure/subclass was allocated for.

    (Each model class gets a structure object instance, per-model-class).

    It's best to define these api_options at class-definition time
    (either for the structure or model); and not dynamically later to get consistent behavior.

    ## How to change Dynamically:

    If you want to change it dynamically, set the options via the Model types
    `xmodel.base.api.BaseApi.options`, ie: `MyModel.api.options.cache_by_id = True`.
    """

    def configure_for_model_type(
        self,
        *,
        max_query_by_id: int = None,
        api_options: "ApiOptions" = None,
        **kwargs
    ):
        """
        Read super-class docs for more details at `xmodel.base.structure.BaseStructure`.

        But to summarize, we are passed any model-class-arguments that the user provided
        when they defined their RemoteModel sub-class as key-word arguments into
        us, the `configure_for_model_type` method your reading about here.

        The super-method of us also has basic things like `model_type`, `type_hints` and other
        basic ones that are calculated/collects and come from
        `xmodel.base.model.BaseModel.__init_subclass__`.

        We are only documenting the ones relevant to RemoteModel/RemoteStructure here,
        see BaseModel/BaseStructure for the more details.

        Args:
            max_query_by_id (int): If passed in, will set the max number of objects we can request
                by id in the same request at the same time. This is inherited from a super-class.

                If a super-class has not set it, will default to `100`.
                We will otherwise inherit whatever the number is from parent model
                object if it set it to something different.

                See `RemoteStructure.max_query_by_id`, we simply set that property in here.

                Example of easily setting this per-model-class
                (using a more concrete class RestModel, which inherits from RemoteModel):

                >>> from xmodel_rest import RestModel
                >>> class MyRemote(RestModel, max_query_by_id=500)
                ...     pass

                ### More Details

                This is used as a hint to `xmodel.remote.model.RemoteModel.get_via_id`
                on how much to query at a time. It uses this method to split up into chunks
                a list of ID's as needed automatically.

                That way the outside user can just pass in a list or generator function,
                that has many ID's. They will be chunked automatically into
                correct number to query for at a time.

                If you pass in a `1` to this method, that means can only grab an object
                by it's id one at a time instead of in bulk.


            api_options (xmodel.options.ApiOptions): Set of options to use for the API if you
                wanted to change something so the option is enabled/disabled by Default for
                this Model. Keep in mind that a user can override these defaults via
                `xmodel.base.api.BaseApi.options`.

        """
        super().configure_for_model_type(**kwargs)

        if max_query_by_id is not None:
            self.max_query_by_id = max_query_by_id

        if api_options is not None:
            # We will get a copy of each attribute that api_options does not have set
            # but that the parent does.
            # todo: Look at this a bit more, I think we can come up with a better way
            #       perhaps with the new xsentinels `Default` type or some such.
            api_options.set_unset_values(self.api_options)
            self.api_options = api_options

    def __init__(
        self,
        *,
        parent: Optional['RemoteStructure'],
        field_type: Type[F]
    ):
        old_options = copy(self.api_options)
        if not old_options:
            old_options = ApiOptions()
        self.api_options = old_options

        super().__init__(parent=parent, field_type=field_type)

        if parent:
            self.api_options = old_options
            self.api_options.set_unset_values(parent.api_options)

    def __copy__(self):
        obj = super().__copy__()
        obj.api_options = copy(self.api_options)
        return obj

    def has_id_field(self):
        # Hard-Coding to return True; for details on why see doc-comment
        # on `BaseStructure.has_id_field`. Leaving doc-comment empty here because pydoc3
        # will just copy/reuse doc-comment from parent BaseStructure that way.
        return True
