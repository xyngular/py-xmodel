from xmodel import Field, JsonModel
import datetime as dt


def test_json_path():
    class TestModel(JsonModel['TestModel']):
        json_path_field: str = Field(json_path='json_path_field.value')

    json = {
        'json_path_field': {'value': 'the-value'}
    }

    obj = TestModel(json)
    assert obj.json_path_field == 'the-value'


def test_basic_datetime_conversion():
    class TestModel(JsonModel['TestModel']):
        a_datetime_field: dt.datetime

    obj = TestModel(a_datetime_field='2023-04-08T10:11:12Z')
    assert obj.a_datetime_field.isoformat() == '2023-04-08T10:11:12+00:00'
