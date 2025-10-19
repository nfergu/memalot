from typing import Any, Callable, Type

import pytest

from memalot.base import MemalotObjectIds
from memalot.objects import filter_objects


class _CustomA:
    pass


class _CustomB:
    pass


customa1 = _CustomA()
customa2 = _CustomA()
customb1 = _CustomB()
string1 = "string"
int1 = 123
the_list: list[Any] = [1, 2, 3]
the_dict: dict[str, Any] = {"k": "v"}

sample_objects = [
    customa1,
    customa2,
    customb1,
    string1,
    int1,
    the_list,
    the_dict,
]


class TestFilterObjects:
    """
    Tests for the `filter_objects` function.
    """

    @pytest.mark.parametrize(
        "included_type_names,excluded_type_names,include_ids,exclude_ids,expected",
        [
            pytest.param(
                set(),
                set(),
                set(),
                set(),
                [customa1, customa2, customb1, string1, the_list, the_dict],
                id="none",
            ),
            pytest.param(
                {"Custom"},
                set(),
                set(),
                set(),
                [customa1, customa2, customb1],
                id="only_included_type_names",
            ),
            pytest.param(
                set(),
                {"Custom"},
                set(),
                set(),
                [string1, the_list, the_dict],
                id="only_excluded_type_names",
            ),
            pytest.param(
                {"Custom"},
                {"CustomB"},
                set(),
                set(),
                [customa1, customa2],
                id="include_and_exclude_names",
            ),
            pytest.param(
                set(),
                set(),
                {id(customa1), id(the_list)},
                set(),
                [customa1, the_list],
                id="include_object_ids",
            ),
            pytest.param(
                set(),
                set(),
                set(),
                {id(customa2), id(the_dict)},
                [customa1, customb1, string1, the_list],
                id="exclude_object_ids",
            ),
            pytest.param(
                {"Custom"},
                set(),
                set(),
                {id(customa2)},
                [customa1, customb1],
                id="names_and_exclude_ids",
            ),
            pytest.param(
                {"Custom"},
                set(),
                {id(customb1)},
                set(),
                [customb1],
                id="names_and_include_ids_subselection",
            ),
            pytest.param(
                {"Custom"},
                set(),
                {id(the_dict)},
                set(),
                [],
                id="include_ids_conflict_with_names",
            ),
            pytest.param(
                {"DoesNotExist"},
                set(),
                set(),
                set(),
                [],
                id="included_names_no_results",
            ),
            pytest.param(
                set(),
                {"NoSuch"},
                set(),
                set(),
                [customa1, customa2, customb1, string1, the_list, the_dict],
                id="excluded_names_no_effect",
            ),
            pytest.param(
                {"Custom"},
                {"CustomB"},
                {id(customa1), id(the_list)},
                {id(customa2), id(the_dict)},
                [customa1],
                id="combined",
            ),
        ],
    )
    def test_filter_objects_parametrized(
        self,
        included_type_names: set[str],
        excluded_type_names: set[str],
        include_ids: set[int],
        exclude_ids: set[int],
        expected: list[Any],
    ) -> None:
        """
        Tests the filter_objects function with various inclusions and exclusions.
        """
        excluded_types: set[Type[Any]] = {int}
        result = filter_objects(
            objects=sample_objects,
            excluded_types=excluded_types,
            included_type_names=included_type_names,
            excluded_type_names=excluded_type_names,
            include_object_ids=MemalotObjectIds(include_ids),
            exclude_object_ids=MemalotObjectIds(exclude_ids),
        )

        assert result == expected

    def test_closure_filtering_with_excluded_type(self) -> None:
        """
        Tests that closure cells and their contents are properly filtered when the
        type is excluded.
        """
        captured_object = _CustomA()

        # Create a closure that captures the _CustomA object
        def create_closure() -> Callable[[], _CustomA]:
            def inner_function() -> _CustomA:
                return captured_object

            return inner_function

        closure = create_closure()

        # Get the closure cell directly from the closure
        assert closure.__closure__ is not None
        closure_cell = closure.__closure__[0]

        test_objects = [captured_object, closure_cell]

        # When _CustomA is not excluded, both cell and object should be present
        result_not_excluded = filter_objects(
            objects=test_objects,
            excluded_types=set(),  # Don't exclude _CustomA
            included_type_names=set(),
            excluded_type_names=set(),
            include_object_ids=MemalotObjectIds(),
            exclude_object_ids=MemalotObjectIds(),
        )

        # Both the closure cell and the captured object should be present
        assert captured_object in result_not_excluded
        assert closure_cell in result_not_excluded

        # When _CustomA is excluded, both cell and object should be absent
        result_excluded = filter_objects(
            objects=test_objects,
            excluded_types={_CustomA},  # Exclude _CustomA
            included_type_names=set(),
            excluded_type_names=set(),
            include_object_ids=MemalotObjectIds(),
            exclude_object_ids=MemalotObjectIds(),
        )

        # Neither the closure cell nor the captured object should be present
        assert captured_object not in result_excluded
        assert closure_cell not in result_excluded


def test_gc_and_get_objects() -> None:
    """
    Test that gc_and_get_objects returns a list of objects.

    This is just a smoke test. Most testing of the underlying functionality is done in
    the tests for `get_objects`.
    """
    from memalot.objects import gc_and_get_objects

    result = gc_and_get_objects(max_untracked_search_depth=1)

    assert isinstance(result, list)
    assert len(result) > 0  # Should have some objects
    # Check that we get various types of objects
    types_found = {type(obj) for obj in result}
    assert len(types_found) > 1  # Should find multiple types
