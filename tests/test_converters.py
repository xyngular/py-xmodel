from xmodel.converters import ConvertBasicInt, Converter, DEFAULT_CONVERTERS
from xmodel import Field, converters
from xmodel import BaseModel
from xsentinels.null import Null
import datetime as dt
from decimal import Decimal


class BasicModel(BaseModel):
    field_int: int
    field_str: str
    field_date: dt.date
    field_time: dt.datetime
    field_bool: bool
    field_float: float
    field_decimal: Decimal


def test_basic_int_converter():
    converter = ConvertBasicInt()
    model = BasicModel()
    field = BasicModel.api.structure.get_field('field_int')
    # By default, the basic int converter should turn a blank string into zero.
    assert converter(model.api, Converter.Direction.to_model, field, '') == 0


def test_basic_decimal_converter():
    field = BasicModel.api.structure.get_field('field_decimal')
    converter = field.converter
    model = BasicModel()
    assert converter(model.api, Converter.Direction.to_model, field, '1.03') == Decimal('1.03')
    assert converter(model.api, Converter.Direction.to_json, field, Decimal('2.03')) == '2.03'


def test_default_converters_against_null():
    obj = BasicModel()
    for field in BasicModel.api.structure.fields:
        type_hint = field.type_hint
        converter = DEFAULT_CONVERTERS[type_hint]
        result = converter(obj.api, converters.Converter.Direction.to_json, field, Null)
        assert result is Null

        # For now, just test basic types with blank values
        if type_hint not in (int, float, str, bool):
            continue
        blank_value = type_hint()
        result = converter(obj.api, converters.Converter.Direction.to_json, field, type_hint())
        assert result == blank_value
        assert result is not Null


def test_default_model_values_use_converters():
    class B2Model(BaseModel):
        f1: int
        f2: Decimal = Field(default='10.32')

    b2 = B2Model()
    assert b2.f2 == Decimal('10.32')
