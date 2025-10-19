from typing import Callable, Generator, Tuple

import pytest

from memalot.base import ApproximateSize, CachingIterable, ObjectSignature

_NUM_SAME_ID_ATTEMPTS = 100


class TestApproximateSize:
    """
    Tests for the ApproximateSize class.
    """

    def test_default_initialization(self) -> None:
        """
        Test that ApproximateSize initializes with default values.
        """
        size = ApproximateSize()
        assert size.approx_size == 0
        assert size.upper_bound_known is True

    @pytest.mark.parametrize(
        "approx_size,upper_bound_known,expected_prefix",
        [
            (100, True, "~"),
            (500, False, ">="),
            (0, True, "~"),
        ],
    )
    def test_initialization_with_values(
        self, approx_size: int, upper_bound_known: bool, expected_prefix: str
    ) -> None:
        """
        Test ApproximateSize initialization with various values.
        """
        size = ApproximateSize(approx_size=approx_size, upper_bound_known=upper_bound_known)
        assert size.approx_size == approx_size
        assert size.upper_bound_known == upper_bound_known
        assert size.prefix == expected_prefix

    @pytest.mark.parametrize(
        "size1_approx,size1_known,size2_approx,size2_known,"
        "expected_approx,expected_known,expected_prefix",
        [
            (100, True, 200, True, 300, True, "~"),
            (100, True, 200, False, 300, False, ">="),
            (100, False, 200, True, 300, False, ">="),
            (100, False, 200, False, 300, False, ">="),
        ],
    )
    def test_addition(
        self,
        size1_approx: int,
        size1_known: bool,
        size2_approx: int,
        size2_known: bool,
        expected_approx: int,
        expected_known: bool,
        expected_prefix: str,
    ) -> None:
        """
        Test ApproximateSize addition operation.
        """
        size1 = ApproximateSize(approx_size=size1_approx, upper_bound_known=size1_known)
        size2 = ApproximateSize(approx_size=size2_approx, upper_bound_known=size2_known)

        result = size1 + size2

        assert result.approx_size == expected_approx
        assert result.upper_bound_known == expected_known
        assert result.prefix == expected_prefix

    def test_addition_creates_new_instance(self) -> None:
        """
        Test that addition creates a new ApproximateSize instance.
        """
        size1 = ApproximateSize(approx_size=100, upper_bound_known=True)
        size2 = ApproximateSize(approx_size=200, upper_bound_known=False)

        result = size1 + size2

        assert result is not size1
        assert result is not size2
        assert size1.approx_size == 100  # Original unchanged
        assert size2.approx_size == 200  # Original unchanged

    def test_equality_with_same_values(self) -> None:
        """
        Test that ApproximateSize instances with same values are equal.
        """
        size1 = ApproximateSize(approx_size=100, upper_bound_known=True)
        size2 = ApproximateSize(approx_size=100, upper_bound_known=True)

        assert size1 == size2

    def test_equality_with_different_values(self) -> None:
        """
        Test that ApproximateSize instances with different values are not equal.
        """
        size1 = ApproximateSize(approx_size=100, upper_bound_known=True)
        size2 = ApproximateSize(approx_size=200, upper_bound_known=True)
        size3 = ApproximateSize(approx_size=100, upper_bound_known=False)

        assert size1 != size2
        assert size1 != size3

    def test_equality_with_non_approximate_size(self) -> None:
        """
        Test that ApproximateSize is not equal to non-ApproximateSize objects.
        """
        size = ApproximateSize(approx_size=100, upper_bound_known=True)

        assert size != 100
        assert size != "100"
        assert size is not None

    def test_hashing(self) -> None:
        """
        Test that ApproximateSize instances with same values have the same hash.
        """
        size1 = ApproximateSize(approx_size=100, upper_bound_known=True)
        size2 = ApproximateSize(approx_size=100, upper_bound_known=True)
        size3 = ApproximateSize(approx_size=200, upper_bound_known=True)
        size4 = ApproximateSize(approx_size=100, upper_bound_known=False)

        assert hash(size1) == hash(size2)
        assert hash(size1) != hash(size3)
        assert hash(size1) != hash(size4)


class TestCachingIterable:
    """
    Tests for the CachingIterable class.
    """

    @pytest.fixture(name="create_sample_iterable")
    def _create_sample_iterable(self) -> Callable[[], Generator[int, None, None]]:
        """
        Provide a generator function for testing.
        """

        def create_generator() -> Generator[int, None, None]:
            for item in range(1, 6):
                yield item

        return create_generator

    def test_caching_with_generator(
        self, create_sample_iterable: Callable[[], Generator[int, None, None]]
    ) -> None:
        """
        Test that generator items are cached properly.
        """
        caching_iterable = CachingIterable(create_sample_iterable())
        first_result = list(caching_iterable)
        assert first_result == [1, 2, 3, 4, 5]
        # Since the iterable is a generator, it should be exhausted after the first iteration,
        # so the only way we'll get the same result is if the cache is used.
        second_result = list(caching_iterable)
        assert second_result == [1, 2, 3, 4, 5]

    def test_partial_iteration_then_full(
        self, create_sample_iterable: Callable[[], Generator[int, None, None]]
    ) -> None:
        """
        Test partial iteration followed by full iteration.
        """
        caching_iterable = CachingIterable(create_sample_iterable())

        # Partially iterate through the iterable
        iterator = iter(caching_iterable)
        partial_result = [next(iterator), next(iterator)]
        assert partial_result == [1, 2]
        assert caching_iterable._cache == [1, 2]

        # Full iteration should include cached and remaining items
        full_result = list(caching_iterable)
        assert full_result == [1, 2, 3, 4, 5]
        assert caching_iterable._cache == [1, 2, 3, 4, 5]

    def test_empty_iterable(self) -> None:
        """
        Test CachingIterable with empty input.
        """
        caching_iterable: CachingIterable[int] = CachingIterable([])
        assert list(caching_iterable) == []

    def test_single_item_iterable(self) -> None:
        """
        Test CachingIterable with single item.
        """
        caching_iterable = CachingIterable([42])
        assert list(caching_iterable) == [42]

    def test_iterator_protocol(
        self, create_sample_iterable: Callable[[], Generator[int, None, None]]
    ) -> None:
        """
        Test that CachingIterable properly implements the iterator protocol.
        """
        caching_iterable = CachingIterable(create_sample_iterable())

        # Test manual iteration
        iterator = iter(caching_iterable)
        results = []
        try:
            while True:
                results.append(next(iterator))
        except StopIteration:
            pass

        assert results == [1, 2, 3, 4, 5]
        assert list(caching_iterable) == [1, 2, 3, 4, 5]


class HashableObject:
    def __init__(self, value: int) -> None:
        self._value = value

    def __hash__(self) -> int:
        return hash(self._value)


class OtherHashableObject:
    def __init__(self, value: int) -> None:
        self._value = value

    def __hash__(self) -> int:
        return hash(self._value)


@pytest.fixture(name="list_pair")
def _create_list_pair() -> Tuple[list[int], list[int]]:
    """
    Provide two separate list instances with the same contents.
    """
    return [1, 2, 3], [1, 2, 3]


class TestObjectSignature:
    """
    Tests for the `ObjectSignature` class.
    """

    def test_same_object_unhashable_returns_true(
        self, list_pair: Tuple[list[int], list[int]]
    ) -> None:
        """
        Test that ObjectSignature identifies the same unhashable object instance as the same object.
        """
        a, _ = list_pair
        sig = ObjectSignature(a)
        assert sig.is_probably_same_object(a) is True

    def test_different_object_unhashable_returns_false(
        self, list_pair: Tuple[list[int], list[int]]
    ) -> None:
        """
        Test that ObjectSignature identifies a different unhashable object instance as
        a different object.
        """
        a, b = list_pair
        sig = ObjectSignature(a)
        assert sig.is_probably_same_object(b) is False

    def test_same_object_hashable_returns_true(self) -> None:
        """
        Test that ObjectSignature identifies the same hashable object instance as the same object.
        """
        obj = HashableObject(6282762661928727)
        sig = ObjectSignature(obj)
        assert sig.is_probably_same_object(obj) is True

    def test_different_object_same_hash(self) -> None:
        """
        Test that ObjectSignature identifies a different hashable object instance,
        even if it has the same hash, as different.
        """
        obj1 = HashableObject(6282762661928727)
        obj2 = HashableObject(6282762661928727)
        sig = ObjectSignature(obj1)
        assert sig.is_probably_same_object(obj2) is False

    def test_same_object_id_different_hash(self) -> None:
        """
        Tests that if an object ID is reused for a different object with the same type but a
        different hash, then ObjectSignature identifies it as a different object.
        """
        object_signature, previous_object_id = self._get_hashable_object1_signature()
        # Try (multiple times) to create a new object with the same ID as the previous object.
        # We skip the test if it doesn't happen. This isn't ideal but is probably better than not
        # testing this case at all.
        for _ in range(_NUM_SAME_ID_ATTEMPTS):
            new_obj = self._get_hashable_object2()
            new_obj_id = id(new_obj)
            if new_obj_id == previous_object_id:
                break
        else:
            pytest.skip(
                f"Failed to create object with reused ID after {_NUM_SAME_ID_ATTEMPTS} attempts"
            )
        # Objects have the same ID but different hashes, so should be identified as different.
        assert not object_signature.is_probably_same_object(new_obj)

    def test_same_object_id_same_hash(self) -> None:
        """
        Tests that if an object ID is reused for a different object with the same type and hash,
        then ObjectSignature identifies it as the same object.

        This behavior is not ideal but is a limitation of the current implementation.
        """
        object_signature, previous_object_id = self._get_hashable_object1_signature()
        # Try (multiple times) to create a new object with the same ID as the previous object.
        # We skip the test if it doesn't happen. This isn't ideal but is probably better than not
        # testing this case at all.
        for _ in range(_NUM_SAME_ID_ATTEMPTS):
            new_obj = self._get_hashable_object1()
            new_obj_id = id(new_obj)
            if new_obj_id == previous_object_id:
                break
        else:
            pytest.skip(
                f"Failed to create object with reused ID after {_NUM_SAME_ID_ATTEMPTS} attempts"
            )
        # Objects have the same ID and same hashes, so should be identified as the same.
        assert object_signature.is_probably_same_object(new_obj)

    def test_same_object_id_different_type(self) -> None:
        """
        Tests that if an object ID is reused for a different object with a different type,
        then ObjectSignature identifies it as a different object.
        """
        object_signature, previous_object_id = self._get_hashable_object1_signature()
        # Try (multiple times) to create a new object with the same ID as the previous object.
        # We skip the test if it doesn't happen. This isn't ideal but is probably better than not
        # testing this case at all.
        for _ in range(_NUM_SAME_ID_ATTEMPTS):
            new_obj = self._get_other_hashable_object2()
            new_obj_id = id(new_obj)
            if new_obj_id == previous_object_id:
                break
        else:
            pytest.skip(
                f"Failed to create object with reused ID after {_NUM_SAME_ID_ATTEMPTS} attempts"
            )
        # Objects have the same ID but different types, so should be identified as different.
        assert not object_signature.is_probably_same_object(new_obj)

    def _get_hashable_object1(self) -> HashableObject:
        return HashableObject(1)

    def _get_hashable_object2(self) -> HashableObject:
        return HashableObject(2)

    def _get_hashable_object1_signature(self) -> Tuple[ObjectSignature, int]:
        obj = self._get_hashable_object1()
        return ObjectSignature(obj), id(obj)

    def _get_other_hashable_object2(self) -> OtherHashableObject:
        return OtherHashableObject(2)
