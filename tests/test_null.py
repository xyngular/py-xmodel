import pytest
from xsentinels.null import Nullable, Null
from xmodel import BaseModel


class MyModel(BaseModel):
    nullable_field: Nullable[str]
    non_nullable: int


def test_nullable():
    # See if nullable is being set correctly.
    structure = MyModel.api.structure
    nullable_field = structure.get_field('nullable_field')
    non_null_field = structure.get_field('non_nullable')

    assert nullable_field.nullable
    assert not non_null_field.nullable
    assert nullable_field.type_hint is str
    assert non_null_field.type_hint is int


def test_set_nullable_on_not_nullable_field():
    model = MyModel()
    model.nullable_field = Null

    with pytest.raises(AttributeError, match='Null value for field.+does not support NullType'):
        model.non_nullable = Null
