import gc
import weakref
from collections import Counter
from dataclasses import replace
from typing import Any, Tuple
from unittest.mock import ANY, MagicMock

import pytest
from networkx.classes import DiGraph
from pytest_mock import MockerFixture
from referrers import ReferrerGraph, ReferrerGraphNode

from memalot.base import ApproximateSize, MemalotCount
from memalot.base import ReferrerGraph as MyReferrerGraph
from memalot.memory import MemalotMemoryUsage
from memalot.monitors import FilteringObjectGetter
from memalot.options import Options
from memalot.reports import LeakSummary, TypeSummary
from memalot.snapshots import MemalotObjects, MemalotSnapshotManager, MemalotUsageSnapshot
from tests.utils_for_testing import FixedObjectGetter, create_mock

_NUM_SAME_ID_ATTEMPTS = 100


class CustomObject:
    """
    A custom object class for testing that supports weak references.
    """

    def __init__(self, value: str) -> None:
        self.value = value

    def __eq__(self, other: object) -> bool:
        return isinstance(other, CustomObject) and self.value == other.value

    def __repr__(self) -> str:
        return f"CustomObject(value='{self.value}')"


class NonWeakRefObject:
    """
    A custom object that does not support weak references.
    """

    __slots__ = ["value"]

    def __init__(self, value: str) -> None:
        self.value = value

    def __eq__(self, other: object) -> bool:
        return isinstance(other, NonWeakRefObject) and self.value == other.value

    def __hash__(self) -> int:
        return hash(self.value)


class NonWeakRefIntObject:
    """
    A custom object containing an int that does not support weak references.
    """

    __slots__ = ["value"]

    def __init__(self, value: int) -> None:
        self.value = value

    def __eq__(self, other: object) -> bool:
        return isinstance(other, NonWeakRefIntObject) and self.value == other.value

    def __hash__(self) -> int:
        return hash(self.value)


@pytest.fixture(name="custom_objects")
def _custom_objects_fixture() -> list[CustomObject]:
    """
    Provides a list of custom objects for testing.
    """
    return [CustomObject("test1"), CustomObject("test2"), CustomObject("test3")]


@pytest.fixture(name="builtin_objects")
def _builtin_objects_fixture() -> list[object]:
    """
    Provides a list of builtin objects that don't support weak references.
    """
    return [[], {}, "string", 42, [1, 2, 3], {"key": "value"}]


@pytest.fixture(name="mixed_objects")
def _mixed_objects_fixture(
    custom_objects: list[CustomObject], builtin_objects: list[object]
) -> list[object]:
    """
    Provides a mixed list of objects with and without weak reference support.
    """
    return custom_objects + builtin_objects


@pytest.fixture(name="default_options")
def _default_options_fixture() -> Options:
    """
    Provides default Options instance for testing.
    """
    return Options()


@pytest.fixture(name="diff_objects")
def _diff_objects_fixture() -> list[object]:
    """
    Provides objects for creating MemalotUsageDiff instances.
    """
    return [
        CustomObject("diff1"),
        CustomObject("diff2"),
        [1, 2, 3],
        {"key": "value"},
        "test_string",
    ]


@pytest.fixture(name="test_memory_usage")
def _test_memory_usage_fixture() -> MemalotMemoryUsage:
    """
    Provides a MemoryUsage instance for testing.
    """
    return MemalotMemoryUsage(
        current_rss_bytes=1024000,
        peak_rss_bytes=2048000,
        system_percent_used=25.5,
        iteration_number=1,
    )


class TestMemalotUsageDiff:
    """
    Tests for the `MemalotUsageDiff` class.
    """

    def test_with_empty_list(self, default_options: Options) -> None:
        """
        Tests that MemalotUsageDiff works with an empty object list.
        """
        diff = MemalotObjects([])
        assert len(diff) == 0
        summary = diff.get_leak_summary(iteration=MemalotCount(4), options=default_options)
        assert summary == LeakSummary(
            iteration=4,
            type_summaries=[],
            max_types_in_summary=500,
        )
        object_details_list = list(diff.generate_object_details([], default_options))
        assert object_details_list == []

    @pytest.mark.parametrize("compute_size", [True, False])
    @pytest.mark.parametrize("module_prefixes", [{"override_prefix."}, None])
    def test_with_multiple_objects(
        self, default_options: Options, compute_size: bool, module_prefixes: set[str] | None
    ) -> None:
        """
        Tests that MemalotUsageDiff works with multiple objects of different types.
        """
        default_options = replace(
            default_options,
            compute_size_in_leak_summary=compute_size,
            referrers_module_prefixes=module_prefixes,
        )
        mock_referrer_graph = create_mock(spec=ReferrerGraph)
        mock_get_referrers = MagicMock(return_value=mock_referrer_graph)
        mock_networkx_graph = DiGraph()
        mock_networkx_graph.add_node(ReferrerGraphNode(name="root", id=1001, type="local"))
        mock_networkx_graph.add_node(ReferrerGraphNode(name="child", id=1002, type="attr"))
        mock_referrer_graph.to_networkx.return_value = mock_networkx_graph

        objects = [
            CustomObject("obj1"),
            CustomObject("obj2"),  # 2 CustomObjects
            [1, 2],
            [3, 4],
            [5, 6],  # 3 lists
            {"a": 1},
            {"b": 2},  # 2 dicts
            "string1",
            "string2",
            "string3",
            "string4",  # 4 strings
        ]
        diff = MemalotObjects(objects)

        summary = diff.get_leak_summary(iteration=MemalotCount(4), options=default_options)
        actuals = summary.type_summaries
        assert summary == LeakSummary(
            iteration=4,
            type_summaries=[
                TypeSummary(
                    object_type="builtins.str",
                    count=4,
                    shallow_size_bytes=actuals[0].shallow_size_bytes,  # Sizes not known
                ),
                TypeSummary(
                    object_type="builtins.list",
                    count=3,
                    shallow_size_bytes=actuals[1].shallow_size_bytes,  # Sizes not known
                ),
                TypeSummary(
                    object_type="tests.test_snapshots.CustomObject",
                    count=2,
                    shallow_size_bytes=actuals[2].shallow_size_bytes,  # Sizes not known
                ),
                TypeSummary(
                    object_type="builtins.dict",
                    count=2,
                    shallow_size_bytes=actuals[3].shallow_size_bytes,  # Sizes not known
                ),
            ],
            max_types_in_summary=500,
        )

        if compute_size:
            assert all(
                type_summary.shallow_size_bytes is not None
                for type_summary in summary.type_summaries
            )
        else:
            assert all(
                type_summary.shallow_size_bytes is None for type_summary in summary.type_summaries
            )

        object_details_list = list(
            diff.generate_object_details(
                [],
                default_options,
                get_referrers_func=mock_get_referrers,
            )
        )

        assert mock_get_referrers.call_count == 11  # One call per object
        # Check that the correct arguments were passed. We don't check every object here.
        mock_get_referrers.assert_any_call(
            CustomObject("obj1"),
            exclude_object_ids=ANY,
            max_depth=default_options.referrers_max_depth,
            max_untracked_search_depth=default_options.referrers_max_untracked_search_depth,
            timeout=default_options.referrers_search_timeout,
            single_object_referrer_limit=default_options.single_object_referrer_limit,
            module_prefixes=module_prefixes if module_prefixes is not None else {"tests."},
        )

        type_names = [object_details.object_type_name for object_details in object_details_list]
        assert set(type_names) == {
            "tests.test_snapshots.CustomObject",
            "builtins.list",
            "builtins.dict",
            "builtins.str",
        }
        object_ids = [object_details.object_id for object_details in object_details_list]
        assert set(object_ids) == {id(obj) for obj in objects}
        approx_sizes = [object_details.deep_size_bytes for object_details in object_details_list]
        # We don't know the exact sizes, but there should be 11 sizes (one per object)
        assert len(approx_sizes) == 11
        assert all(isinstance(size, ApproximateSize) for size in approx_sizes)
        referrer_graphs = [object_details.referrer_graph for object_details in object_details_list]
        for graph in referrer_graphs:
            assert isinstance(graph, MyReferrerGraph)
        # Check that each graph has the expected structure
        assert all(len(graph.graph_nodes) == 2 for graph in referrer_graphs if graph is not None)
        strings = [object_details.object_str for object_details in object_details_list]
        assert set(strings) == {
            "CustomObject(value='obj1')",
            "CustomObject(value='obj2')",
            "[1, 2]",
            "[3, 4]",
            "[5, 6]",
            "string1",
            "string2",
            "string3",
            "string4",
            "{'a': 1}",
            "{'b': 2}",
        }

    def test_ordering_by_type_count(self) -> None:
        """
        Tests that generate_object_details returns ObjectDetails instances ordered by the number
        of occurrences of each type, with the most frequent type first.
        """
        mock_referrer_graph = create_mock(spec=ReferrerGraph)
        mock_get_referrers = MagicMock(return_value=mock_referrer_graph)
        mock_networkx_graph = DiGraph()
        mock_networkx_graph.add_node(ReferrerGraphNode(name="root", id=1001, type="local"))
        mock_referrer_graph.to_networkx.return_value = mock_networkx_graph

        # Create objects with different type frequencies:
        # - 5 strings (most frequent)
        # - 3 CustomObjects (second most frequent)
        # - 2 lists (third most frequent)
        # - 1 dict (least frequent)
        objects = [
            "string1",
            "string2",
            "string3",
            "string4",
            "string5",  # 5 strings
            CustomObject("obj1"),
            CustomObject("obj2"),
            CustomObject("obj3"),  # 3 CustomObjects
            [1, 2],
            [3, 4],  # 2 lists
            {"key": "value"},  # 1 dict
        ]
        diff = MemalotObjects(objects)

        # Set max_object_details high enough to include all objects
        high_limit_options = Options(max_object_details=100)

        object_details_list = list(
            diff.generate_object_details(
                [],
                high_limit_options,
                get_referrers_func=mock_get_referrers,
            )
        )

        # Extract the type names in the order they were yielded
        type_names_in_order = [obj_details.object_type_name for obj_details in object_details_list]

        # Verify that objects are grouped by type and types appear in frequency order
        # Expected order: str (5), CustomObject (3), list (2), dict (1)
        expected_first_type = "builtins.str"  # Most frequent (5 occurrences)
        expected_second_type = "tests.test_snapshots.CustomObject"  # Second most frequent (3)
        expected_third_type = "builtins.list"  # Third most frequent (2)
        expected_fourth_type = "builtins.dict"  # Least frequent (1)

        # Find first occurrence of each type to check ordering
        str_first_index = type_names_in_order.index(expected_first_type)
        custom_obj_first_index = type_names_in_order.index(expected_second_type)
        list_first_index = type_names_in_order.index(expected_third_type)
        dict_first_index = type_names_in_order.index(expected_fourth_type)

        # Assert that types appear in the correct order (most frequent first)
        assert str_first_index < custom_obj_first_index
        assert custom_obj_first_index < list_first_index
        assert list_first_index < dict_first_index

        # Count objects by type to verify all are included
        type_counts = Counter(type_names_in_order)
        assert type_counts[expected_first_type] == 5
        assert type_counts[expected_second_type] == 3
        assert type_counts[expected_third_type] == 2
        assert type_counts[expected_fourth_type] == 1

    def test_with_max_object_details_limit(self, default_options: Options) -> None:
        """
        Tests that MemalotUsageDiff respects max_object_details and returns
        the correct subset of objects.
        """
        mock_referrer_graph = create_mock(spec=ReferrerGraph)
        mock_get_referrers = MagicMock(return_value=mock_referrer_graph)
        mock_networkx_graph = DiGraph()
        mock_networkx_graph.add_node(ReferrerGraphNode(name="root", id=1001, type="local"))
        mock_referrer_graph.to_networkx.return_value = mock_networkx_graph

        # Create many objects of different types - more than max_object_details
        objects: list[Any] = []
        # 10 CustomObjects
        for i in range(10):
            objects.append(CustomObject(f"obj{i}"))
        # 8 lists
        for i in range(8):
            objects.append([i, i + 1])
        # 6 dicts
        for i in range(6):
            objects.append({f"key{i}": f"value{i}"})
        # 4 strings
        for i in range(4):
            objects.append(f"string{i}")

        diff = MemalotObjects(objects)

        # Set max_object_details to 10 (less than total 28 objects)
        limited_options = Options(max_object_details=10)

        # With 4 types and max_object_details=10, we should get at least 2 objects per type (
        # 10//4=2) with the remainder going to the most frequent types
        object_details_list = list(
            diff.generate_object_details(
                [],
                limited_options,
                get_referrers_func=mock_get_referrers,
            )
        )

        # Should have exactly 10 objects (2 per type, plus remainder)
        assert len(object_details_list) == 10

        # Count objects by type
        type_counts = Counter(obj.object_type_name for obj in object_details_list)
        assert type_counts["tests.test_snapshots.CustomObject"] == 3
        assert type_counts["builtins.list"] == 3
        assert type_counts["builtins.dict"] == 2
        assert type_counts["builtins.str"] == 2

        # Verify that referrers were obtained for each returned object
        assert mock_get_referrers.call_count == 10

        # Verify that referrers_checked is True for all objects
        # (since check_referrers=True by default)
        for obj_details in object_details_list:
            assert obj_details.referrers_checked is True

    def test_with_check_referrers_false(self, default_options: Options) -> None:
        """
        Tests that MemalotUsageDiff works correctly when check_referrers is False.
        """
        mock_get_referrers = MagicMock()

        objects = [
            CustomObject("obj1"),
            [1, 2, 3],
            {"key": "value"},
            "test_string",
        ]
        diff = MemalotObjects(objects)

        no_referrers_options = Options(check_referrers=False)

        object_details_list = list(
            diff.generate_object_details(
                [],
                no_referrers_options,
                get_referrers_func=mock_get_referrers,
            )
        )

        # Should have all 4 objects
        assert len(object_details_list) == 4

        # Referrers function should never be called
        mock_get_referrers.assert_not_called()

        # All referrer_graph fields should be None and referrers_checked should be False
        for obj_details in object_details_list:
            assert obj_details.referrer_graph is None
            assert obj_details.referrers_checked is False

        # Other fields should still be populated correctly
        object_ids = [obj_details.object_id for obj_details in object_details_list]
        assert set(object_ids) == {id(obj) for obj in objects}

        strings = [obj_details.object_str for obj_details in object_details_list]
        assert set(strings) == {
            "CustomObject(value='obj1')",
            "[1, 2, 3]",
            "{'key': 'value'}",
            "test_string",
        }

    def test_with_object_str_exception(self, default_options: Options) -> None:
        """
        Tests that MemalotUsageDiff handles objects that raise exceptions when getting string
        representation.
        """

        class ExceptionObject:
            """
            An object that raises an exception when str() is called.
            """

            def __str__(self) -> str:
                raise ValueError("Cannot convert to string")

        mock_referrer_graph = create_mock(spec=ReferrerGraph)
        mock_get_referrers = MagicMock(return_value=mock_referrer_graph)
        mock_networkx_graph = DiGraph()
        mock_networkx_graph.add_node(ReferrerGraphNode(name="root", id=1001, type="local"))
        mock_referrer_graph.to_networkx.return_value = mock_networkx_graph

        exception_obj = ExceptionObject()
        normal_obj = CustomObject("normal")
        objects = [exception_obj, normal_obj]

        diff = MemalotObjects(objects)

        object_details_list = list(
            diff.generate_object_details(
                [],
                default_options,
                get_referrers_func=mock_get_referrers,
            )
        )

        assert len(object_details_list) == 2

        # Find the object details for the exception object
        exception_details = None
        normal_details = None
        for obj_details in object_details_list:
            if obj_details.object_id == id(exception_obj):
                exception_details = obj_details
            elif obj_details.object_id == id(normal_obj):
                normal_details = obj_details

        assert exception_details is not None
        assert normal_details is not None

        # The exception object should have an error message in its string representation
        assert "Error when getting string representation" in exception_details.object_str
        assert "Cannot convert to string" in exception_details.object_str

        # The normal object should have its normal string representation
        assert normal_details.object_str == "CustomObject(value='normal')"

    def test_with_custom_str_func(self, default_options: Options) -> None:
        """
        Tests that MemalotUsageDiff uses custom str_func when provided in options.
        """

        def custom_str_func(obj: Any, max_length: int) -> str:
            """
            A custom string function that adds a prefix.
            """
            return f"CUSTOM: {str(obj)[:max_length]}"

        mock_referrer_graph = create_mock(spec=ReferrerGraph)
        mock_get_referrers = MagicMock(return_value=mock_referrer_graph)
        mock_networkx_graph = DiGraph()
        mock_networkx_graph.add_node(ReferrerGraphNode(name="root", id=1001, type="local"))
        mock_referrer_graph.to_networkx.return_value = mock_networkx_graph

        objects = [
            CustomObject("obj1"),
            [1, 2, 3],
            {"key": "value"},
        ]
        diff = MemalotObjects(objects)

        custom_options = Options(str_func=custom_str_func)

        object_details_list = list(
            diff.generate_object_details(
                [],
                custom_options,
                get_referrers_func=mock_get_referrers,
            )
        )

        assert len(object_details_list) == 3

        # All string representations should have the custom prefix
        strings = [obj_details.object_str for obj_details in object_details_list]
        assert all(s.startswith("CUSTOM: ") for s in strings)

        # Check specific expected strings
        expected_strings = {
            "CUSTOM: CustomObject(value='obj1')",
            "CUSTOM: [1, 2, 3]",
            "CUSTOM: {'key': 'value'}",
        }
        assert set(strings) == expected_strings

    def test_eq_with_equal_objects(self) -> None:
        """
        Tests that two MemalotObjects instances with equal but different object lists are equal.
        """
        obj1 = CustomObject("test")
        obj2 = [1, 2, 3]
        objects1 = [obj1, obj2]
        objects2 = [obj1, obj2]  # Same objects, same order
        diff1 = MemalotObjects(objects1)
        diff2 = MemalotObjects(objects2)
        assert diff1 == diff2

    def test_eq_with_different_objects(self) -> None:
        """
        Tests that two MemalotObjects instances with different objects are not equal.
        """
        objects1 = [CustomObject("test1"), [1, 2, 3]]
        objects2 = [CustomObject("test2"), [4, 5, 6]]
        diff1 = MemalotObjects(objects1)
        diff2 = MemalotObjects(objects2)
        assert diff1 != diff2

    def test_eq_with_wrong_type(self) -> None:
        """
        Tests that comparing a MemalotObject instance with a string returns False.
        """
        objects1 = [CustomObject("test1"), [1, 2, 3]]
        diff1 = MemalotObjects(objects1)
        assert diff1 != "diff2"

    def test_generate_object_details_with_function_name(self, default_options: Options) -> None:
        """
        Tests that generate_object_details correctly handles function_name parameter.
        """
        # Create a mock referrer graph with nodes that have the decorator wrapper names
        mock_referrer_graph = create_mock(spec=ReferrerGraph)
        mock_get_referrers = MagicMock(return_value=mock_referrer_graph)
        mock_networkx_graph = DiGraph()

        # Add nodes with the specific names that should be replaced
        mock_networkx_graph.add_node(
            ReferrerGraphNode(
                name="memalot_decorator_inner_wrapper.memalot_decorator_inner_args",
                id=1001,
                type="local",
            )
        )
        mock_networkx_graph.add_node(
            ReferrerGraphNode(
                name="memalot_decorator_inner_wrapper.memalot_decorator_inner_kwargs",
                id=1002,
                type="local",
            )
        )
        mock_referrer_graph.to_networkx.return_value = mock_networkx_graph

        objects = [CustomObject("test")]
        diff = MemalotObjects(objects)

        object_details_list = list(
            diff.generate_object_details(
                [],
                default_options,
                function_name="my_test_function",
                get_referrers_func=mock_get_referrers,
            )
        )

        # Should have 1 object
        assert len(object_details_list) == 1
        obj_details = object_details_list[0]

        # Verify the object details
        assert obj_details.object_id == id(objects[0])

        # Verify the referrer graph has the replaced names
        assert obj_details.referrer_graph is not None
        referrer_names = [node.name for node in obj_details.referrer_graph.graph_nodes]

        # The names should have been replaced with the function name
        assert "my_test_function args" in referrer_names
        assert "my_test_function kwargs" in referrer_names

        # The original decorator wrapper names should not be present
        assert "memalot_decorator_inner_wrapper.memalot_decorator_inner_args" not in referrer_names
        assert (
            "memalot_decorator_inner_wrapper.memalot_decorator_inner_kwargs" not in referrer_names
        )


class TestMemalotUsageSnapshot:
    """
    Tests for the `MemalotUsageSnapshot` class.
    """

    def test_is_new_since_snapshot(self, default_options: Options) -> None:
        """
        Tests that new objects are correctly identified as new.
        """
        custom_objects = [CustomObject("test1"), CustomObject("test2"), CustomObject("test3")]
        # Double check that weak references can be created
        for obj in custom_objects:
            weakref.ref(obj)
        builtin_objects: list[object] = [[1, 2, 3], {"a": 1}, "string"]
        mixed_objects: list[object] = custom_objects + builtin_objects

        snapshot = MemalotUsageSnapshot(
            object_getter=FixedObjectGetter(mixed_objects),
            filter_condition=None,
        )

        # Check that existing objects are not considered new
        for mixed_obj in mixed_objects:
            assert not snapshot.is_new_since_snapshot(mixed_obj)

        # Check that new objects with the same values are considered new.
        # We can't test all of them as some are interned (like small integers and
        # strings).
        assert snapshot.is_new_since_snapshot(CustomObject("test1"))
        assert snapshot.is_new_since_snapshot([1, 2, 3])
        assert snapshot.is_new_since_snapshot({"a": 1})

        # Check that new objects with different values are considered new
        assert snapshot.is_new_since_snapshot(CustomObject("new_object"))
        assert snapshot.is_new_since_snapshot([1, 2, 3, 4])
        assert snapshot.is_new_since_snapshot({"new": "dict"})

    def test_is_in_snapshot(self, default_options: Options) -> None:
        """
        Tests that objects in the snapshot are correctly identified.
        """
        custom_objects = [CustomObject("test1"), CustomObject("test2"), CustomObject("test3")]
        # Double check that weak references can be created
        for obj in custom_objects:
            weakref.ref(obj)
        builtin_objects: list[object] = [[1, 2, 3], {"a": 1}, "string"]
        mixed_objects: list[object] = custom_objects + builtin_objects

        snapshot = MemalotUsageSnapshot(
            object_getter=FixedObjectGetter(mixed_objects),
            filter_condition=None,
        )

        # Check that existing objects are correctly identified as being in the snapshot
        for mixed_obj in mixed_objects:
            assert snapshot.is_in_snapshot(mixed_obj)

        # Check that new objects with the same values are NOT in the snapshot
        # (they are different instances)
        assert not snapshot.is_in_snapshot(CustomObject("test1"))
        assert not snapshot.is_in_snapshot([1, 2, 3])
        assert not snapshot.is_in_snapshot({"a": 1})

        # Check that new objects with different values are NOT in the snapshot
        assert not snapshot.is_in_snapshot(CustomObject("new_object"))
        assert not snapshot.is_in_snapshot([1, 2, 3, 4])
        assert not snapshot.is_in_snapshot({"new": "dict"})

    @pytest.mark.parametrize(
        "objects_in_snapshot,new_objects,expected_diff",
        [
            pytest.param(
                [],
                expected := [CustomObject("new")],
                MemalotObjects(expected),  # type: ignore[name-defined]
                id="Empty snapshot with new object",
            ),
            pytest.param(
                [CustomObject("one")],
                expected := [CustomObject("one")],
                MemalotObjects(expected),  # type: ignore[name-defined]
                id="Existing snapshot with object of same value",
            ),
            pytest.param(
                [CustomObject("old")],
                expected := [CustomObject("new"), CustomObject("new2")],
                MemalotObjects(expected),  # type: ignore[name-defined]
                id="Existing snapshot with multiple new objects",
            ),
            pytest.param(
                [CustomObject("old")],
                [],
                MemalotObjects([]),
                id="Existing snapshot with no new objects",
            ),
            pytest.param(
                [[1, 2]],
                expected_val := [[3, 4], {"c": 3}],
                MemalotObjects(expected_val),  # type: ignore[name-defined]
                id="Builtin objects",
            ),
        ],
    )
    def test_get_diff(
        self,
        objects_in_snapshot: list[object],
        new_objects: list[object],
        expected_diff: MemalotObjects,
        default_options: Options,
    ) -> None:
        """
        Tests the is_new_since_snapshot method with various object combinations.
        """
        snapshot = MemalotUsageSnapshot(
            object_getter=FixedObjectGetter(objects_in_snapshot),
            filter_condition=None,
        )
        all_objects = objects_in_snapshot + new_objects
        diff = MemalotObjects([obj for obj in all_objects if snapshot.is_new_since_snapshot(obj)])

        assert {id(obj) for obj in diff.objects} == {id(obj) for obj in expected_diff.objects}

    def test_is_new_since_snapshot_with_non_weak_ref_objects(
        self, default_options: Options
    ) -> None:
        """
        Tests that objects not supporting weak references are handled correctly in
        is_new_since_snapshot.
        """
        # Create objects that don't support weak references
        non_weak_ref_objects = [
            NonWeakRefObject("test1"),
            NonWeakRefObject("test2"),
            [1, 2, 3],
            {"key": "value"},
            "string_object",
            42,
        ]
        # Double check that weak references cannot be created
        for obj in non_weak_ref_objects:
            with pytest.raises(TypeError):
                weakref.ref(obj)

        snapshot = MemalotUsageSnapshot(
            object_getter=FixedObjectGetter(non_weak_ref_objects),
            filter_condition=None,
        )

        # Test that existing objects are not considered new
        for obj in non_weak_ref_objects:
            assert not snapshot.is_new_since_snapshot(obj)

        # Check that new objects with the same values are considered new
        # We can't test all of them as some are interned (like small integers and
        # strings).
        assert snapshot.is_new_since_snapshot(NonWeakRefObject("test1"))
        assert snapshot.is_new_since_snapshot(NonWeakRefObject("test2"))
        assert snapshot.is_new_since_snapshot([1, 2, 3])
        assert snapshot.is_new_since_snapshot({"key": "value"})

        # Test that new objects with different values are considered new
        new_non_weak_ref_obj = NonWeakRefObject("new_value")
        new_list = [4, 5, 6]
        new_dict = {"new_key": "new_value"}
        new_string = "new_string"
        new_int = 99

        assert snapshot.is_new_since_snapshot(new_non_weak_ref_obj)
        assert snapshot.is_new_since_snapshot(new_list)
        assert snapshot.is_new_since_snapshot(new_dict)
        assert snapshot.is_new_since_snapshot(new_string)
        assert snapshot.is_new_since_snapshot(new_int)

    def test_get_diff_with_non_weak_ref_objects(self, default_options: Options) -> None:
        """
        Tests that is_new_since_snapshot works correctly with objects that don't support
        weak references.
        """
        # Create initial snapshot with non-weak-ref objects
        initial_objects = [
            NonWeakRefObject("original1"),
            NonWeakRefObject("original2"),
            [1, 2],
            {"old": "dict"},
            "old_string_unique_12345",
        ]
        # Double check that weak references cannot be created
        for obj in initial_objects:
            with pytest.raises(TypeError):
                weakref.ref(obj)

        snapshot = MemalotUsageSnapshot(
            object_getter=FixedObjectGetter(initial_objects),
            filter_condition=None,
        )

        # Create new objects, some with the same value but different identities.
        new_objects = [
            NonWeakRefObject("original1"),  # Different object ID; will be in diff
            NonWeakRefObject("new_value"),  # New value; will be in diff
            [1, 2],  # Different object ID; will be in diff
            [3, 4],  # New value; will be in diff
            {"old": "dict"},  # Different object ID; will be in diff
            {"new": "dict"},  # New value; will be in diff
            "new_string_unique_67890",  # New value; will be in diff
        ]

        all_objects = initial_objects + new_objects
        diff = MemalotObjects([obj for obj in all_objects if snapshot.is_new_since_snapshot(obj)])

        assert {id(obj) for obj in diff.objects} == {id(obj) for obj in new_objects}

    def test_weak_ref_object_gced(self, default_options: Options) -> None:
        """
        Tests that if an object supporting weak references is garbage collected,
        it is no longer considered part of the snapshot.
        """
        snapshot, gced_object_id, non_gced_object = _generate_snapshot_with_weak_ref_object(
            default_options=default_options
        )
        gc.collect()
        object_ids = snapshot.active_object_ids
        assert gced_object_id not in object_ids
        assert id(non_gced_object) in object_ids

    def test_non_weak_ref_object_id_reused(self, default_options: Options) -> None:
        """
        Tests that if an object ID is reused for a non-weak-ref object, then the objects are still
        considered different if they have different hashes.
        """
        snapshot, previous_object_id = self._get_snapshot_with_non_weak_ref_object1(
            default_options=default_options
        )
        # Try (multiple times) to create a new object with the same ID as the previous object.
        # We skip the test if it doesn't happen. This isn't ideal but is probably better than not
        # testing this case at all.
        for _ in range(_NUM_SAME_ID_ATTEMPTS):
            new_obj = self._get_non_weak_ref_object2()
            new_obj_id = id(new_obj)
            # Check that the new object has the same ID as the previous object.
            # This behaviour is not guaranteed, as the object ID may not be reused
            # (this is implementation-dependent).
            if new_obj_id == previous_object_id:
                break
        else:
            pytest.skip(
                f"Could not create object with same ID as previous object after "
                f"{_NUM_SAME_ID_ATTEMPTS} attempts - skipping test"
            )
        # Even though the object ID is the same, it is a different object (it has
        # a different hash), so should be considered new.
        # Note: this wouldn't work properly if the object hash was the same, even
        # if the object was new. This is a current limitation of the implementation.
        assert snapshot.is_new_since_snapshot(new_obj)

    def test_excludes_internal_machinery_objects(self, default_options: Options) -> None:
        """
        Tests that objects that are created as part of creating the snapshot
        are excluded from the snapshot.
        """
        original_objects = [
            CustomObject("internal_test1"),  # Weak-ref object
            CustomObject("internal_test2"),  # Weak-ref object
            [1, 2, 3],  # Non-weak-ref object
        ]

        # A mock version of the internal machinery objects
        internal_machinery_objects = [
            CustomObject("machinery1"),  # Weak-ref object
            CustomObject("machinery2"),  # Weak-ref object
            [7, 8, 9],  # Non-weak-ref object
        ]

        get_objects_func = MagicMock(side_effect=[original_objects, internal_machinery_objects])

        snapshot = MemalotUsageSnapshot(
            object_getter=FilteringObjectGetter(
                get_objects_func=get_objects_func,
                options=default_options,
                snapshot_managers=[create_mock(MemalotSnapshotManager)],
            ),
            filter_condition=None,
        )

        # The original objects should not be considered new
        for obj in original_objects:
            assert not snapshot.is_new_since_snapshot(obj)

        # The (mock) internal machinery objects should not be considered new
        for obj in internal_machinery_objects:
            assert not snapshot.is_new_since_snapshot(obj)

        # A new object created after get_objects_func is called is considered new
        new_normal_object = CustomObject("new_normal")
        assert snapshot.is_new_since_snapshot(new_normal_object)

    def test_filter_condition_filters_objects(self, default_options: Options) -> None:
        """
        Tests that the filter_condition parameter properly filters objects during snapshot creation.
        """
        all_objects = [
            CustomObject("obj1"),
            CustomObject("obj2"),
            CustomObject("obj3"),
            CustomObject("obj4"),
        ]

        # Create a filter that only allows objects with "2" or "4" in their value
        def filter_func(obj: object) -> bool:
            if isinstance(obj, CustomObject):
                return "2" in obj.value or "4" in obj.value
            return False

        snapshot = MemalotUsageSnapshot(
            object_getter=FixedObjectGetter(all_objects),
            filter_condition=filter_func,
        )

        # Only obj2 and obj4 should be in the snapshot
        assert snapshot.is_in_snapshot(all_objects[1])  # obj2
        assert snapshot.is_in_snapshot(all_objects[3])  # obj4
        assert not snapshot.is_in_snapshot(all_objects[0])  # obj1
        assert not snapshot.is_in_snapshot(all_objects[2])  # obj3

        # Verify that the snapshot only contains 2 objects
        assert len(snapshot.active_object_ids) == 2

    def _get_non_weak_ref_object1(self) -> NonWeakRefIntObject:
        return NonWeakRefIntObject(1)

    def _get_non_weak_ref_object2(self) -> NonWeakRefIntObject:
        return NonWeakRefIntObject(2)

    def _get_snapshot_with_non_weak_ref_object1(
        self, default_options: Options
    ) -> Tuple[MemalotUsageSnapshot, int]:
        obj = self._get_non_weak_ref_object1()
        snapshot = MemalotUsageSnapshot(
            object_getter=FixedObjectGetter([obj]), filter_condition=None
        )
        return snapshot, id(obj)


class TestMemalotSnapshotManager:
    """
    Tests for the `MemalotSnapshotManager` class.
    """

    def test_generate_new_snapshot(self, default_options: Options) -> None:
        """
        Tests that generate_new_snapshot creates multiple snapshots correctly from a
        new manager instance.
        """
        manager = MemalotSnapshotManager(
            report_id="test-snapshot-123",
        )

        # Initial state - no snapshot
        assert manager.most_recent_snapshot is None
        assert manager.most_recent_snapshot_time is None

        # Create first snapshot
        objects1 = [CustomObject("snap1"), [1, 2], {"key": "value1"}]
        manager.generate_new_snapshot(
            object_getter=FixedObjectGetter(objects1), since_snapshot=None
        )

        # Verify first snapshot contains the expected object IDs
        first_snapshot = manager.most_recent_snapshot
        assert first_snapshot is not None
        assert manager.most_recent_snapshot_time is not None
        first_time = manager.most_recent_snapshot_time
        expected_ids1 = {id(obj) for obj in objects1}
        assert first_snapshot.active_object_ids == expected_ids1

        # Create second snapshot - should replace the first
        objects2 = [CustomObject("snap2"), [3, 4], {"key": "value2"}, "new_string"]
        manager.generate_new_snapshot(
            object_getter=FixedObjectGetter(objects2), since_snapshot=first_snapshot
        )

        # Verify second snapshot contains the expected object IDs and replaced the first
        second_snapshot = manager.most_recent_snapshot
        assert second_snapshot is not None
        assert manager.most_recent_snapshot_time is not None
        assert second_snapshot != first_snapshot
        assert manager.most_recent_snapshot_time >= first_time
        expected_ids2 = {id(obj) for obj in objects2}
        assert second_snapshot.active_object_ids == expected_ids2

        # Create third snapshot to ensure multiple rotations work
        objects3 = [CustomObject("snap3"), NonWeakRefObject("test")]
        manager.generate_new_snapshot(
            object_getter=FixedObjectGetter(objects3), since_snapshot=second_snapshot
        )

        # Verify third snapshot contains the expected object IDs
        third_snapshot = manager.most_recent_snapshot
        assert third_snapshot is not None
        assert manager.most_recent_snapshot_time is not None
        expected_ids3 = {id(obj) for obj in objects3}
        assert third_snapshot.active_object_ids == expected_ids3

    def test_clear_snapshots(self, default_options: Options) -> None:
        """
        Tests that clear_snapshots removes all snapshot data.
        """
        manager = MemalotSnapshotManager(
            report_id="test-clear-123",
        )

        # Create a snapshot first
        objects = [CustomObject("clear_test"), [1, 2, 3]]
        manager.generate_new_snapshot(object_getter=FixedObjectGetter(objects), since_snapshot=None)

        # Verify snapshot exists
        assert manager.most_recent_snapshot is not None
        assert manager.most_recent_snapshot_time is not None

        # Clear snapshots
        manager.clear_snapshots()

        # Verify all snapshot data is cleared
        assert manager.most_recent_snapshot is None
        assert manager.most_recent_snapshot_time is None

    def test_rotate_memory_usage(self, default_options: Options) -> None:
        """
        Tests that rotate_memory_usage tracks memory usage across multiple calls from a new
        manager instance.
        """
        manager = MemalotSnapshotManager(
            report_id="test-memory-123",
        )

        # Initial state - no memory usage tracked
        assert manager.most_recent_reported_usage is None

        # First rotation - should return None for old usage
        old_usage1, new_usage1 = manager.rotate_memory_usage(iteration=MemalotCount(1))

        assert old_usage1 is None
        assert new_usage1 is not None
        assert new_usage1.iteration_number == 1
        assert manager.most_recent_reported_usage == new_usage1

        # Second rotation - should return previous usage as old
        old_usage2, new_usage2 = manager.rotate_memory_usage(iteration=MemalotCount(2))

        assert old_usage2 == new_usage1
        assert new_usage2 is not None
        assert new_usage2.iteration_number == 2
        assert manager.most_recent_reported_usage == new_usage2

        # Third rotation - ensure multiple rotations work
        old_usage3, new_usage3 = manager.rotate_memory_usage(iteration=MemalotCount(3))

        assert old_usage3 == new_usage2
        assert new_usage3 is not None
        assert new_usage3.iteration_number == 3
        assert manager.most_recent_reported_usage == new_usage3

    def test_report_id_property(self, default_options: Options) -> None:
        """
        Tests that the report_id property returns the correct report ID.
        """
        report_id = "test-property-id-456"
        manager = MemalotSnapshotManager(
            report_id=report_id,
        )

        assert manager.report_id == report_id

    def test_snapshot_created_with_correct_parameters(self, mocker: MockerFixture) -> None:
        """
        Tests that MemalotUsageSnapshot is created with filter_condition=None when
        since_snapshot=None.
        """
        mock_snapshot_init = mocker.patch(
            "memalot.snapshots.MemalotUsageSnapshot.__init__", return_value=None
        )
        mock_get_objects_func = MagicMock()
        manager = MemalotSnapshotManager(
            report_id="report_id",
        )
        manager.generate_new_snapshot(object_getter=mock_get_objects_func, since_snapshot=None)
        mock_snapshot_init.assert_called_once_with(
            object_getter=mock_get_objects_func,
            filter_condition=None,
        )

    def test_snapshot_created_with_filter_condition_when_new_objects_only(
        self, mocker: MockerFixture, default_options: Options
    ) -> None:
        """
        Tests that MemalotUsageSnapshot is created with a filter_condition when since_snapshot
        is provided. The filter_condition should be the is_new_since_snapshot method of the
        since_snapshot.
        """
        mock_snapshot_init = mocker.patch(
            "memalot.snapshots.MemalotUsageSnapshot.__init__", return_value=None
        )
        mock_get_objects_func = MagicMock()
        manager = MemalotSnapshotManager(
            report_id="report_id",
        )
        manager.generate_new_snapshot(object_getter=mock_get_objects_func, since_snapshot=None)

        first_snapshot = manager.most_recent_snapshot

        manager.generate_new_snapshot(
            object_getter=mock_get_objects_func, since_snapshot=first_snapshot
        )

        # The second call should have a filter_condition that is the is_new_since_snapshot
        # method of the first snapshot
        assert mock_snapshot_init.call_count == 2
        second_call = mock_snapshot_init.call_args_list[1]
        assert second_call.kwargs["object_getter"] is mock_get_objects_func
        assert first_snapshot is not None  # Keep Mypy happy
        assert second_call.kwargs["filter_condition"] == first_snapshot.is_new_since_snapshot

    def test_new_objects_only_requires_existing_snapshot(self, default_options: Options) -> None:
        """
        Tests that generate_new_snapshot with since_snapshot parameter is correctly applied.
        """
        manager = MemalotSnapshotManager(
            report_id="report_id",
        )

        # This should work fine - no error expected when since_snapshot is None
        manager.generate_new_snapshot(
            object_getter=FixedObjectGetter([]),
            since_snapshot=None,
        )


def _generate_snapshot_with_weak_ref_object(
    default_options: Options,
) -> Tuple[MemalotUsageSnapshot, int, CustomObject]:
    """
    Helper to generate two weak-referencable objects and return a snapshot containing them.

    When this function returns, the first object will be eligible for garbage collection, but
    the second will not (since it's returned).
    """
    gced_object = CustomObject("gced_object")
    non_gced_object = CustomObject("non_gced_object")
    # Double check that weak references can be created
    weakref.ref(gced_object)
    weakref.ref(non_gced_object)
    snapshot = MemalotUsageSnapshot(
        object_getter=FixedObjectGetter([gced_object, non_gced_object]),
        filter_condition=None,
    )
    return snapshot, id(gced_object), non_gced_object
