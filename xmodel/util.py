from typing import Union, Iterator, Iterable, TypeVar
from xloop import xloop, DEFAULT_NOT_ITERATE

T = TypeVar("T")


def loop(*args: Union[Iterable[T], T]) -> Iterator[T]:
    return xloop(*args, not_iterate=[*DEFAULT_NOT_ITERATE, dict])
