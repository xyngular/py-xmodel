from decimal import Decimal
from typing import List

from xmodel import Field, JsonModel
from xmodel.remote import RemoteClient
from xmodel.remote.model import RemoteModel
from enum import Enum


class MyEnum(Enum):
    FIRST_VALUE = 'first-value'
    SECOND_VALUE = 'second-value-2'


class BModel(RemoteModel['MyModel']):
    _a_field_storage = None
    _b_field_storage = None

    a_field: str = Field(include_with_fields={'b_field'})

    @a_field.getter
    def a_field(self) -> str:
        return self._a_field_storage

    @a_field.setter
    def a_field(self, value):
        self._a_field_storage = value

    b_field: int

    @property
    def b_field(self):
        return self._b_field_storage

    @b_field.setter
    def b_field(self, value):
        self._b_field_storage = value

    enum_field: MyEnum


def test_enum_field():
    m = BModel()
    m.enum_field = MyEnum.FIRST_VALUE.value
    assert m.enum_field is MyEnum.FIRST_VALUE
    assert m.api.json()['enum_field'] == MyEnum.FIRST_VALUE.value

    m.api.update_from_json({'enum_field': MyEnum.SECOND_VALUE.value})
    assert m.enum_field is MyEnum.SECOND_VALUE
    assert m.api.json()['enum_field'] == MyEnum.SECOND_VALUE.value


def test_property_field():
    m = BModel()
    m.a_field = "my-value"
    # Property should have stored it here:
    assert m._a_field_storage == "my-value"

    m._a_field_storage = "new-value"
    assert m.a_field == "new-value"


def test_include_with_fields_option():
    original_value = {'a_field': 'a-value', 'b_field': 2}
    m = BModel(original_value)

    # Will return all changes, since `id` is set to None still.
    assert m.api.json(only_include_changes=True) == original_value

    m.api.update_from_json({'id': 20})

    # Will return no changes due to 'id' value being not None and no changes made to the object.
    assert m.api.json(only_include_changes=True) is None

    m.a_field = "hello"

    # Will return a_field + id, since 'a_field' was changed and 'id' is always included with
    # any other changes.
    assert m.api.json(only_include_changes=True) == {'a_field': 'hello', 'id': 20}

    m.a_field = "a-value"

    # Will return None since change was reverted
    assert m.api.json(only_include_changes=True) is None

    m.b_field = 42

    # Will return b_field + id, since 'a_field' was changed and 'id' is always included with
    # any other changes; also includes 'a_field', since it's configured to be included when
    # 'b_field' is as well.
    assert m.api.json(only_include_changes=True) == {
        'a_field': 'a-value', 'b_field': 42, 'id': 20
    }


def test_changes_only_embedded_jsonmodel_object():
    class JModel(JsonModel['JModel']):
        field_str: str
        field_int: int

    class RParent(RemoteModel['RParent']):
        p_field_int: int
        embedded: JModel

    rp = RParent({
        'id': 1,
        'p_field_int': 100,
        'embedded': {
            'field_str': 'a-str',
            'field_int': 10
        }
    })

    assert rp.api.json(only_include_changes=True) is None

    rp.embedded.field_int = 33

    # Only including changes, so should only include the embedded-objects changes
    assert rp.api.json(only_include_changes=True) == {'embedded': {'field_int': 33}, 'id': 1}
    assert rp.api.json() == {
        'id': 1, 'embedded': {'field_int': 33, 'field_str': 'a-str'}, 'p_field_int': 100
    }


def test_default_value_called_if_callable_as_needed():
    class JModel(RemoteModel['JModel']):
        field_str: str = 2
        field_list: List[str] = list

    j = JModel()
    assert j.field_str == '2'
    assert j.field_list == []
    j_list = j.field_list

    j2 = JModel()

    assert j_list is not j2.field_list
    assert j2.field_list == []


def test_related_field_id_type_conversion():
    class JModel(RemoteModel['JModel']):
        id: int

    class JParent(RemoteModel['JParent']):
        embedded: JModel

    # Ensure related model field id is of correct type.
    jp = JParent({'embedded_id': Decimal("20")})
    v = jp.api._api_state.get_related_field_id('embedded')
    assert type(v) is int
    assert v == 20


def test_empty_json_dict_to_create_model():
    class JModel(RemoteModel['JModel']):
        a_field: str = "default-value"
    obj = JModel({})
    assert obj.a_field == "default-value"


def test_parent_model_no_id_then_embed_json_sub_model_fully():
    class JModel(JsonModel['JModel']):
        child_field: str

    class RParent(RemoteModel['RParent']):
        embedded: JModel
        parent_field: str

    json_data = {
        'embedded': {
            'child_field': 'child-value'
        },
        'parent_field': 'parent-value'
    }

    rp = RParent({'id': 1, **json_data})

    # Did not make any changes, so should be `None`:
    assert rp.api.json(only_include_changes=True) is None  # Should only include changes

    # If model has an id-field and there is no `id` value, model will override the
    # suggestion to `only_include_changes` and should include everything, including what is in
    # the embedded sub-model.
    rp.id = None
    assert rp.api.json(only_include_changes=True) == json_data




