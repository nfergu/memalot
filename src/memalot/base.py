import collections
from abc import ABC, abstractmethod
from typing import Any, Generic, Iterable, Iterator, List, TypeVar

from pydantic.dataclasses import dataclass

_HASHABLE_TYPE = collections.abc.Hashable


class MemalotInt(int):
    """
    An int. This is used in preference to int so that it can be excluded from reports.
    """

    pass


class MemalotCount(int):
    """
    A count. This is used in preference to int so that it can be excluded from reports.
    """

    pass


class MemalotObjectId(int):
    """
    An object ID. This is used in preference to int so that it can be excluded from reports.
    """


class MemalotObjectIds(set[int]):
    """
    A set of object IDs. This is used in preference to a set so that it can be excluded
    from reports.
    """


class MemalotList(list[Any]):
    """
    A list. This is used in preference to a regular list so that it can be excluded from reports.
    """


class MemalotSet(set[Any]):
    """
    A set. This is used in preference to a regular list so that it can be excluded from reports.
    """


class ObjectSignature:
    """
    An object signature that uses heuristics to determine whether two objects are the same
    or not.

    Objects cannot be compared by their ID alone, since after objects are garbage collected
    their IDs may be reused (from the Python docs: "objects with non-overlapping lifetimes may
    have the same id() value") so this class uses the object's type and hash as well as the
    object ID. If objects are not hashable, then only the object ID and type are used.
    """

    def __init__(self, obj: Any) -> None:
        self._id = MemalotObjectId(id(obj))
        self._type = type(obj)
        self._signature = self._get_hash(obj)

    def _get_hash(self, obj: Any) -> MemalotInt:
        try:
            return self._hash(obj)
        except Exception:
            pass
        # Fall-back to using the object ID if the object is not hashable (or another
        # error occurs getting the hash). This isn't great, since it won't work for collections
        # like dicts and lists, but there's probably not much we can do about that
        # (they're mutable anyway, so comparing their contents won't help us much).
        return MemalotInt(id(self))

    def _hash(self, obj: Any) -> MemalotInt:
        return MemalotInt(hash(obj))

    def is_probably_same_object(self, obj: Any) -> bool:
        return (
            MemalotObjectId(id(obj)) == self._id and type(obj) is self._type and self._get_hash(obj)
        ) == self._signature


@dataclass
class ApproximateSize:
    """
    Represents an approximate uncertain size. That is, a size where the lower bound is known
    approximately, and the upper bound may not be known at all.
    """

    approx_size: int = 0
    """
    If `upper_bound_known` is `True`, then this is the approximate size. If `upper_bound_known` is
    `False`, then this is the approximate lower bound of the size.
    """

    upper_bound_known: bool = True
    """
    Whether the upper bound of the size is known.
    """

    def __add__(self, other: "ApproximateSize") -> "ApproximateSize":
        return ApproximateSize(
            self.approx_size + other.approx_size, self.upper_bound_known and other.upper_bound_known
        )

    @property
    def prefix(self) -> str:
        if self.upper_bound_known:
            return "~"
        else:
            return ">="

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, ApproximateSize):
            return False
        return (
            self.approx_size == other.approx_size
            and self.upper_bound_known == other.upper_bound_known
        )

    def __hash__(self) -> int:
        return hash((self.approx_size, self.upper_bound_known))


T = TypeVar("T")


class CachingIterable(Generic[T]):
    """
    Iterable that caches the underlying iterable.

    Note: this class is *not* thread-safe!
    """

    def __init__(self, iterable: Iterable[T]):
        self._iterator = iter(iterable)
        self._cache: List[T] = []

    def __iter__(self) -> Iterator[T]:
        for item in self._cache:
            yield item
        try:
            while True:
                item = next(self._iterator)
                self._cache.append(item)
                yield item
        except StopIteration:
            pass

    def __len__(self) -> int:
        # Consume the entire iterator to get the length
        # We need to exhaust the iterator without calling list(self) to avoid recursion
        for _ in self:
            pass
        return len(self._cache)


@dataclass
class ReferrerNode:
    """
    Represents a node in a referrer graph.

    This represents something that refers to other objects. For example, a local variable,
    an instance attribute, a collection, or a global variable. In addition, objects themselves
    can be represented in the graph as nodes.
    """

    id: int
    """
    A unique ID for the node.
    """

    name: str
    """
    A descriptive (human-readable) name for the node.
    """

    object_id: int
    """
    The object ID that the node represents. Note that this is not a unique ID, since multiple
    nodes can represent the same object. For example, an object may be represented by
    (potentially multiple) instance attributes, and by the object itself.
    """

    referent_ids: list[int]
    """
    The IDs of the referents of the node. These are the nodes that this node refers to.

    For example, if the node represents a local variable, then the referent is the object
    that the variable refers to.
    """


@dataclass
class ReferrerGraph:
    """
    A graph of referrers.

    This graph is used to represent the referrers (both direct and indirect) of one or more
    target objects.
    """

    target_ids: set[int]
    """
    IDs of the target objects. These are the objects that we have found the referrers of.
    """

    root_ids: set[int]
    """
    IDs of the root nodes. These are nodes that have no referrers.
    """

    graph_nodes: list[ReferrerNode]
    """
    The nodes in the graph.

    Edges are represented by the `referent_ids` attribute of the nodes.
    """

    def __len__(self) -> int:
        return len(self.graph_nodes)


class ObjectGetter(ABC):
    """
    Gets objects in memory.
    """

    @abstractmethod
    def get_objects(self) -> list[Any]:
        """
        Get filtered objects by calling the underlying function and applying filters.
        """
        pass  # pragma: no cover
