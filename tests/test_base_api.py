from xmodel import BaseApi, BaseModel
from xmodel.converters import DEFAULT_CONVERTERS
from typing import TypeVar

M = TypeVar('M')


def none_converter(*args, **kwargs):
    pass


def str_converter(*args, **kwargs):
    pass


class MyFirstApi(BaseApi[M]):
    default_converters = {
        None: none_converter
    }


class MySecondApi(MyFirstApi[M]):
    default_converters = {
        str: str_converter
    }


class CommonModel(BaseModel[M]):
    api: MyFirstApi


class MyFirstModel(CommonModel['MyFirstModel']):
    pass


class MySecondModel(CommonModel['MySecondModel']):
    api: MySecondApi


def test_default_converters_inhert():
    assert MyFirstApi.default_converters == {None: none_converter}
    assert MyFirstModel.api.default_converters == {
        **DEFAULT_CONVERTERS,
        **{None: none_converter}
    }

    assert MySecondApi.default_converters == {str: str_converter}
    assert MySecondModel.api.default_converters == {
        **DEFAULT_CONVERTERS,
        **{None: none_converter},
        **{str: str_converter}
    }
