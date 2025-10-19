import sys
from abc import ABC, abstractmethod
from collections import Counter, defaultdict
from datetime import datetime, timezone
from typing import Any, Callable, Dict, Generator, Tuple, Type
from weakref import WeakValueDictionary

import objsize
import referrers
from referrers import ReferrerGraph

from memalot.base import (
    ApproximateSize,
    MemalotCount,
    MemalotObjectId,
    MemalotObjectIds,
    MemalotSet,
    ObjectGetter,
    ObjectSignature,
)
from memalot.memory import (
    MemalotMemoryUsage,
    get_memory_usage,
)
from memalot.options import Options
from memalot.reports import (
    LeakSummary,
    ObjectDetails,
    TypeSummary,
)
from memalot.utils import (
    convert_graph_nodes,
    get_full_type_name,
    get_module_prefix,
    get_object_type_budgets,
)

# Names to replace in the referrer graph when using a decorator. This is obviously a
# bit brittle, but hopefully integration tests will catch any issues.
_DECORATOR_WRAPPER_NAME = "memalot_decorator_inner_wrapper"
_DECORATOR_ARGS_NAME = "memalot_decorator_inner_args"
_DECORATOR_KWARGS_NAME = "memalot_decorator_inner_kwargs"
_ARGS_SUBSTITUTION = f"{_DECORATOR_WRAPPER_NAME}.{_DECORATOR_ARGS_NAME}"
_KWARGS_SUBSTITUTION = f"{_DECORATOR_WRAPPER_NAME}.{_DECORATOR_KWARGS_NAME}"


class MemalotObjects:
    """
    A collection of objects.

    A summary can be produced via the `get_leak_summary` method, and object details can be
    obtained via the `generate_object_details` method.
    """

    def __init__(self, objects: list[Any]) -> None:
        self._objects = objects

    def get_leak_summary(self, iteration: MemalotCount, options: Options) -> LeakSummary:
        """
        Gets a summary of potential leaks.
        """
        type_counts = Counter(type(o) for o in self._objects)
        type_sizes: dict[Type[Any], ApproximateSize] = defaultdict(ApproximateSize)
        for obj in self._objects:
            obj_type = type(obj)
            if options.compute_size_in_leak_summary:
                type_sizes[obj_type] += _safe_shallow_size(obj)
        type_summaries = []
        for obj_type, count in type_counts.most_common(options.max_types_in_leak_summary):
            if options.compute_size_in_leak_summary:
                size = type_sizes[obj_type]
            else:
                size = None
            type_summaries.append(
                TypeSummary(
                    object_type=get_full_type_name(obj_type),
                    count=count,
                    shallow_size_bytes=size,
                )
            )
        return LeakSummary(
            iteration=int(iteration),
            type_summaries=type_summaries,
            max_types_in_summary=options.max_types_in_leak_summary,
        )

    def generate_object_details(
        self,
        excluded_from_referrers: list[int],
        options: Options,
        function_name: str | None = None,
        get_referrers_func: Callable[..., ReferrerGraph] = referrers.get_referrer_graph,
    ) -> Generator[ObjectDetails, None, None]:
        if not self._objects:
            return

        # Figure out how many objects to return per type based on options.max_referrers.
        # If we have more types than options.max_referrers, then we return one of each
        # of the most common types.
        type_counts = Counter(type(o) for o in self._objects)
        most_common_types = dict(type_counts.most_common(options.max_object_details))
        type_budgets = get_object_type_budgets(
            object_type_counts=most_common_types, total_budget=options.max_object_details
        )

        # Replace decorator wrapper names with the decorated function name.
        replacements = {}
        if function_name is not None:
            replacements[_ARGS_SUBSTITUTION] = f"{function_name} args"
            replacements[_KWARGS_SUBSTITUTION] = f"{function_name} kwargs"

        # If module prefixes are not specified, we use the module prefix of the caller
        # (not the direct caller of this method; the caller of Memalot)
        if options.referrers_module_prefixes is not None:
            module_prefixes = options.referrers_module_prefixes
        else:
            prefix = get_module_prefix()
            if prefix is not None:
                module_prefixes = {prefix}
            else:  # pragma: no cover
                module_prefixes = None

        # Return objects in order of the most common types.
        sorted_objects = sorted(self._objects, key=lambda x: type_counts[type(x)], reverse=True)
        # Get an iterator rather than using a for loop, so we can exclude it from the
        # referrers.
        iterator = iter(sorted_objects)
        current_counts_per_type: Counter[type] = Counter()
        str_func = options.str_func if options.str_func else self._safe_str
        try:
            while True:
                # Wrap the object in a list so we can exclude it
                obj_list = [next(iterator)]
                obj_type = type(obj_list[0])
                current_counts_per_type[obj_type] += 1
                if (
                    obj_type not in most_common_types
                    or current_counts_per_type[obj_type] > type_budgets[obj_type]
                ):
                    continue
                if options.check_referrers:
                    referrer_graph = get_referrers_func(
                        obj_list[0],
                        exclude_object_ids=[
                            id(sorted_objects),
                            id(iterator),
                            id(self._objects),
                            id(obj_list),
                        ]
                        + excluded_from_referrers,
                        max_depth=options.referrers_max_depth,
                        max_untracked_search_depth=options.referrers_max_untracked_search_depth,
                        timeout=options.referrers_search_timeout,
                        single_object_referrer_limit=options.single_object_referrer_limit,
                        module_prefixes=module_prefixes,
                    )
                else:
                    referrer_graph = None
                yield ObjectDetails(
                    deep_size_bytes=_safe_deep_size(obj_list[0]),
                    object_type_name=get_full_type_name(type(obj_list[0])),
                    object_id=id(obj_list[0]),
                    object_str=str_func(obj_list[0], options.str_max_length),
                    referrer_graph=(
                        convert_graph_nodes(
                            referrer_graph.to_networkx(),
                            replacements=replacements,
                        )
                        if referrer_graph
                        else None
                    ),
                    referrers_checked=options.check_referrers,
                )
        except StopIteration:
            pass

    def __len__(self) -> int:
        return len(self._objects)

    def _safe_str(self, obj: Any, truncate_at: int) -> str:
        try:
            str_repr = str(obj)
            if len(str_repr) > truncate_at:  # pragma: no cover
                str_repr = str_repr[:truncate_at] + f" … ({len(str_repr) - truncate_at} more chars)"
            return str_repr
        except Exception as e:
            # Some things don't like their string representation being obtained.
            return f"<Error when getting string representation: {str(e)}>"

    @property
    def objects(self) -> list[Any]:
        return self._objects

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, MemalotObjects):
            return False
        return self._objects == other._objects


class MemalotUsageSnapshot:
    """
    A snapshot of memory usage at a particular point in time.
    """

    def __init__(
        self,
        object_getter: ObjectGetter,
        filter_condition: Callable[[Any], bool] | None,
    ) -> None:
        objects = object_getter.get_objects()
        # We use a WeakValueDictionary here to avoid leaking memory. If an object disappears
        # from the dict then it has been garbage collected. If we later find an object with
        # the same ID, that is a different object.
        # However, some builtins (lists, dicts, etc.) do not support weak refs. For these,
        # we use ObjectSignature which allows objects to be compared using heuristics.
        self._weak_ref_objects: WeakValueDictionary[MemalotObjectId, Any] = WeakValueDictionary()
        self._non_weak_ref_objects: Dict[MemalotObjectId, ObjectSignature] = {}
        for obj in [obj for obj in objects if filter_condition is None or filter_condition(obj)]:
            object_id = MemalotObjectId(id(obj))
            try:
                self._weak_ref_objects[object_id] = obj
            except TypeError:
                # Some built-in objects do not support weak-refs (lists, dicts, etc).
                self._non_weak_ref_objects[object_id] = ObjectSignature(obj)
        # Get objects that were created during snapshot creation. These need to be excluded.
        # We just use a combination of object ID and type here to avoid creating more objects.
        # This isn't perfect, but it's probably good enough, particularly since most objects
        # created during snapshot creation will live as long as the snapshot itself.
        # Note: this will exclude some objects that were created in other threads during
        # snapshot creation, but we don't have a better solution for now, so this is called
        # out in the limitations section of the docs.
        (
            self._ids_during_snapshot_creation,
            self._types_during_snapshot_creation,
        ) = self._get_added_during_snapshot_creation(
            objects_before_snapshot_creation=objects,
            object_getter=object_getter,
        )

    def is_new_since_snapshot(self, obj: Any) -> bool:
        """
        Returns `True` if the given object is (probably) new since the snapshot was taken.

        We know for sure whether weakly referenceable objects were part of the snapshot. For
        non-weakly referenceable objects, we base this on heuristics, so we do not know for sure.
        """
        object_id = MemalotObjectId(id(obj))
        if (
            object_id in self._ids_during_snapshot_creation
            and type(obj) in self._types_during_snapshot_creation
        ):
            return False
        if object_id in self._weak_ref_objects:
            return False
        elif object_id in self._non_weak_ref_objects:
            return not self._non_weak_ref_objects[object_id].is_probably_same_object(obj)
        else:
            return True

    def is_in_snapshot(self, obj: Any) -> bool:
        """
        Returns `True` if the given object is in the snapshot.
        """
        object_id = MemalotObjectId(id(obj))
        return object_id in self._weak_ref_objects or (
            object_id in self._non_weak_ref_objects
            and self._non_weak_ref_objects[object_id].is_probably_same_object(obj)
        )

    def _get_added_during_snapshot_creation(
        self,
        objects_before_snapshot_creation: list[Any],
        object_getter: ObjectGetter,
    ) -> Tuple[MemalotObjectIds, MemalotSet]:
        """
        Gets object IDs of objects that were created during snapshot creation. These are internal
        machinery and need to be excluded.
        """
        # Note: there should not be any issue with using object IDs here, since the objects
        # in `objects_before_snapshot_creation` remain in scope while this function is called
        # and so the IDs of the objects in that list cannot be reused (they are not eligible
        # for garbage collection).
        id_set = MemalotObjectIds()
        type_set = MemalotSet()
        obj_object_ids = {id(obj) for obj in objects_before_snapshot_creation}
        for new_obj in object_getter.get_objects():
            new_obj_id = id(new_obj)
            if new_obj_id not in obj_object_ids:
                id_set.add(MemalotObjectId(new_obj_id))
                type_set.add(type(new_obj))
        id_set_id = MemalotObjectId(id(id_set))
        id_set.add(id_set_id)
        type_set.add(type(id_set_id))
        type_set_id = MemalotObjectId(id(type_set))
        id_set.add(type_set_id)
        type_set.add(type(type_set_id))
        return id_set, type_set

    @property
    def active_object_ids(self) -> MemalotObjectIds:
        """
        Returns the IDs of all objects in the snapshot. This includes objects that are
        weakly-referenceable and have not been garbage collected, and *all* objects that are
        not weakly-referenceable.

        Do not use this to determine whether an object is in the snapshot or not - use
        `is_new_since_snapshot()` for that.
        """
        return MemalotObjectIds(
            set(self._weak_ref_objects.keys()) | set(self._non_weak_ref_objects.keys())
        )


class MemoryUsageProvider(ABC):
    @abstractmethod
    def rotate_memory_usage(  # pragma: no cover
        self, iteration: MemalotCount
    ) -> Tuple[MemalotMemoryUsage | None, MemalotMemoryUsage]:
        pass


class MemalotSnapshotManager(MemoryUsageProvider):
    """
    Manages one or more memory snapshots and allows a report to be generated based on
    these.
    """

    def __init__(
        self,
        report_id: str,
    ) -> None:
        self._report_id = report_id

        # Mutable state
        self._most_recent_snapshot: MemalotUsageSnapshot | None = None
        self._most_recent_snapshot_time: datetime | None = None
        self._added_during_snapshot_creation: MemalotObjectIds | None = None
        self._most_recent_reported_usage: MemalotMemoryUsage | None = None

    def generate_new_snapshot(
        self,
        object_getter: ObjectGetter,
        since_snapshot: MemalotUsageSnapshot | None,
    ) -> None:
        if since_snapshot:
            filter_condition = since_snapshot.is_new_since_snapshot
        else:
            filter_condition = None
        self._most_recent_snapshot = MemalotUsageSnapshot(
            object_getter=object_getter, filter_condition=filter_condition
        )
        self._most_recent_snapshot_time = datetime.now(timezone.utc)

    def clear_snapshots(self) -> None:
        self._most_recent_snapshot = None
        self._most_recent_snapshot_time = None

    def rotate_memory_usage(
        self, iteration: MemalotCount
    ) -> Tuple[MemalotMemoryUsage | None, MemalotMemoryUsage]:
        old_usage = self._most_recent_reported_usage
        self._most_recent_reported_usage = get_memory_usage(iteration=iteration)
        return old_usage, self._most_recent_reported_usage

    @property
    def report_id(self) -> str:
        return self._report_id

    @property
    def most_recent_snapshot(self) -> MemalotUsageSnapshot | None:
        return self._most_recent_snapshot

    @property
    def most_recent_snapshot_time(self) -> datetime | None:
        return self._most_recent_snapshot_time

    @property
    def most_recent_reported_usage(self) -> MemalotMemoryUsage | None:
        return self._most_recent_reported_usage


def _safe_deep_size(obj: Any) -> ApproximateSize:
    """
    Gets the approximate deep size of an object. If an error is encountered getting
    the deep size, then an `ApproximateSize` where the upper bound is unknown is returned.
    """
    try:
        return ApproximateSize(
            approx_size=objsize.get_deep_size(obj),
        )
    except Exception:  # pragma: no cover
        return ApproximateSize(approx_size=0, upper_bound_known=False)


def _safe_shallow_size(obj: Any) -> ApproximateSize:
    """
    Gets the approximate shallow size of an object. If an error is encountered getting
    the deep size, then an `ApproximateSize` where the upper bound is unknown is returned.
    """
    try:
        return ApproximateSize(
            approx_size=sys.getsizeof(obj),
        )
    except Exception:  # pragma: no cover
        return ApproximateSize(approx_size=0, upper_bound_known=False)
