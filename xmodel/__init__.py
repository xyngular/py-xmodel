"""
Provides easy way to map dict to/from Full-Fledged 'JsonModel' object.

Also, an abstract RemoteModel interface used in xmodel-rest and xdynamo along with
some common code.

.. important:: Doc-comments in varius classes have out-of-date/broken refs; will be fixed soon.


.. important:: Docs Below Are OUT OF DATE!!!
    Most of the docs below belong int xmodel-rest and xdynamo.
    We will revamp them soon, and put more into the README.md as well.
    Currently, I would look at the docs above or README.md for info on how to use
    `JsonModel` class, which is the main-class of this library.


# Old Docs Below - Need A Lot Of Updates (ORM is old reference)

Used to be called the ORM library, that reference will be removed/updated as we get the docs
back in shape here soon. For now, they are older references that may not be entirely accurate
anymore.

## ORM Library Overview
[orm-library-overview]: #orm-library-overview

Library is intended to be used as a way to consolidate and standardize how we work with Model
classes  that can represent data from various different locations.  It can be used as an easy way
to communicate to/from our various places where we store models/information.

Right now this includes:

- Our own API's, such as Account, Auth and Founder's club API's.
- Dynamo tables.
- Big commerce
- Hubspot

Some reasons to use orm:

- The foundation for `xmodel-rest` library's Model objects.
    - Let's us easily map objects into/out of various rest API's.
    - Handles breaking up requests to get objects by id transparently into
        several sub-requests.
    - Does pagination for you automatically
    - Can lazily and prefetch0in-bulk child objects.
- Useful for accessing generally restful API's.
    - hubspot and bigcommerce projects use to to access their services api.
- Consistant interface, works the same wherever it's used
    (vs one-off methods inside the project doing the same things in diffrent ways).
- `xmodel.dynamo`: A library to map objects into Dynamo, we consolidated code from
    a few diffrent projects
    - Easily map objects into and out of Dynamo.
    - No need to duplicate code for things like paginating the results.
    - Add features or fix bugs in library, all other projects that use it benefit.
    - Can figure out best way to query dynamo for you automatically.

Some of the Models classes are kept directly in their respective projects (such as with hubspot).
In these cases, you can import that project as a Library to utilize it's Model's and to also
utilize it's other code/processes (which probably work closely with the Model's in question).

## Model Fields
[model-fields]: #model-fields

You can create your own Models. For a real example, see `hubspot.api.api.Contact`.

.. note:: (side-note: We should have put it in "hubspot.api.contact.Contact" or some such).

Here is a basic Model below that I will use for illustrative purposes.
It's a basic model that is using the standard functionality, with the only customization
being the `base_url` which is one of elements that construct's the url/path to it's endpoint.

### Basic Model Example
[model-fields]: #basic-model-example

>>> from xmodel import Field, BaseModel
>>> import datetime as dt
>>>
>>> class MyModel(
...    BaseModel,
...    base_url="accounts"  # <-- Class argument passed to underlying Structure object.
... ):
...    my_attribute: str  # <-- Automatically maps to API without extra effort
...    created_at: dt.datetime  # <-- Can auto-convert other types for you
...
...    other_attribute: int = Field(read_only=True)  # <-- Customize options
...
...    _will_not_map_to_api: int  # <-- Anything that begins with '_' won't map
...    also_will_not_map = None  # <-- No type-hint, 'Field' not auto-created

### Type-hints
[type-hints]: #type-hints

When Model classes are created, they will lazily find type-hinted attributes and determine
if a `xmodel.fields.Field` should automatically be created for them.
A `xmodel.fields.Field` is what is used by the sdk to map an attribute into it's corresponding
JSON field that is sent/retrieved from the API service.

You can specify other types, such as datetime/date types.
The SDK has a default converter in place for datetime/date types.
You can define other default converters, see [Type Converters](#type-converters) for more details.
Converters can also be used on a per-field basis via `xmodel.fields.Field.converter`.

The Model will enforce these type-hints, and use a converter if needed and one is available.

For example, if you try do do this:


>>> obj = MyModel()
>>> obj.my_attribute = 123
>>> obj.my_attribute
"123"


Notice how the output of the attribute is a str now and not an int. The Model will automatically
realize that it needs to be a string and try to convert it into a string for you.
If this is unsuccessful, it will raise an exception.

When this model is initialized from JSON, it does the same conversions. When grabbing this
object from the API it will automatically create the Model from the JSON it receives from API.

If you wish, you can also pass in your own dict structure when creating an object. The `Dict`
could have come from a JSON string.

>>> import json
>>> parsed_values = json.loads('{"my_attribute": 1234}')
>>> obj = MyModel(parsed_values)
>>> obj.my_attribute
"1234"

### Field Objects
[field-objects]: #field-objects

A `xmodel.base.model.BaseModel` has a set of `xmodel.fields.Field`'s that define how each
field will map to an attribute to/from JSON, which we currently use for all of our APIs.
See [JSON](#json) for more details.

You can get a list of `xmodel.fields.Field`'s via `xmodel.base.api.BaseApi.fields`.
This will allow you do iterate over all the fields the system will use when interacting
with JSON documents.

If you don't allocate a `xmodel.fields.Field` object directly on the Class at class definition
time we will auto-generate them for you. It will only do this for fields that have a type-hint.
If there is no type-hint, we won't auto-allocate a Field for it, and hence we won't
map it to/from the [JSON](#json), enforce the types or auto-convert them.
See [Type Hints](#type-hints).

#### Field Subclasses

You can have your own Field sub-class if you wish. To guarantee all auto-generated fields
use you class, you can set the type on `xmodel.base.structure.Structure.field_type`.

This needs to be set before any Model class that uses it is initialized.
You can do that by subclassing `xmodel.base.structure.Structure` and setting it at class
definition time. You then tell your BaseApi's to use your new structure.

For an example of doing all of this and also creating a custom `xmodel.fields.Field` subclass,
see `xmodel.dynamo.DynField`. We use this in our Dynamo-related code to put additional
options on model Fields that are only really useful for Dynamo models.

But the general idea is this:

>>> from xmodel import BaseStructure.....
# todo: Finish this example.

### JSON
[JSON]: #JSON

Right now all of our API's accept and return JSON.
The Models handle JSON natively.  This means you can also use Model's
to more easily deal with JSON without necessarily having to use any of the
`xmodel.rest.RestClient` aspects (send/receive).
This is what we did with Dynamo at first, we simply grabbed the json via `xmodel.base.api.json`
and send that directly into boto.
Later on we put together a special `xmodel.dynamo.DynClient`
to automatically send/receive it via boto (wraps boto).

Some the the reasons why it may be easier is due to the Model's in combination with the Fields.
You can easily define a mapping and automatic type-conversion with only a simple Model defintion.

.. hint:: What about API's that use a non-JSON format?
    If we ever have an API that has some other format, we would have a
    `xmodel.rest.RestClient` subclass that would handle mapping it to/from the JSON that
    we use on the Models. After RestClient gets a response, it would make a Dict out of it as if
    it got it from JSON and give that to the Model; and vic-versa (map from Dict into API format).


## Model.api

You can also export or update an existing `xmodel.base.model.BaseModel` object via methods
under a special attribute `xmodel.base.model.BaseModel.api`. This attribute has a reserved name
on every Model. This attribute is how the Model interfaces with the rest of the SDK.
That way the rest of the namespace for the Model attributes is available for use by Model subclass.

You can update an object via a dict from parse JSON via
`xmodel.base.api.BaseApi.update_from_json`.
Exporting JSON is easily done via `xmodel.base.api.BaseApi.json`.  Both of these methods
accept/return a `xmodel.types.JsonDict`, which is just a `dict` with `str`
keys and `Any` value.

`xmodel.base.model.BaseModel.api` is also how you can easily get/send objects to/from the
API service.


There are various ways to change/customize a model, keep reading further.

## BaseApi Class

One of the more important classes is `xmodel.base.api.BaseApi`.

For an overview of the class see [BaseApi Class Overview](./api.html#api-class-overview)
api.html#use-of-type-hints-for-changing-used-type

The class is a sort of central hub, it's where you can specify which types are allocated
for each sub-class. This is done via type-hints (typehints are read and used to allocate
correct class).

For more details see
[Use of Type Hints for Changing Type Used](./api.html#use-of-type-hints-for-changing-used-type)

### Type Converters
[type-converters]: #type-converters

The mapping of basic types to their converter function lives at
`xmodel.base.api.BaseApi.default_converters`. Normally you could customize this by
by subclassing `xmodel.base.api.BaseApi` with your own version for you Model(s).
You can also change it dynamically via adjusting `xmodel.base.api.BaseApi.default_converters`.

For the default converter map, see `xmodel.converters.DEFAULT_CONVERTERS`.

.. todo::
    ## This is how I want it to work in the future:

    Something to keep in mind is when the xmodel.base.api.BaseApi converts a type, and it needs
    a lookup a default converter it uses `xmodel.base.api.BaseApi.get_default_converter`.
    This method first checks it's self, and if type to convert is not in dict, it will check
    the superclasses default converters and so on until one is found.

    This means you can override a type conversion from a super class, or let it be used if it works
    as needed. One example of this is how hubspot uses a time-stamp integer to communicate time
    but most other systems use the normal ISO date/time format. So for the BaseApi class that all
    hubspot Model's use, they have the datetime converter overriden with a special Hubspot version.

You can also set a converter per-field via a callback on a `xmodel.fields.Field` object.

All converters have a calling convention, see `xmodel.fields.Converter` for details.

## RestClient Class

.. todo::: Section is unfinished, needs to be fleshed out more.

The config object that this api uses, can be customized per-model. All you have to
do is this to make it a different type::


    class MyClient():
        # Customize RestClient class in some way....
        my_custom_var: str = ConfigVar("MY_CUSTOM_ENVIRONMENTAL_VAR", "default")

    class MyApi(base.BaseApi[T]):
        client: MyClient

    class MyModel(base.model['MyModel'], endpoint_url="custom/path"):
        api: MyApi


The type-hints are enough to tell the system what types to use. They also will
tell any IDE in use about what type it should be, for type-completion.
So it's sort of doing double-duty to both tell IDE what it is and tell class what type to allocate
for the attribute when creating the class/object.

.. todo: Make changing default_converters work as expected [api-class vs api-instance];
    and then talk about te default type-converters here.

## Related Child Model's
[child-models]: #child-models

Going back to this example (from end of the [ORM Library Overview](#orm-library-overview) section):

>>> from some_lib.account import Account
>>> account = Account.api.get_via_id(3)
>>> print(account.account_no)
"3"

We will look at the this Account model more closely, it has a good example of using child objects.
Here is a simplified version of the Account Model:

```python
class PhoneNumber(AccountModel['PhoneNumber'], base_url="account/phone_numbers"):
    account_id: int
    number: str
    description: str
    is_active: bool

class Account(AccountModel['Account'], base_url="accounts"):
    # Configure a more specific api to use with the Accounts endpoint.
    api: AccountsEndpointApi[Account]

    # This is generally very useful for Account objects,
    # don't exclude updated_at by default.
    updated_at: dt.datetime = Field(exclude=False)

    account_no: str
    first_name: str
    last_name: str
    preferred_name: str
    preferred_phone_number: PhoneNumber
    preferred_address: Address
```

Here is an example of getting that objects preferred phone number:

>>> print(account.preferred_phone_number.number)
"8015551234"

By default `preferred_phone_number` is currently `None` (internally),
so the system knows that the `PhoneNumber` object has not been retrieved from the API yet.
It also knows the id for the preferred_phone_number. It's stored on the account object via
`preferred_phone_number_id` (via JSON from api).
The ORM stored this number internally when the object was fetched.

If you define a field like this in the object:

>>> preferred_phone_number_id: int

Instead of storing the number internally, it would store it here instead
(and you can get/set it as needed).
You can also get/set it by setting the `id` field of the child object, like so:

>>> obj: Account
>>> obj.preferred_phone_number.id
123456

If this `id` is known to the Model, meaning that it was fetched when the object was retrieved
from api (or set to something via `preferred_phone_number_id`); The sdk can lazily lookup
the object on demand when it's asked for.
It knows `preferred_phone_number` is a `PhoneNumber` model type
(and that it's also associated with a diffrent api endpoint) and it knows the id,
so it simply asks for it on demand/lazily via `ChildType.api.get_via_id`
(aka: `xmodel.base.api.BaseApi.get_via_id`).


It automatically takes this `preferred_phone_number_id`` and looks-up the preferred phone number
on the spot when you ask for it:

>>> obj.preferred_phone_number

This object is stored under `preferred_phone_number` so in the future it already has the object
when something asks for it again.

### Auto Prefetch Children
[auto-prefetch-children]: #auto-prefetch-children

You can also pre-fetch these child objects in bulk if you have a collection of model objects (such
as a `List` of `some_lib.account.Account`'s) via `xmodel.children.bulk_request_lazy_children`.
This is much more efficient if you have a lot of objects because it can grab many of the children
pre-request.

.. todo:: At some point the xmodel-rest will probably fetch many child objects lazily in bulk.
    When someone accesses one lazily, it could grab more for other Model objects that don't have
    their children fetched yet. We just put in a weak-ref cache, so using this we could
    find the ones that we have fetched in the past and and are still around.
    We could fetch their children too at the same time in the same request in bulk
    (ie: so we fetch original child requested, along with 50 more or so via a single request).


You can also have the xmodel do this automatically as it receives pages of objects via
`xmodel.options.ApiOptions.auto_get_child_objects` like so:

>>> Account.api.options.auto_get_child_objects = True

This sets this option for this Model type in the current `xinject.context.XContext`.
If you make a new XContext, and then throw the XContext away, it will revert these option changes.

>>> from xinject.context import XContext
>>>
>>> # Starts out as False....
>>> assert not Account.api.options.auto_get_child_objects
>>>
>>> with XContext():
...     Account.api.options.auto_get_child_objects = True
...     # Returned generator will 'remember' the options at time of creation
...     accounts_gen_with_children_pre_fetched = Account.api.get(top=100)
>>>
>>> # After XContext is gone, it reverts back to what it was before
>>> assert not Account.api.options.auto_get_child_objects

You can use this to grab all of the accounts. The below returns a Generator and will grab a page
of Account objects at a time, but still returning each object individually via the generator.

>>> [account.id for account in Account.api.get()]
[1, 2, 3, 4, 5, 118, 127, ...]

This is to help limit memory usage. It will also allow the sdk to asynchronously grab multiple
pages in the future [pre-fetch them] without changing the sdk's public interface to other projects.

.. todo:: Asynchronously pre-fetch pages of objects as the generator iterates though result set.

## Caching

There is a strong-ref and weak-ref caching system in the ORM you can take advantage of,
depending on the situation.

By default, they are both disabled.  They are explicitly an opt-in feature.

### Strong-Ref Caching

You can enable strong-ref caching in three ways currently:

-  Set it on directly on `xmodel.base.api.BaseApi.options.cache_by_id=True`

-  Set `cache_by_id=True` as one of the model classes options, like so:

>>> from xmodel import ApiOptions
>>> class MyModel(RestModel['MyModel'], api_options=ApiOptions(cache_by_id=True)):
...     account_id: int
...     number: str
...     description: str
...     is_active: bool


-  Via a subclass of a structure, such as `xmodel.rest.RestStructure`,
   and setting it's `xmodel.base.structure.BaseStructure.api_options` to a default set
   that are used by default for new Model sub-classes that use that Structure subclass.
   Here is an example:

>>> from typing import TypeVar
>>> from xmodel import Field
>>>
>>> F = TypeVar(name="F", bound=Field)
>>> class AlwaysEnableCacheByIDStructure(RestStructure[F]):
...     # todo: Have ability to set a default value for api_options on the Api class
...     #   Right now you can only set this on a Model or Structure class.
...     api_options = ApiOptions(cache_by_id=True)

The strong cache is useful for caching objects that almost never change.


### Weak-Ref Caching

Caching objects weakly is also disabled by default.

The weak-caching is nice, because there are situations where various object will reference
the same object. Take for instance order and order-lines.  The order-lines would have a
one-to-one relationship back to the order object, and there is no need to lookup the same
order object over and over again if you ask each order-line for it's order-object.

This is where the weak-cache can shine. The ORM can store temporary references to objects
by 'id' and check this cache to retrieve them later instead of having to do an actual
fetch-request.

Another place this can be useful is when query objects that are in a tree.
And objects parent could be referenced by several children.

You can enable weak-caching via the `xmodel.weak_cache_pool.WeakCachePool`.
`xmodel` imports this, so you can import it easily via:

>>> from xmodel import WeakCachePool

There is an enable property on it that you set to `True` to enable the caching.
See `xmodel.weak_cache_pool.WeakCachePool.enable`.

It's a `xinject.context.Dependency`, and so can be used like any other normal resource.
You can set the enable property on the current resource to make it more permently on.

>>> WeakCachePool.grab().enabled = True

Or you can temporarly enable it by creating a new `xmodel.weak_cache_pool.WeakCachePool`
object and activating it temporarily.

>>> from xmodel import WeakCachePool
>>> @WeakCachePool(enabled=True)
>>> def lambda_event_handler(event, context):
...    pass

The most recent WeakCachePool is the one that is used, and the weak refrences are stored inside it.
So when a WeakCachePool is deactivated and thrown-away, it will forgot anything that was weakly
cached in it. Same thing happens when activating a new WeakCachePool, it will not use the
previous pool for anything until the new WeakCachePool is deactivated.

This means, when you activate a new WeakCachePool, you are gurateed to always request new
objects instead of using previously cached ones.

"""

from .base import (
    BaseModel, BaseApi, BaseStructure
)
from .base.fields import Field, Converter
from .errors import XModelError
from .json import JsonModel
from .remote.weak_cache_pool import WeakCachePool


__all__ = [
    'BaseModel',
    'BaseApi',
    'BaseStructure',
    'Field',
    'Converter',
    'XModelError',
    'JsonModel'
]

__version__ = '0.7.0'
