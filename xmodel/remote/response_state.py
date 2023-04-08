from typing import Dict, List, Any, Optional, Union, TypeVar, Generic
# noinspection PyPep8Naming
from enum import Enum, auto as EnumAuto  # noqa
from xurls.url import URL
from abc import ABC, abstractmethod

T = TypeVar("T")

# We want these special methods in the documentation.
__pdoc__ = {
    'HttpErrorHandler.__call__': True
}


# todo: Consider moving this somewhere else, perhaps make it exclusive to ApiOptions for now...
class ErrorHandler(Generic[T], ABC):
    """ Method signature of a ErrorHandler callback method.

        See `HttpErrorHandler.__call__` for details.
    """
    @abstractmethod
    def __call__(self, obj: T, http: "ResponseState[T]", url: URL) -> bool:
        """
        Signature of the call that happens for an HttpErrorHandler.

        Keep in mind that xmodel.rest.RestClient only checks for this for POST/PUT/PATCH
        at the moment. I want to expand it's use to other methods in the future.

        Different things happen based on what's returned:
            If True: Error was handled and no more error handling will be done.
            If False: Run next handler, and if that does not exist we do the default handling.

        False is the default value returned from this.

        Args:
            obj (xmodel.base.model.BaseModel): The original model object.

            http (ResponseState): The `xmodel.remote.api.RemoteApi.response_state` object,
                passed in here for convenience.

            url (xurls.URL): url that was used. You can ask the url for the http method that
                was used, there will always only be exactly ONE method assigned to the URL you get
                here (`xurls.URL.methods`).
        """
        return False


class ResponseStateRetryValue(Enum):
    """ Possible values for HttpState.should_retry_send.
        Controls if the data that was previously exported from the object should be reused in
        the new request, or if the objects data/values needs to be re-exported into JSON.
    """
    AS_IS = EnumAuto()
    """
    This is an optimization: The values that were previously exported when we previously
    attempted to send it will be reused again.  It's more efficient because dates, and other
    special objects, along with the JSON dicts/lists won't have to be re-created again.
    This is the default option. If the object has changed in some way, then you should
    use the `ResponseStateRetryValue.EXPORT_JSON_AGAIN` value instead.
    """

    EXPORT_JSON_AGAIN = EnumAuto()
    """
    Will re-export/convert to JSON from the object's values before trying the request again.
    You want to use this option if the object was changed in some way and we need to re-export
    it's value before trying to sending it again.
    """


class ResponseState(Generic[T]):
    """ This object encapsulates the previous request to send the object to the API.

        You can use retry_send to mark an object as needing to be retried while it's error handler,
        or while the `RestClient.parse_send_response_error` method is called for object.

        Use `HttpState.has_field_error` to easily see if there was a specific type of field error.

        Also useful:

        - `HttpState.had_error`
        - `HttpState.did_send`

        `HttpState.try_count` is incremented each time the object had an attempt to send it.
        The `xmodel.rest.RestClient` by default will only retry 4 times,
        to prevent infinite loops.
    """

    had_error: Optional[bool] = None
    """ Is `None` if no request involving this object has been completed yet. `True` if last http
        request with this object had an error, otherwise `False`.
    """

    errors: Optional[List[Any]] = None
    """ List of error strings related to last request involving this object, meant to be
        Human readable reasons for the error from the API.

        Even if `HttpState.had_error` is True, this could still be None.
    """

    field_errors: Optional[Dict[str, List[Dict[str, str]]]] = None
    """
    Dict with the key a field name, the value is a list of errors. Each list element is a
    dict with a human readable error message, consistent code, etc; about field if we are able
    to parse this out of the response.

    for easy ways to work with this structure see methods:

    - `HttpState.add_field_error`
    - `HttpState.has_field_error`

    Even if `HttpState.had_error` is True, this could still be None if we were unable to find/parse
    the field errors. Field are are just more specific information about the error(s) with the
    request.

    You can subclass the `xmodel.rest.RestClient` class and override
    `xmodel.rest.RestClient.parse_errors_from_send_response`
    (go there for more docs/details about this).

    You can get a `xmodel.base.model.BaseModel`'s response_state state from
    `xmodel.remote.api.RemoteApi.response_state` via `xmodel.base.model.BaseModel.api`.

    If you want to parse out field errors and add them to the `model_obj.api.response_state`
    see `xmodel.rest.RestClient.parse_errors_from_send_response`.
    """

    response_code: Optional[int] = None
    """ HTTP response code for the last request involving this object. """

    did_send = None
    """ If value is:

        - `True`: Object was sent to API.
        - `False`: Then `xmodel.rest.RestClient.enable_send_changes_only` was enabled for
            client and it was determined the object did not have any changes to send.
        - `None`: No determination has been made yet or an attempt to send object has not happened
            yet.
    """

    try_count: int = 0
    """ Right after an attempt is made to send object, this should be incremented by 1.
        This is how many attempts have been made to send the object.

        If the `HttpState.try_count` is zero, we are either in the middle of sending the object
        or it has not been attempted yet.
    """

    should_retry_send: Optional[ResponseStateRetryValue] = None
    """ The system uses this to mark something that had an error, that it should be retried.
        You should use 'HttpState.retry_send()` if you want to mark something to retry.

        The `xmodel.rest.RestClient` will call `HttpState.reset` passing in `for_retry=True`
        right before it actually does the retry.
    """

    error_handler: Optional[ErrorHandler[T]] = None
    """ Totally optional way to customize the error handling process for a single object.

        If this is None, then we check the `error_handler` in
        `xmodel.options.ApiOptions.error_handler`
        {via `xmodel.api.BaseApi.option_for_name`('error_handler')}. If that turns up nothing
        the `xmodel.rest.RestClient` will do whatever the standard error handling is.

        Normally it would move on to to send next object so it can update as many objects as it
        can (if there are more to send). An exception is normally only raised if there is a more
        serious error (ie: can't parse the response due to invalid JSON, etc).

        .. todo:: In Future: Perhaps have a way to raise an exception if there is an error after
            it sends as many objects as it can?  Not sure... I'll think about it.
    """

    def mark_for_no_errors(self):
        """
        This can be called to reliably mark that no errors happened.
        Resets all related error fields and set had_error = False.

        Won't change the `HttpState.did_send` and other non-error related information.
        This only sets the error related info to indicate no errors happened.

        Resets:

        - `HttpState.had_error`
        - `HttpState.errors`
        - `HttpState.field_errors`
        """
        # _self Helps PyCharm go to the class-level attribute when jumping to it's declaration.
        # Otherwise it will come here instead of where the attributes doc-comment is.
        _self = self
        _self.had_error = False
        _self.errors = None
        _self.field_errors = None

    def reset(self, *, for_retry: bool = False):
        """
        RestClient calls this on all objects before it tries to send/get anything.
        Everything in object will be reset to None or Zero.

        Args:
            for_retry (bool): If provided value is:

            - `False` (default): Nothing more happens.
            - `True`: We will NOT reset the self.try_count, it will be left as-is.
        """

        # _self Helps PyCharm go to the class-level attribute when jumping to it's declaration.
        # Otherwise it will come here instead of where the attributes doc-comment is.
        _self = self
        _self.had_error = None
        _self.errors = None
        _self.field_errors = None
        _self.response_code = None
        _self.did_send = None
        _self.should_retry_send = None

        if not for_retry:
            _self.try_count = 0

    def retry_send(
        self, retry_value: Union[bool, ResponseStateRetryValue] = ResponseStateRetryValue.AS_IS
    ):
        """
        RestClient calls this on all objects that it wants the system to retry when client calls
        the `parse_send_response_error` method on RestClient class object.

        Args:
            retry_value (Union[bool, ResponseStateRetryValue]): Default to
                `ResponseStateRetryValue.AS_IS`, if it is:

                - `False`: We will use the value ResponseStateRetryValue.EXPORT_JSON_AGAIN,
                    which will re-export
                    the JSON from the object before trying again. You want to use this option if
                    the object was changed in some way and we need to re-export it's value before
                    we try sending it again.
                - `True` / `ResponseStateRetryValue.RETRY_AS_IS` (default):
                    If retry_value is True, ResponseStateRetryValue.RETRY_AS_IS will be used.
                - `ResponseStateRetryValue`: Use whatever ResponseStateRetryValue was passed in,
                    see `ResponseStateRetryValue` for details.
        """
        if retry_value is True:
            retry_value = ResponseStateRetryValue.AS_IS
        elif retry_value is False:
            retry_value = ResponseStateRetryValue.EXPORT_JSON_AGAIN

        self.should_retry_send = retry_value

    def add_field_error(
            self,
            field: str,
            code: Union[str, int],
            other: Dict[str, Union[str, int]] = None
    ):
        """
        Easily add/append a field-error into self.field_errors in a way that will make it
        work when using 'has_field_error'.

        .. important::
            The 'code' that is passed in will override anything keyed with 'code' from other.

        Args:
            field (str): Field name that had the error. Used as the field-key in self.field_errors.
            code (Union[str, int]): str/int that's value consistent for the type of error returned
                from api. This will be added to the final message dict after inserting anything
                from `other` into message.
            other (Dict[str, Union[str, int]]): Other data the api may return about the error,
                will be inserted into the final message dict.
                Usually includes some sort of human readable message among other things.
        """
        field_errors = self.field_errors
        if field_errors is None:
            field_errors = {}
            self.field_errors = field_errors

        error_list = field_errors.setdefault(field, [])

        # construct final message structure:
        message = {
            **(other or {}),
            "code": code
        }

        # Append message to error list.
        error_list.append(message)
        self.had_error = True

    def has_field_error(self, field: str, code: Union[str, int]) -> bool:
        """
        Looks for a field error for the name/code, and returns True if one is found,
        otherwise False.

        If self.had_error is False, we will always return False.
        Args:
            field (str): field name to check.
            code: (Union[str, int]): value to check for on field if any field error is present.

        Returns:
            bool: `True` if error with code found, otherwise `False`.
        """
        if not self.had_error:
            return False

        errors = self.field_errors
        if not errors or not isinstance(errors, dict):
            return False

        field_err = errors.get(field)
        if not field_err or not isinstance(field_err, list):
            return False

        for e in field_err:
            if not isinstance(e, dict):
                continue

            if e.get('code') == code:
                return True

        return False
