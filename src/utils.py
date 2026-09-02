from __future__ import annotations

from typing import Iterable, Iterator, List, TypeVar

T = TypeVar("T")


def chunk_list(items: List[T], size: int) -> Iterator[List[T]]:
    for i in range(0, len(items), size):
        yield items[i : i + size]
