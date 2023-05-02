"""
The purpose of the JsonModel is to be able to create model classes from json data we have
retrieved from somewhere that is not an API endpoint or as a subclass of data from an API
endpoint that does not have it's own endpoint. We also want to be able to find any related models
that may have an API endpoint that we can retrieve their data from. An example of this would be a
database that has a RemoteModel's id stored within it that we may want to retrieve at a later date
or only at certain times when that data is relevant so that we do not manually have to look up
that RemoteModel ourselves and will let the associated model look itself up in the way that it
knows how to.
"""

from typing import TypeVar
from .base import BaseModel


M = TypeVar('M')


class JsonModel(BaseModel):
    pass
