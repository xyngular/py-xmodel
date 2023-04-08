from copy import copy
from typing import List, Optional, Any, TypeVar

T = TypeVar("T")


# todo: Update (2021-03-26): I want to eventually remove all use of this.
#       Look at `xmodel.fields.Field` class for better example of how to inherit values
#       from parents.
#       No one should use this for new code!!!!
class SetUnsetValues:
    def set_unset_values(self, parent: Optional['SetUnsetValues']):
        """
        .. deprecated:: Update (2021-03-26): I want to eventually remove all use of this.
            Look at `xmodel..fields.Field` class for better example of how to inherit
            values from parents.
            No one should use this for new code!!!!

        Takes values that were DIRECTLY set on passed in parent and sets a copy of value on self
        as long as the values in `self` have not been directly set [ie: they are still using
        their default value from the class].

        This is called on sub-classes the BaseModel for each object if the child and parent
        classes both define a object for the same attribute name. In this way, child/subclasses
        that directly set values on their field class will override the parents value
        for that particular Field.xyz attribute.

        The values set directly on the class are the default values. When calling
        `set_unset_values()`, only the values that are explicitly set on the passed in object and
        NOT set on 'self' are set on 'self [ie: self=object your calling 'set_unset_values()' on].

        This means that for a particular value, if it still uses the class value for a particular
        field value, it won't be appended. If you want a particular value set, then set the value
        to something via __init__ method or by direct assignment to object.

        :param parent:
            object to be appended on this. It only appends the attribute to self if it's
            NOT currently set directly on object [ie: does not exist in object, but only on class].
        """
        if not parent:
            return

        for name, value in parent.__dict__.items():
            if name not in self.__dict__:
                setattr(self, name, copy(value))


def chunk_list(list: List[Any], chunk_size: int) -> List[List[Any]]:
    """
    Accepts a list, and returns that list, split up into chunk_size chunks.
    Args:
        list (List[Any]): List to operate on.
        chunk_size (int): Max size of each chunk.
    """
    return [list[i:i + chunk_size] for i in range(0, len(list), chunk_size)]
