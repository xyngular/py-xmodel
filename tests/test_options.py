from xmodel.remote.options import ApiOptions, ApiOptionsGroup
from xmodel.remote import RemoteModel, RemoteApi


class MyRemoteModel(RemoteModel):
    pass


def test_api_options():
    MyRemoteModel.api.options.cache_by_id = True
    assert MyRemoteModel.api.options.cache_by_id is True
    with ApiOptionsGroup():
        # Gets the latest option that was actually set.
        assert MyRemoteModel.api.option_for_name('cache_by_id') is True

        # We set an option, it will go into the current ApiOptionsGroup:
        MyRemoteModel.api.options.cache_by_id = False
        assert MyRemoteModel.api.options.cache_by_id is False

    # We throw away the previous option-group, to restore previously set options.
    assert MyRemoteModel.api.options.cache_by_id is True
