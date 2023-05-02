from decimal import Decimal
from typing import List

import pytest

from xmodel import JsonModel, Field, XModelError
from enum import Enum

from xmodel.remote import RemoteModel


class MyEnum(Enum):
    FIRST_VALUE = 'first-value'
    SECOND_VALUE = 'second-value-2'


class MyJModel(JsonModel):
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
    m = MyJModel()
    m.enum_field = MyEnum.FIRST_VALUE.value
    assert m.enum_field is MyEnum.FIRST_VALUE
    assert m.api.json()['enum_field'] == MyEnum.FIRST_VALUE.value

    m.api.update_from_json({'enum_field': MyEnum.SECOND_VALUE.value})
    assert m.enum_field is MyEnum.SECOND_VALUE
    assert m.api.json()['enum_field'] == MyEnum.SECOND_VALUE.value


def test_property_field():
    m = MyJModel()
    m.a_field = "my-value"
    # Property should have stored it here:
    assert m._a_field_storage == "my-value"

    m._a_field_storage = "new-value"
    assert m.a_field == "new-value"


def test_include_with_fields_option():
    original_value = {'a_field': 'a-value', 'b_field': 2}
    m = MyJModel(original_value)

    # Will return nothing as object was just created.
    assert m.api.json(only_include_changes=True) is None

    m.a_field = "hello"

    # Will return a_field, since 'a_field' was changed.
    assert m.api.json(only_include_changes=True) == {'a_field': 'hello'}

    m.a_field = "a-value"

    # Will return None since change was reverted
    assert m.api.json(only_include_changes=True) is None

    m.api.update_from_json({'a_field': 'a-value-changed'})

    # Will return None as it was updated from json.
    assert m.api.json(only_include_changes=True) is None

    m.b_field = 42

    # Will return b_field, since 'a_field' was changed; also includes 'a_field', since it's
    # configured to be included when 'b_field' is as well.
    assert m.api.json(only_include_changes=True) == {'a_field': 'a-value-changed', 'b_field': 42}


def test_changes_only_embedded_object():
    class JModel(JsonModel):
        field_str: str
        field_int: int

    class JParent(JsonModel):
        p_field_int: int
        embedded: JModel

    jp = JParent({
        'p_field_int': 100,
        'embedded': {
            'field_str': 'a-str',
            'field_int': 10
        }
    })

    assert jp.api.json(only_include_changes=True) is None

    jp.embedded.field_int = 33

    # Only including changes, so should only include the embedded-objects changes
    assert jp.api.json(only_include_changes=True) == {'embedded': {'field_int': 33}}
    assert jp.api.json() == {
        'embedded': {'field_int': 33, 'field_str': 'a-str'},
        'p_field_int': 100
    }


def test_default_value_called_if_callable_as_needed():
    class JModel(JsonModel):
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
    class RModel(RemoteModel):
        id: int

    class JParent(JsonModel):
        embedded: RModel

    # Ensure related model field id is of correct type.
    jp = JParent({'embedded_id': Decimal("20")})
    v = jp.api._api_state.get_related_field_id('embedded')
    assert type(v) is int
    assert v == 20


def test_related_field_id_type_conversion_str():
    class RModel(RemoteModel):
        id: str

    class JParent(JsonModel):
        embedded: RModel

    # Ensure related model field id is of correct type.
    jp = JParent({'embedded_id': Decimal("20")})
    jp.embedded = RModel(id="20")
    jp.embedded_id = 20
    v = jp.api._api_state.get_related_field_id('embedded')
    assert type(v) is str
    assert v == "20"
    assert jp.embedded


def test_related_field_id_type_conversion2():
    class JModel(JsonModel):
        id: int

    class JParent(JsonModel):
        embedded: JModel

    # Ensure related model field id is of correct type.
    jp = JParent({'embedded_id': Decimal("20")})
    with pytest.raises(XModelError):
        v = jp.api._api_state.get_related_field_id('embedded')


def test_empty_json_dict_to_create_model():
    class JModel(JsonModel):
        a_field: str = "default-value"
    obj = JModel({})
    assert obj.a_field == "default-value"
