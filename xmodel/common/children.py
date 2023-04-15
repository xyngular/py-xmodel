from typing import List, Sequence, Union, Callable, Tuple, Dict, Type, Iterable
import types
import typing_inspect
import inspect
from dataclasses import dataclass

from xinject.context import XContext
from xsentinels.default import Default
from xsentinels.null import Null
from xmodel.util import loop

from xmodel import BaseModel
from xmodel.errors import XModelError
from xmodel.base.fields import Field
from xmodel import _private


@dataclass
class ModelChildRef:
    """ Relates a parent `xmodel.base.model.BaseModel` with a field-name and the child
        `xmodel.base.model.BaseModel` when asking for all child objects via
        `get_all_existent_child_objects`. See that method for more details.
    """
    parent: BaseModel
    """ The parent model of the child (ie: the `xmodel.base.model.BaseModel` child
        BaseModelis set on).
    """
    field: Field
    """ Field that the child is set on (from the parent's field list). """
    child: BaseModel
    """ Child `xmodel.base.model.BaseModel` object in question. """


# todo:  Need to go over this method and convert it for use in the sdk, it's been copied from
def get_all_existent_child_objects(
        objs: List[BaseModel],
        need_endpoint=True,
        *,
        needs_base_url=Default
) -> List[ModelChildRef]:
    """
    Given an list of a sub-type/class of ApiObj, get all the child-objects that exist on them.
    This will only grab the sub-objects that actually exist.

    By default need_endpoint is True and this means the sub-objects need to have model urls
    attached to them to be included in the returned results.
    That's determined right now via seeing if we have any urls on Model or not.

    Args:
        objs (List[xmodel.base.model.BaseModel]): List of `xmodel.base.model.BaseModel` to
            check for children on. These are the `ModelChildRef.parent` objects.

        need_endpoint (bool): If `True`: (default) then we will skip objects that have no
            api endpoint. I use `xmodel.base.structure.BaseStructure.have_api_endpoint` to find
            this out.

            If False: All child objects will be included.

        needs_base_url: If `xsentinels.Default` or `True`, only return objects that have a
            non-`False` base_url.
            This means the object has a foreign-key relationship with the parent object, and is not
            just an embedded dict or some such.

    Returns:
        List[ModelChildRef]: A list of BaseApi Obj's that are child objects of the provided objs.
    """
    if isinstance(objs, types.GeneratorType):
        raise XModelError(
            "bulk_request_lazy_children was called with a generator type, it needs a list"
        )

    result = []
    for obj in objs:
        api = obj.api
        structure = api.structure

        # todo: We are asking for related fields in a few places in this file now,
        # todo: perhaps make a method?
        # todo: We don't want to use 'obj-r', want a better way to get related fields.
        #       perhaps a list of 'xmodel.fields.Field' class objects directly from a method.
        for field_obj in structure.fields:
            # We want to prevent grabbing objects via API, so we check to see if it has a related
            # field id set on it.  If it does, then we continue to next field since the object
            # is not existent.
            related_type = field_obj.related_type
            if not related_type:
                continue

            type_hint = field_obj.type_hint
            if not inspect.isclass(type_hint) or not issubclass(type_hint, BaseModel):
                raise NotImplementedError(
                    f"Haven't implemented `List[BaseModel]` things yet; type_hint ({type_hint})..."
                )

            related_structure = api.structure

            if need_endpoint and not related_structure.have_api_endpoint:
                # Don't have an endpoint, so skip.
                continue

            child = api.get_child_without_lazy_lookup(field_obj.name)
            if not child:
                # If we are None/Null/False/Etc, we don't have an existent object.
                continue

            result.append(ModelChildRef(parent=obj, field=field_obj, child=child))

    return result


# todo:  Need to go over this method and convert it for use in the sdk, it's been copied from
def bulk_request_lazy_children(objs: Union[BaseModel, Sequence[BaseModel]]):
    """
    .. important:: This method currently only gets one 'level' of sub-objects;
        ie: it won't do it recursively.  When we need this feature, we can add it in.
        The intent is to ultimately support that.
        Just don't want to do the work until we start needing that.

    This method will bulk-get all the sub-objects if needed from the passed in list of objs.
    We will only get the sub-object if it can be lazily gotten. This means that the `*child*_id`
    field
    must have been passed into the parent object's json updater method and is not Null.
    When this happens the object keeps track of this `*child*_id` value in a hidden field and
    will retrieve the sub-object when someone asks for it on-demand.

    Instead of getting objects one at a time as they are requested, you can run a list of objects
    though this method, and they will all be gotten in a fast-bulk fashion [many objects
    per-request].

    So calling this method is more of an optimization if you know you will need the sub-objects.
    If you don't use this method, it will still work but it may be slower.

    The reason it only may be slower is because with either method [getting them on demand, or
    preemptively via this bulk method], we ultimately call `xmodel.base.api.BaseApi.get_via_id`
    on the model classes `xmodel.base.model.BaseModel.api`; which will
    check to see if we have a cached value (if enabled for that class/endpoint).  If all the
    sub-objects you care about are already cached, then getting them one at a time is just as
    fast as calling this bulk method.

    If you want to get all child objects on a set of parents without bulk-fetching the children
    that have not been fetched yet see `get_all_existent_child_objects`.

    Args:
        objs (Union[BaseModel, Sequence[BaseModel]): A list of objects that are of type ApiObj.
            They can be any mix of ApiObj subclasses.
    """

    if isinstance(objs, types.GeneratorType):
        raise XModelError(
            "bulk_request_lazy_children was called with a generator type, it needs a list"
        )

    # Some internal data structure notes:
    #
    # We have a ApiObj type key to a id int type key to a list of updating methods:
    # ie: `updating_methods[class][int] = [updating_method_def]`
    #
    # This is used to gather all the primary keys, which class/endpoint they go with and
    # finally a list of callables to call once we retrieve the object. We bulk-get by
    # Ctx, that way if multiple Ctx's are used for the same class, we use the correct
    # one per-object, but still in a bulk-fasion.  Normally there is only one Ctx instance
    # per-class, but I don't know if that will be the case in the future.  So I decided to not
    # assume only one and to make a general solution that should always work.

    updating_method_def = Tuple[BaseModel, Callable[[BaseModel], None]]
    updating_methods_value_type = Dict[int, List[updating_method_def]]
    updating_methods: Dict[Type[BaseModel], updating_methods_value_type] = {}

    # todo: Should we recursively grab sub-sub-objects in bulk, when we need it.
    #       We should loop right here and keep a set of objects to further traverse as we
    #       do our work. Use a set of already traversed objects we can check to make sure we don't
    #       infinitely loop.  When we run out of objects to traverse, we return.

    # Loop though all passed in objects to grab what sub-objects they need. We consolidate on
    # the primary key, so we only retrieve/request one object per-id, per-Ctx [we separate by
    # the Ctx value later on].
    for obj in loop(objs):
        c = type(obj)
        api = obj.api
        structure = api.structure
        state = _private.api.get_api_state(api)

        # We retrieve the lazy-state this way, since we can:
        #   1. Get the hidden lazy id field.
        #
        #   2. Prevent the object from lazily request the object on it's own with our own
        #      inspection here!  We want to get them in bulk, not one at a time accidentally.
        #
        # When an object is set on the property, it removes any related lazy field id, so
        # that way we know it exists on the object [or is unretrievable, which is fine too].
        #
        # We are allowed to use any of the private methods when we do it within this file.
        #
        for field_obj in structure.fields:
            if not field_obj.related_type:
                continue

            related_model_class = field_obj.type_hint
            field_name = field_obj.name
            name_id_value = state.get_related_field_id(field_name, return_false_if_child_set=True)
            if name_id_value in (None, Null, False):
                # No need to look further...
                continue

            dict_of_id_to_updaters = updating_methods.get(related_model_class)
            if dict_of_id_to_updaters is None:
                dict_of_id_to_updaters = {}
                updating_methods[related_model_class] = dict_of_id_to_updaters

            list_of_updaters = dict_of_id_to_updaters.get(name_id_value)
            if list_of_updaters is None:
                list_of_updaters = []
                dict_of_id_to_updaters[name_id_value] = list_of_updaters

            # Create mapping logic
            # noinspection PyShadowingNames
            def updater(child_obj: Union[BaseModel, list], obj=obj, field_name=field_name):
                setattr(obj, field_name, child_obj)

            # Insert mapping logic into list of callable's:
            list_of_updaters.append((obj, updater,))

    # todo: We could simplify this by directly using the `Field` objects, they already
    #   know what the inner-model-type is [if the type-hint was a generizied `List`].
    for model_type, id_to_updaters in updating_methods.items():
        model_type_was_list = False
        if typing_inspect.get_origin(model_type) is list:
            model_type = typing_inspect.get_args(model_type)[0]
            model_type_was_list = True

        api = model_type.api
        id_to_updaters: updating_methods_value_type
        ctx_to_updaters: Dict[XContext, updating_methods_value_type] = {}

        if model_type_was_list:
            for _id, updater_def_list in id_to_updaters.items():
                id_list: list = []
                parent_obj_map_by_id = {}
                for updater_def in updater_def_list:
                    id_list.append(updater_def[0].id)
                    parent_obj_map_by_id[updater_def[0].id] = updater_def

                query_id_field_name = str(_id) + "_id"
                query = {
                    query_id_field_name: id_list
                }
                objs = api.get(query=query)

                objs_mapped_to_parent_ids = {}
                for obj in objs:
                    parent_id = getattr(obj, query_id_field_name, None)
                    if parent_id:
                        objs_for_parent = objs_mapped_to_parent_ids.get(parent_id)
                        if not objs_for_parent:
                            objs_for_parent = []
                        objs_for_parent.append(obj)
                        objs_mapped_to_parent_ids[parent_id] = objs_for_parent
                for parent_id, parent_obj in parent_obj_map_by_id.items():
                    child_objs = objs_mapped_to_parent_ids.get(parent_id, [])
                    parent_obj[1](child_objs)
        else:
            # Separate by Ctx, that way we use correct Ctx to bulk-get sub-objects.
            for _id, updater_def_list in id_to_updaters.items():
                for updater_def in updater_def_list:
                    ctx = updater_def[0].api.context
                    new_id_to_updater_list = ctx_to_updaters.get(ctx)
                    if new_id_to_updater_list is None:
                        new_id_to_updater_list = {}
                        ctx_to_updaters[ctx] = new_id_to_updater_list

                    new_updaters = new_id_to_updater_list.get(_id)
                    if new_updaters is None:
                        new_updaters = []
                        new_id_to_updater_list[_id] = new_updaters

                    new_updaters.append(updater_def)

            # Grab and assign the objects in their parent objects.
            for ctx, ctx_id_to_updater_def_list in ctx_to_updaters.items():
                id_list: Iterable[int] = ctx_id_to_updater_def_list.keys()
                # This is where the bulk-getting per-Ctx happens.
                objs = api.get_via_id(id_list)
                for obj in objs:
                    updater_def_list = ctx_id_to_updater_def_list.get(obj.id, None)
                    if updater_def_list is not None:
                        for updater_def in updater_def_list:
                            updater_def[1](obj)
