from types import CellType
from typing import AbstractSet, Any, Type

from memalot.base import MemalotObjectIds
from memalot.utils import get_full_type_name, get_objects


def _is_included_type(
    obj: Any,
    excluded_types: set[Type[Any]],
    included_type_names: AbstractSet[str],
    excluded_type_names: AbstractSet[str],
    include_object_ids: MemalotObjectIds,
    exclude_object_ids: MemalotObjectIds,
) -> bool:
    """
    Returns `True` if the object should be included, based on the inclusion and exclusion rules.
    """
    if (
        id(obj) == id(excluded_types)
        or id(obj) == id(included_type_names)
        or id(obj) == id(excluded_type_names)
        or id(obj) == id(include_object_ids)
        or id(obj) == id(exclude_object_ids)
        or id(obj) in exclude_object_ids
    ):
        return False
    if include_object_ids and id(obj) not in include_object_ids:
        return False
    if type(obj) in excluded_types:
        return False
    # Also exclude objects where an excluded type is referred to by a cell (closure)
    if isinstance(obj, CellType):
        try:
            if type(obj.cell_contents) in excluded_types:
                return False
        except Exception:  # pragma: nocover
            # If we can't get the contents of the cell, just carry on.
            pass
    type_name = get_full_type_name(type(obj))
    if included_type_names and not any(
        included_type in type_name for included_type in included_type_names
    ):
        return False
    if excluded_type_names and any(
        excluded_type in type_name for excluded_type in excluded_type_names
    ):
        return False
    return True


def filter_objects(
    objects: list[Any],
    excluded_types: set[Type[Any]],
    included_type_names: AbstractSet[str],
    excluded_type_names: AbstractSet[str],
    include_object_ids: MemalotObjectIds,
    exclude_object_ids: MemalotObjectIds,
) -> list[Any]:
    """
    Filters the provided `objects` according to a set of rules.

    Objects are returned in the same order they are passed in.

    :param objects: The objects to filter.
    :param excluded_types: Concrete Python types to exclude from the results.
    :param included_type_names: Substrings of fully-qualified type names that must match for
        objects to be included (when non-empty).
    :param excluded_type_names: Substrings of fully-qualified type names that cause objects to
        be excluded when any match.
    :param include_object_ids: If non-empty, only objects whose IDs are contained here will be
        included in the result.
    :param exclude_object_ids: Objects whose IDs are contained here will be excluded.
    :return: A new list containing the objects that satisfy the inclusion rules.
    """
    # Also exclude the IDs of the objects in the include_object_ids and exclude_object_ids lists
    exclude_object_ids = MemalotObjectIds(
        exclude_object_ids
        | {id(include_object_id) for include_object_id in include_object_ids}
        | {id(exclude_object_id) for exclude_object_id in exclude_object_ids}
    )
    exclude_dict_ids = set()
    return_objects = []
    for obj in objects:
        if _is_included_type(
            obj=obj,
            excluded_types=excluded_types,
            included_type_names=included_type_names,
            excluded_type_names=excluded_type_names,
            include_object_ids=include_object_ids,
            exclude_object_ids=exclude_object_ids,
        ):
            return_objects.append(obj)
        if _safe_hasattr(obj, "__dict__"):
            exclude_dict_ids.add(id(obj.__dict__))
    # Do another pass to exclude the dicts of the objects. This is necessary in Python versions
    # <3.12 because gc.get_objects() also returns the dicts of objects
    # as well as the objects themselves, which adds noise to the results.
    return [obj for obj in return_objects if id(obj) not in exclude_dict_ids]


def gc_and_get_objects(max_untracked_search_depth: int) -> list[Any]:
    """
    Performs a garbage collection and returns the in-memory, non-collectable objects.

    :param max_untracked_search_depth: The maximum depth to search for untracked objects.
    :return: A list of live objects currently reachable in the process.
    """
    # The utils.get_objects function takes care of garbage collection
    return get_objects(max_untracked_search_depth=max_untracked_search_depth)


def _safe_hasattr(obj: Any, attr_name: str) -> bool:
    try:
        return hasattr(obj, attr_name)
    except Exception:  # pragma: nocover
        # Some things don't like hasattr being called on them.
        return False
