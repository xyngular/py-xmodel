from xmodel.remote.response_state import ResponseState
from xmodel.remote.model import RemoteModel


def test_error_state_detailed_error():
    state = ResponseState()
    state.add_field_error(field='my_field', code='some-code')

    assert state.has_field_error(field='my_field', code='some-code')
    assert not state.has_field_error(field='my_field', code='some-other-code')
    assert not state.has_field_error(field='my_field_other', code='some-code')

    assert state.had_error

    state_no_error = ResponseState()
    assert not state_no_error.has_field_error(field='my_field', code='some-code')


class TestModel(RemoteModel):
    pass


def test_remote_model_repr_with_error_state():
    # Ensure the string representation has the objects error info in it, if error info set.
    a = TestModel()
    a.api.response_state.had_error = True
    assert "__had_error=True" in str(a)
    assert "__response_code" not in str(a)
    assert "__errors" not in str(a)

    a.api.response_state.response_code = 404
    assert "__had_error=True" in str(a)
    assert "__response_code=404" in str(a)
    assert "__errors" not in str(a)

    a.api.response_state.errors = ['an error']
    assert "__had_error=True" in str(a)
    assert "__response_code=404" in str(a)
    assert "__errors=['an error']" in str(a)


