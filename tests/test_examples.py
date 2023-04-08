

def test_basic_example():
    from xmodel import JsonModel

    class MyModel(JsonModel):
        some_attr: str

    json_dict_input = {'some_attr': 'a-value'}

    obj = MyModel(json_dict_input)
    assert obj.some_attr == 'a-value'

    json_dict = obj.api.json()
    assert json_dict == json_dict_input
