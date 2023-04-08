from xmodel.errors import XModelError


class XRemoteError(XModelError):
    pass


class XRemoteMaintenanceError(XRemoteError):
    """
    Standard exception that should be raised if during an API communication it's determined
    there is an error due to a maintenance window of some sort.
    """
