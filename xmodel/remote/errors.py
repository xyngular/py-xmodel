from xmodel.errors import XynModelError


class XynRemoteError(XynModelError):
    pass


class XynRemoteMaintenanceError(XynRemoteError):
    """
    Standard exception that should be raised if during an API communication it's determined
    there is an error due to a maintenance window of some sort.
    """
