from xmodel.converters import Direction
from xmodel.errors import XModelError
from xsentinels.null import Null
from typing import TYPE_CHECKING, TypeVar, Generic
from xmodel.base.model import BaseModel
from xmodel.common.types import JsonDict

M = TypeVar("M", bound=BaseModel)

# noinspection PyUnreachableCode
if TYPE_CHECKING:
    # We only need this for the type-hint, and nothing else.
    # Use forward-refs 'BaseApi' [with the quotes].
    # Gives code from outside this module hints about some of the types.
    from xmodel import BaseApi


class PrivateApiState(Generic[M]):
    """ This class is used as a private repository to store api related state for a BaseModel
        instance.
    """

    def __init__(self, model: BaseModel):
        self.model = model
        self.related_field_id_area = {}

    # ------------------------------------------------------
    # --------- These Can Vary BaseModel per-instance! ---------

    model: M
    """ Instance of model [or None if this state is directly associated with a BaseModel Class
        and not any particular instance.
    """

    last_original_update_json: JsonDict = None
    """ The keys are set to the raw-value of the last time that attribute was updated via
        update_from_json. So the value is what was originally passed to update_from_json, per-key.
        Meaning that if we get an update from API that does not include some fields that were
        previously included in the past [for the same ApiObj instance], we leave them as they were
        and only update the keys that we got via the last update_from_json() call.

        This is used to send only what has changed. If what we would send to DB is different
        then what we originally got, then we know if it changed or not. If there is no key set
        for a particular attribute, then assume we never got a copy of it from API and it should
        be sent to API during next Patch to API.

        If this value is None, that means we never got any value via a JSON dict, which normally
        means that we did not come from the API, we were created directly and/or our values came
        from somewhere else.
    """

    related_field_id_area = None

    @property
    def api(self) -> "BaseApi[M]":
        return self.model.api

    def reset_related_field_id_if_exists(self, name):
        if name in self.related_field_id_area:
            del self.related_field_id_area[name]

    def get_related_field_id(self, name, return_false_if_child_set=False):
        """
        This will grab the id from child obj if it exists or from related id storage.

        :param name:
        :param return_false_if_child_set:
            [Default is False]
            If True:  Return False if the child has been set. This indicates that
                      you can ask the child of anything you want.
            If False: Return the id directly from the child if child has been already set.
        :return:
        """
        api = self.api
        structure = api.structure

        if not structure.is_field_a_child(name, and_has_id=True):
            raise XModelError(
                f"Called is_field_a_child('{name}') for model cls "
                f"({structure.model_cls}), but field is not a child with a "
                f"defined id."
            )

        child = api.get_child_without_lazy_lookup(name)
        if return_false_if_child_set and child is not None:
            return False

        if child is Null:
            return Null

        if child is not None:
            return child.id

        return self.related_field_id_area.get(name, None)

    def set_related_field_id(self, name, value):
        """
        Sets the `id` for the related field.  If the field is not a child object, or if the child
        does not use an id field, then will raise an XModelError.

        If a child is already set on field 'name' and:
            1. It's id == value you pass in, then nothing will change.
            2. Value is Null and child's id field is set to None, nothing will change.
            3. Value is Null and child has an id, we set the child-field value directly to Null.
            4. Otherwise, we will delete the child attribute to force it to be lazily looked
               up by the new related field id `value` next time someone directly requests the
               child by its field value.

        We store this id in a special area. The next time the child is asked for by it's normal
        field/attribute name, we will lazily look it up via API and store that on the field.

        If a child object is set on the field directly by someone else, any previously set
        related_field_id will be deleted, as it is no longer relevant [and even mis-leading].

        Reminder: self._get_related_field_id will grab the value from the child directly if it
        has been set.  It only consults the special storage area if the child is set to None or
        has not been set on it's parent at field `name`.

        :param name: Field name of the child.
        :param value: Value to set it's id value to.
        :return: None
        """

        api = self.api
        model = self.model
        structure = api.structure

        if not structure.is_field_a_child(name, and_has_id=True):
            raise XModelError(
                f"Called set_related_field_id('{name}') for ({self.model}), but field is not a "
                f"child with a defined id."
            )

        child = api.get_child_without_lazy_lookup(name, false_if_not_set=True)
        have_child_obj = child not in (None, Null, False)

        def convert_id(value):
            field = child.api.structure.get_field("id")
            return field.converter(child.api, Direction.to_model, field, value)

        if have_child_obj and value is not Null and child.id == convert_id(value):
            # Child object already has this id, nothing more to do...
            return
        elif child is Null and value is Null:
            return
        elif have_child_obj and value is Null:
            # We only want to nullify the child obj value if it has a primary key that is
            # different then the one we are being set with now. If they have a None for the
            # id, then the object has not been created yet.  We assume the parent needed
            # to be created first before the child could be created, so we will leave the
            # uncreated child be and do nothing with the Null value we got.

            if child.api.structure.has_id_field() and child.id is not None:
                setattr(model, name, Null)
            return
        elif value is Null:
            setattr(model, name, Null)
            return

        # I want to delete the attribute if it exists, because we then will lazily lookup object
        # next time the field is accessed.
        if child is not False:
            delattr(model, name)

        self.related_field_id_area[name] = value
