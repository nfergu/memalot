import gc
import inspect
from typing import Any, List, Set, Tuple

import networkx as nx
import numpy as np
import pytest
from referrers import ReferrerGraphNode

from memalot import utils
from memalot.base import ReferrerGraph, ReferrerNode
from memalot.utils import PrintableReferrerNode
from tests.utils_for_testing import create_mock, one


@pytest.fixture(name="custom_tag")
def _custom_tag_fixture() -> str:
    """
    Custom tag fixture for testing.
    """
    return "custom_tag"


@pytest.fixture(name="numpy_array_holder")
def _numpy_array_holder_fixture() -> "NumpyArrayHolder":
    """
    Fixture providing a NumpyArrayHolder instance.
    """
    return NumpyArrayHolder(128)


@pytest.fixture(name="tuple_holder")
def _tuple_holder_fixture() -> "TupleHolder":
    """
    Fixture providing a TupleHolder instance.
    """
    return TupleHolder(("string in tuple",))


class NumpyArrayHolder:
    def __init__(self, size: int) -> None:
        self.payload = np.ones(size)


class TupleHolder:
    def __init__(self, the_tuple: Tuple[Any, ...]) -> None:
        self.the_tuple = the_tuple


class TestAsMib:
    """
    Tests for the `as_mib` function.
    """

    @pytest.mark.parametrize(
        "num_bytes,expected",
        [
            (0, "[memory_absolute]0.0[/memory_absolute] MiB"),
            (1024, "[memory_absolute]0.0[/memory_absolute] MiB"),
            (1048576, "[memory_absolute]1.0[/memory_absolute] MiB"),  # 1 MiB
            (2097152, "[memory_absolute]2.0[/memory_absolute] MiB"),  # 2 MiB
            (1572864, "[memory_absolute]1.5[/memory_absolute] MiB"),  # 1.5 MiB
            (1073741824, "[memory_absolute]1024.0[/memory_absolute] MiB"),  # 1 GiB
        ],
    )
    def test_as_mib_default_tag(self, num_bytes: int, expected: str) -> None:
        """
        Test as_mib with default tag and various byte values.
        """
        result = utils.as_mib(num_bytes)
        assert result == expected

    def test_as_mib_custom_tag(self, custom_tag: str) -> None:
        """
        Test as_mib with custom tag.
        """
        result = utils.as_mib(1048576, custom_tag)
        expected = f"[{custom_tag}]1.0[/{custom_tag}] MiB"
        assert result == expected


class TestAsMibSf:
    """
    Tests for the `as_mib_sf` function.
    """

    @pytest.mark.parametrize(
        "num_bytes,expected",
        [
            (0, "[memory_absolute]0[/memory_absolute] MiB"),
            (1024, "[memory_absolute]0.000977[/memory_absolute] MiB"),
            (1048576, "[memory_absolute]1[/memory_absolute] MiB"),  # 1 MiB
            (2097152, "[memory_absolute]2[/memory_absolute] MiB"),  # 2 MiB
            (1572864, "[memory_absolute]1.5[/memory_absolute] MiB"),  # 1.5 MiB
            (1073741824, "[memory_absolute]1.02e+03[/memory_absolute] MiB"),  # 1 GiB
        ],
    )
    def test_as_mib_sf_default_tag(self, num_bytes: int, expected: str) -> None:
        """
        Test as_mib_sf with default tag and various byte values.
        """
        result = utils.as_mib_sf(num_bytes)
        assert result == expected

    def test_as_mib_sf_custom_tag(self, custom_tag: str) -> None:
        """
        Test as_mib_sf with custom tag.
        """
        result = utils.as_mib_sf(1048576, custom_tag)
        expected = f"[{custom_tag}]1[/{custom_tag}] MiB"
        assert result == expected


class TestFormatBytes:
    """
    Tests for the `format_bytes` function.
    """

    @pytest.mark.parametrize(
        "num_bytes,expected",
        [
            (0, "0 B"),
            (512, "[memory_absolute]512[/memory_absolute] B"),
            (1023, "[memory_absolute]1023[/memory_absolute] B"),
            (1024, "[memory_absolute]1.0[/memory_absolute] KiB"),
            (1536, "[memory_absolute]1.5[/memory_absolute] KiB"),
            (1048576, "[memory_absolute]1.00[/memory_absolute] MiB"),
            (1572864, "[memory_absolute]1.50[/memory_absolute] MiB"),
            (1073741824, "[memory_absolute]1.00[/memory_absolute] GiB"),
            (1610612736, "[memory_absolute]1.50[/memory_absolute] GiB"),
        ],
    )
    def test_format_bytes_default_tag(self, num_bytes: int, expected: str) -> None:
        """
        Test format_bytes with default tag and various byte values.
        """
        result = utils.format_bytes(num_bytes)
        assert result == expected

    def test_format_bytes_custom_tag(self, custom_tag: str) -> None:
        """
        Test format_bytes with custom tag.
        """
        result = utils.format_bytes(1024, custom_tag)
        expected = f"[{custom_tag}]1.0[/{custom_tag}] KiB"
        assert result == expected

    @pytest.mark.parametrize(
        "invalid_input",
        [
            -1,
            -100,
            "1024",
            1024.5,
            None,
        ],
    )
    def test_format_bytes_invalid_input(self, invalid_input: Any) -> None:
        """
        Test format_bytes raises ValueError for invalid inputs.
        """
        with pytest.raises(ValueError, match="Input must be a non-negative integer"):
            utils.format_bytes(invalid_input)


class TestGetFullTypeName:
    """
    Tests for the `get_full_type_name` function.
    """

    def test_get_full_type_name_builtin_types(self) -> None:
        """
        Test get_full_type_name with built-in types.
        """
        assert utils.get_full_type_name(str) == "builtins.str"
        assert utils.get_full_type_name(int) == "builtins.int"
        assert utils.get_full_type_name(list) == "builtins.list"
        assert utils.get_full_type_name(dict) == "builtins.dict"

    def test_get_full_type_name_custom_classes(self) -> None:
        """
        Test get_full_type_name with custom classes.
        """
        assert utils.get_full_type_name(NumpyArrayHolder) == "tests.test_utils.NumpyArrayHolder"
        assert utils.get_full_type_name(TupleHolder) == "tests.test_utils.TupleHolder"

    def test_get_full_type_name_imported_types(self) -> None:
        """
        Test get_full_type_name with imported types.
        """
        assert utils.get_full_type_name(np.ndarray) == "numpy.ndarray"
        assert utils.get_full_type_name(nx.DiGraph) == "networkx.classes.digraph.DiGraph"


class TestGetModulePrefix:
    """
    Tests for the `get_module_prefix` function.
    """

    def test_get_module_prefix_found(self) -> None:
        """
        Test get_module_prefix returns the correct module prefix when called from a module
        outside the memalot package.
        """
        # When this test runs, the calling module is tests.test_utils, so we expect "tests."
        result = utils.get_module_prefix()
        assert result == "tests."


class _ObjectThatOnlyHasOneInstance:
    pass


class TestGetObjects:
    """
    Tests for the `get_objects` function.
    """

    def test_get_objects_no_mocking(self) -> None:
        """
        Test get_objects works without mocking get_objects_func. We don't know what the result
        will be in this case.
        """
        _ = _ObjectThatOnlyHasOneInstance()
        result = utils.get_objects()
        instances = [obj for obj in result if isinstance(obj, _ObjectThatOnlyHasOneInstance)]
        assert len(instances) == 1

    def test_get_objects_mocked_empty_list(self) -> None:
        """
        Test get_objects with mocked get_objects_func returning empty list.
        """
        mock_get_objects = create_mock(spec=lambda: [])
        mock_get_objects.return_value = []

        result = utils.get_objects(get_objects_func=mock_get_objects)

        assert result == []
        mock_get_objects.assert_called_once()

    def test_get_objects_mocked_with_objects(self) -> None:
        """
        Test get_objects with mocked get_objects_func returning known objects.
        """
        test_string = "test_string"
        test_list = [1, 2, 3]
        test_dict = {"key": "value"}

        mock_get_objects = create_mock(spec=lambda: [])
        mock_get_objects.return_value = [test_string, test_list, test_dict, 1, 2, 3, "key", "value"]

        result = utils.get_objects(get_objects_func=mock_get_objects)

        assert len(result) == 8
        assert test_string in result
        assert test_list in result
        assert test_dict in result
        assert "key" in result
        assert "value" in result
        assert 1 in result
        assert 2 in result
        assert 3 in result
        mock_get_objects.assert_called_once()

    def test_get_objects_mocked_with_frame_object(self) -> None:
        """
        Test get_objects filters out frame objects when using mocked get_objects_func.
        """
        test_string = "test_string"
        frame = inspect.currentframe()

        mock_get_objects = create_mock(spec=lambda: [])
        mock_get_objects.return_value = [test_string, frame]

        result = utils.get_objects(get_objects_func=mock_get_objects)

        assert len(result) == 1
        assert test_string in result
        assert frame not in result
        mock_get_objects.assert_called_once()

    def test_get_objects_mocked_with_untracked_objects(self) -> None:
        """
        Test get_objects finds untracked objects through referents when using mocked
        get_objects_func.
        """
        # Create a tracked object (list) that contains untracked objects (tuple)
        untracked_tuple = ("untracked", "data")
        tracked_list = [untracked_tuple]

        mock_get_objects = create_mock(spec=lambda: [])
        mock_get_objects.return_value = [tracked_list]

        result = utils.get_objects(max_untracked_search_depth=2, get_objects_func=mock_get_objects)

        result_ids = {id(obj) for obj in result}
        assert id(tracked_list) in result_ids
        assert id(untracked_tuple) in result_ids
        mock_get_objects.assert_called_once()

    def test_get_objects_removes_duplicates(self) -> None:
        """
        Test get_objects removes duplicate objects when using mocked get_objects_func.
        """
        test_string = "test_string"

        mock_get_objects = create_mock(spec=lambda: [])
        mock_get_objects.return_value = [test_string, test_string, test_string]

        result = utils.get_objects(get_objects_func=mock_get_objects)

        # Should only have one instance of the string
        string_count = sum(1 for obj in result if obj is test_string)
        assert string_count == 1
        mock_get_objects.assert_called_once()

    def test_get_objects_with_np_array_holder(self, numpy_array_holder: NumpyArrayHolder) -> None:
        """
        Tests that NumPy arrays are returned when they are instance attributes of a class.

        In Python 3.10, for example, instance attributes are held in a dict, and since CPython
        doesn't track collections of immutable objects, we need to search the referents for
        at least two levels to find the NumPy array in this case.
        """
        objects = utils.get_objects()
        object_ids: Set[int] = {id(obj) for obj in objects}
        assert id(numpy_array_holder.payload) in object_ids

    def test_get_objects_with_tuple_holder(self, tuple_holder: TupleHolder) -> None:
        """
        Tests that tuples are returned when they are instance attributes of a class.

        In Python 3.10, for example, instance attributes are held in a dict, and since CPython
        doesn't track collections of immutable objects, we need to search the referents for
        at least two levels to find the tuple in this case.
        """
        objects = utils.get_objects()
        object_ids: Set[int] = {id(obj) for obj in objects}
        assert id(tuple_holder.the_tuple) in object_ids
        assert id(tuple_holder.the_tuple[0]) in object_ids

    def test_with_nested_tuples(self) -> None:
        """
        Tests the `get_objects` function with nested tuples. Nested tuples are interesting
        because they are both immutable and collections. Since CPython doesn't track
        collections of immutable objects, it's possible for nested tuples to "hide" objects
        from `get_objects`.

        Note: we need to increase `max_untracked_search_depth` to 5 to find the innermost
        tuple. This is because (in Python 3.10) we have the following reference chain:

        TupleHolder -> __dict__ -> Tuple c -> Tuple b -> Tuple a -> string
        """
        my_object = TupleHolder(self._get_nested_tuples())
        objects = utils.get_objects(max_untracked_search_depth=5)
        object_ids: Set[int] = {id(obj) for obj in objects}
        assert id(my_object.the_tuple) in object_ids
        assert id(my_object.the_tuple[0]) in object_ids
        assert id(my_object.the_tuple[0][0]) in object_ids
        assert id(my_object.the_tuple[0][0][0]) in object_ids

    def _get_nested_tuples(self) -> Tuple[Tuple[Tuple[str]]]:
        a = ("tuples all the way down",)
        b = (a,)
        c = (b,)
        # CPython stops tracking tuples if they contain only immutable objects, but
        # only when they are first seen by the garbage collector, so we need to collect
        # here to trigger this.
        gc.collect()
        return c


class TestConvertGraphNodes:
    """
    Tests for the `convert_graph_nodes` function.
    """

    def test_convert_graph_nodes_empty_graph(self) -> None:
        """
        Test convert_graph_nodes with empty graph.
        """
        empty_graph = nx.DiGraph()
        result = utils.convert_graph_nodes(empty_graph)

        assert isinstance(result, ReferrerGraph)
        assert len(result.graph_nodes) == 0
        assert result.target_ids == set()
        assert result.root_ids == set()

    @pytest.mark.parametrize(
        "node,expected",
        [
            (
                ReferrerGraphNode(name="test_node", id=123, type="str"),
                ReferrerNode(
                    id=0,
                    name="test_node",
                    object_id=123,
                    referent_ids=[],
                ),
            ),
        ],
    )
    def test_convert_graph_nodes_single_node(
        self, node: ReferrerGraphNode, expected: ReferrerNode
    ) -> None:
        """
        Test convert_graph_nodes with single node.
        """
        graph = nx.DiGraph()
        graph.add_node(node)

        result = utils.convert_graph_nodes(graph)

        assert len(result.graph_nodes) == 1
        assert result.graph_nodes[0] == expected
        # Single node with no edges should be a root but not a target
        assert result.root_ids == {0}
        assert result.target_ids == set()

    def test_convert_graph_nodes_with_edges(self) -> None:
        """
        Test convert_graph_nodes with nodes and edges.
        """
        graph = nx.DiGraph()
        node1 = ReferrerGraphNode(name="test_node1", id=123, type="str")
        node2 = ReferrerGraphNode(name="test_node2", id=456, type="str")
        graph.add_node(node1)
        graph.add_node(node2)
        graph.add_edge(node1, node2)

        result = utils.convert_graph_nodes(graph)

        assert len(result.graph_nodes) == 2

        # Check that the first node has the second node as a referent
        assert result.graph_nodes[0].referent_ids == [1]
        assert result.graph_nodes[1].referent_ids == []

        # Verify node details
        assert result.graph_nodes[0].name == "test_node1"
        assert result.graph_nodes[0].object_id == 123
        assert result.graph_nodes[1].name == "test_node2"
        assert result.graph_nodes[1].object_id == 456

        # Node1 should be root (no incoming edges), node2 should not be root
        assert result.root_ids == {0}
        assert result.target_ids == set()

    def test_convert_graph_nodes_with_target_nodes(self) -> None:
        """
        Test convert_graph_nodes correctly identifies target nodes.
        """
        graph = nx.DiGraph()
        node1 = ReferrerGraphNode(name="root_node", id=123, type="str")
        node2 = ReferrerGraphNode(name="target_node", id=456, type="str")
        # Manually set is_target attribute for testing
        object.__setattr__(node2, "is_target", True)
        graph.add_node(node1)
        graph.add_node(node2)
        graph.add_edge(node1, node2)

        result = utils.convert_graph_nodes(graph)

        assert len(result.graph_nodes) == 2

        # Verify target and root identification
        assert result.root_ids == {0}  # node1 is root (no incoming edges)
        assert result.target_ids == {1}  # node2 is target (is_target=True)

        # Verify node details
        assert result.graph_nodes[0].name == "root_node"
        assert result.graph_nodes[1].name == "target_node"

    def test_convert_graph_nodes_with_multiple_targets_and_roots(self) -> None:
        """
        Test convert_graph_nodes with multiple target and root nodes.
        """
        graph = nx.DiGraph()
        root1 = ReferrerGraphNode(name="root1", id=100, type="str")
        root2 = ReferrerGraphNode(name="root2", id=200, type="str")
        target1 = ReferrerGraphNode(name="target1", id=300, type="str")
        target2 = ReferrerGraphNode(name="target2", id=400, type="str")

        # Manually set is_target attribute for testing
        object.__setattr__(target1, "is_target", True)
        object.__setattr__(target2, "is_target", True)

        graph.add_node(root1)
        graph.add_node(root2)
        graph.add_node(target1)
        graph.add_node(target2)
        graph.add_edge(root1, target1)
        graph.add_edge(root2, target2)

        result = utils.convert_graph_nodes(graph)

        assert len(result.graph_nodes) == 4

        # Verify multiple roots and targets
        assert set(result.root_ids) == {0, 1}  # root1 and root2
        assert set(result.target_ids) == {2, 3}  # target1 and target2

    def test_convert_graph_nodes_with_replacements(self) -> None:
        """
        Test convert_graph_nodes applies replacements to node names.
        """
        graph = nx.DiGraph()
        node1 = ReferrerGraphNode(name="module.Class.method", id=123, type="str")
        node2 = ReferrerGraphNode(name="module.AnotherClass", id=456, type="str")
        graph.add_node(node1)
        graph.add_node(node2)
        graph.add_edge(node1, node2)

        replacements = {"module.": "pkg.", "Class": "Klass"}
        result = utils.convert_graph_nodes(graph, replacements)

        assert len(result.graph_nodes) == 2
        assert result.graph_nodes[0].name == "pkg.Klass.method"
        assert result.graph_nodes[1].name == "pkg.AnotherKlass"

    def test_convert_graph_nodes_invalid_node_type(self) -> None:
        """
        Test convert_graph_nodes raises ValueError for invalid node types.
        """
        graph = nx.DiGraph()
        graph.add_node("invalid_node")

        with pytest.raises(ValueError, match="Unexpected type"):
            utils.convert_graph_nodes(graph)

    def test_convert_graph_nodes_invalid_edge_type(self) -> None:
        """
        Test convert_graph_nodes raises ValueError for invalid edge types.
        """
        graph = nx.DiGraph()
        node1 = ReferrerGraphNode(name="test_node", id=123, type="str")
        graph.add_node(node1)
        graph.add_node("invalid_node")
        graph.add_edge(node1, "invalid_node")

        with pytest.raises(ValueError, match="Unexpected type"):
            utils.convert_graph_nodes(graph)


class TestPluralize:
    """
    Tests for the `pluralize` function.
    """

    @pytest.mark.parametrize(
        "base_string,expected",
        [
            pytest.param("item", "item", id="simple_word"),
            pytest.param("", "", id="empty_string"),
        ],
    )
    def test_pluralize_singular_form(self, base_string: str, expected: str) -> None:
        """
        Test pluralize returns the base string unchanged when num is 1.
        """
        result = utils.pluralize(base_string, 1)
        assert result == expected

    @pytest.mark.parametrize(
        "base_string,num,expected",
        [
            pytest.param("item", 0, "items", id="zero_items"),
            pytest.param("item", 2, "items", id="two_items"),
            pytest.param("item", 100, "items", id="many_items"),
        ],
    )
    def test_pluralize_plural_form(self, base_string: str, num: int, expected: str) -> None:
        """
        Test pluralize adds 's' to the base string when num is not 1.
        """
        result = utils.pluralize(base_string, num)
        assert result == expected


class TestConvertGraphNodesToPrintable:
    """
    Tests for the `convert_graph_nodes_to_printable` function.
    """

    def test_graph_with_multiple_targets(self) -> None:
        """
        Test convert_graph_nodes_to_printable with a graph containing multiple target nodes.

        Graph shape: Two separate chains, each with a target node.
        root1 -> target1
        root2 -> target2
        """
        # given
        nodes = [
            ReferrerNode(id=0, name="root1", object_id=100, referent_ids=[1]),
            ReferrerNode(id=1, name="target1", object_id=200, referent_ids=[]),
            ReferrerNode(id=2, name="root2", object_id=300, referent_ids=[3]),
            ReferrerNode(id=3, name="target2", object_id=400, referent_ids=[]),
        ]
        referrer_graph = ReferrerGraph(target_ids={1, 3}, root_ids={0, 2}, graph_nodes=nodes)

        # when
        result = utils.convert_graph_nodes_to_printable(referrer_graph)

        # then
        result_nodes = list(result.nodes())
        assert len(result_nodes) == 4

        # Verify node type counts
        self._verify_node_counts_by_type(
            nodes=result_nodes,
            expected_targets=2,
            expected_roots=2,
            expected_cycle_members=0,
            expected_regular=0,
        )

        # Verify each node's properties individually
        root1_nodes = self._find_nodes_by_name(result_nodes, "root1")
        root1_node = one(root1_nodes)
        self._assert_node_properties(
            node=root1_node,
            expected_name="root1",
            expected_object_id=100,
            expected_is_cycle_member=False,
            expected_is_root=True,
            expected_is_target=False,
        )

        target1_nodes = self._find_nodes_by_name(result_nodes, "target1")
        target1_node = one(target1_nodes)
        self._assert_node_properties(
            node=target1_node,
            expected_name="target1",
            expected_object_id=200,
            expected_is_cycle_member=False,
            expected_is_root=False,
            expected_is_target=True,
        )

        root2_nodes = self._find_nodes_by_name(result_nodes, "root2")
        root2_node = one(root2_nodes)
        self._assert_node_properties(
            node=root2_node,
            expected_name="root2",
            expected_object_id=300,
            expected_is_cycle_member=False,
            expected_is_root=True,
            expected_is_target=False,
        )

        target2_nodes = self._find_nodes_by_name(result_nodes, "target2")
        target2_node = one(target2_nodes)
        self._assert_node_properties(
            node=target2_node,
            expected_name="target2",
            expected_object_id=400,
            expected_is_cycle_member=False,
            expected_is_root=False,
            expected_is_target=True,
        )

        # Verify graph edges (remember: edges are reversed in the printable graph)
        # Original: root1 -> target1, root2 -> target2
        # Reversed: target1 -> root1, target2 -> root2
        self._verify_node_successors(result, target1_node, ["root1"])
        self._verify_node_successors(result, target2_node, ["root2"])
        self._verify_node_successors(result, root1_node, [])  # Roots have no successors
        self._verify_node_successors(result, root2_node, [])  # Roots have no successors

        # Verify predecessors (opposite direction)
        self._verify_node_predecessors(result, root1_node, ["target1"])
        self._verify_node_predecessors(result, root2_node, ["target2"])
        self._verify_node_predecessors(result, target1_node, [])  # Targets have no predecessors
        self._verify_node_predecessors(result, target2_node, [])  # Targets have no predecessors

    def test_graph_with_multiple_roots(self) -> None:
        """
        Test convert_graph_nodes_to_printable with a graph containing multiple root nodes.

        Graph shape: pattern with two roots converging to one target.
        root1 -> intermediate1 -> target
        root2 -> intermediate2 -> target
        """
        # given
        nodes = [
            ReferrerNode(id=0, name="root1", object_id=100, referent_ids=[2]),
            ReferrerNode(id=1, name="root2", object_id=200, referent_ids=[3]),
            ReferrerNode(id=2, name="intermediate1", object_id=300, referent_ids=[4]),
            ReferrerNode(id=3, name="intermediate2", object_id=400, referent_ids=[4]),
            ReferrerNode(id=4, name="target", object_id=500, referent_ids=[]),
        ]
        referrer_graph = ReferrerGraph(target_ids={4}, root_ids={0, 1}, graph_nodes=nodes)

        # when
        result = utils.convert_graph_nodes_to_printable(referrer_graph)

        # then
        result_nodes = list(result.nodes())

        # Should have 5 nodes: no duplicates created since no single node has multiple referent_ids
        assert len(result_nodes) == 5

        # Verify node type counts
        self._verify_node_counts_by_type(
            nodes=result_nodes,
            expected_targets=1,
            expected_roots=2,
            # No cycle members since no single node has multiple referent_ids
            expected_cycle_members=0,
            expected_regular=2,  # Two intermediate nodes
        )

        # Verify root nodes
        root1_nodes = self._find_nodes_by_name(result_nodes, "root1")
        root1_node = one(root1_nodes)
        self._assert_node_properties(
            node=root1_node,
            expected_name="root1",
            expected_object_id=100,
            expected_is_cycle_member=False,
            expected_is_root=True,
            expected_is_target=False,
        )

        root2_nodes = self._find_nodes_by_name(result_nodes, "root2")
        root2_node = one(root2_nodes)
        self._assert_node_properties(
            node=root2_node,
            expected_name="root2",
            expected_object_id=200,
            expected_is_cycle_member=False,
            expected_is_root=True,
            expected_is_target=False,
        )

        # Verify target node
        target_nodes = self._find_nodes_by_name(result_nodes, "target")
        target_node = one(target_nodes)
        self._assert_node_properties(
            node=target_node,
            expected_name="target",
            expected_object_id=500,
            expected_is_cycle_member=False,
            expected_is_root=False,
            expected_is_target=True,
        )

        # Verify intermediate nodes (should have one of each, no duplicates)
        intermediate1_nodes = self._find_nodes_by_name(result_nodes, "intermediate1")
        intermediate1_node = one(intermediate1_nodes)
        self._assert_node_properties(
            node=intermediate1_node,
            expected_name="intermediate1",
            expected_object_id=300,
            expected_is_cycle_member=False,
            expected_is_root=False,
            expected_is_target=False,
        )

        intermediate2_nodes = self._find_nodes_by_name(result_nodes, "intermediate2")
        intermediate2_node = one(intermediate2_nodes)
        self._assert_node_properties(
            node=intermediate2_node,
            expected_name="intermediate2",
            expected_object_id=400,
            expected_is_cycle_member=False,
            expected_is_root=False,
            expected_is_target=False,
        )

        # Verify graph edges (remember: edges are reversed in the printable graph)
        # Original: root1 -> intermediate1 -> target, root2 -> intermediate2 -> target
        # Reversed: target -> intermediate1 -> root1, target -> intermediate2 -> root2
        self._verify_node_successors(result, target_node, ["intermediate1", "intermediate2"])
        self._verify_node_successors(result, intermediate1_node, ["root1"])
        self._verify_node_successors(result, intermediate2_node, ["root2"])
        self._verify_node_successors(result, root1_node, [])  # Roots have no successors
        self._verify_node_successors(result, root2_node, [])  # Roots have no successors

        # Verify predecessors
        self._verify_node_predecessors(result, root1_node, ["intermediate1"])
        self._verify_node_predecessors(result, root2_node, ["intermediate2"])
        self._verify_node_predecessors(result, intermediate1_node, ["target"])
        self._verify_node_predecessors(result, intermediate2_node, ["target"])
        self._verify_node_predecessors(result, target_node, [])  # Target has no predecessors

    def test_graph_with_multiple_referrers_to_nodes(self) -> None:
        """
        Test convert_graph_nodes_to_printable with nodes that have multiple referrers.

        Graph shape: Multiple nodes referring to the same intermediate node.
        root1 -> shared_node -> target
        root2 -> shared_node (same object as above)

        This test verifies that the function handles multiple nodes referring to the same object
        without creating cycle members (since no single node has multiple referent_ids).
        """
        # given
        nodes = [
            ReferrerNode(id=0, name="root1", object_id=100, referent_ids=[2]),
            ReferrerNode(id=1, name="root2", object_id=200, referent_ids=[2]),
            ReferrerNode(id=2, name="shared_node", object_id=300, referent_ids=[3]),
            ReferrerNode(id=3, name="target", object_id=400, referent_ids=[]),
        ]
        referrer_graph = ReferrerGraph(target_ids={3}, root_ids={0, 1}, graph_nodes=nodes)

        # when
        result = utils.convert_graph_nodes_to_printable(referrer_graph)

        # then
        result_nodes = list(result.nodes())

        # Should have exactly 4 nodes since no single node has multiple referent_ids
        assert len(result_nodes) == 4

        # Verify node type counts
        self._verify_node_counts_by_type(
            nodes=result_nodes,
            expected_targets=1,
            expected_roots=2,
            expected_cycle_members=0,  # No cycle members expected
            expected_regular=1,  # One shared node
        )

        # Verify each node's properties individually
        root1_nodes = self._find_nodes_by_name(result_nodes, "root1")
        root1_node = one(root1_nodes)
        self._assert_node_properties(
            node=root1_node,
            expected_name="root1",
            expected_object_id=100,
            expected_is_cycle_member=False,
            expected_is_root=True,
            expected_is_target=False,
        )

        root2_nodes = self._find_nodes_by_name(result_nodes, "root2")
        root2_node = one(root2_nodes)
        self._assert_node_properties(
            node=root2_node,
            expected_name="root2",
            expected_object_id=200,
            expected_is_cycle_member=False,
            expected_is_root=True,
            expected_is_target=False,
        )

        shared_node_nodes = self._find_nodes_by_name(result_nodes, "shared_node")
        shared_node = one(shared_node_nodes)
        self._assert_node_properties(
            node=shared_node,
            expected_name="shared_node",
            expected_object_id=300,
            expected_is_cycle_member=False,
            expected_is_root=False,
            expected_is_target=False,
        )

        target_nodes = self._find_nodes_by_name(result_nodes, "target")
        target_node = one(target_nodes)
        self._assert_node_properties(
            node=target_node,
            expected_name="target",
            expected_object_id=400,
            expected_is_cycle_member=False,
            expected_is_root=False,
            expected_is_target=True,
        )

        # Verify graph edges (remember: edges are reversed in the printable graph)
        # Original: root1 -> shared_node -> target, root2 -> shared_node -> target
        # Reversed: target -> shared_node -> root1, target -> shared_node -> root2
        self._verify_node_successors(result, target_node, ["shared_node"])
        self._verify_node_successors(result, shared_node, ["root1", "root2"])
        self._verify_node_successors(result, root1_node, [])  # Roots have no successors
        self._verify_node_successors(result, root2_node, [])  # Roots have no successors

        # Verify predecessors
        self._verify_node_predecessors(result, root1_node, ["shared_node"])
        self._verify_node_predecessors(result, root2_node, ["shared_node"])
        self._verify_node_predecessors(result, shared_node, ["target"])
        self._verify_node_predecessors(result, target_node, [])  # Target has no predecessors

    def test_cycle_detection_and_breaking(self) -> None:
        """
        Test convert_graph_nodes_to_printable handles multiple referent_ids by creating
        duplicate nodes.

        Graph shape: Two nodes with multiple referent_ids create cycle members.
        root -> node1, node2 (root has 2 referents)
        node1 -> target1, target2, intermediate (node1 has 3 referents)
        node2 -> intermediate
        """
        # given
        nodes = [
            ReferrerNode(id=0, name="root", object_id=100, referent_ids=[1, 2]),  # 2 referents
            ReferrerNode(id=1, name="node1", object_id=200, referent_ids=[3, 4, 5]),  # 3 referents
            ReferrerNode(id=2, name="node2", object_id=250, referent_ids=[5]),
            ReferrerNode(id=3, name="target1", object_id=300, referent_ids=[]),
            ReferrerNode(id=4, name="target2", object_id=400, referent_ids=[]),
            ReferrerNode(id=5, name="intermediate", object_id=500, referent_ids=[]),
        ]
        referrer_graph = ReferrerGraph(target_ids={3, 4}, root_ids={0}, graph_nodes=nodes)

        # when
        result = utils.convert_graph_nodes_to_printable(referrer_graph)

        # then
        result_nodes = list(result.nodes())

        # Should have 9 nodes: original 6 + 3 duplicates (1 root + 2xnode1)
        assert len(result_nodes) == 9

        # Verify node type counts
        self._verify_node_counts_by_type(
            nodes=result_nodes,
            expected_targets=2,  # target1, target2
            expected_roots=2,  # Original root + duplicate root (cycle member)
            expected_cycle_members=3,  # 1 duplicate root + 2 duplicate node1s
            expected_regular=3,  # node1, node2, intermediate (originals only)
        )

        # Verify root nodes (should have original + duplicate)
        root_nodes = self._find_nodes_by_name(result_nodes, "root")
        assert len(root_nodes) == 2

        # Find original and duplicate root
        original_root = self._get_node_by_name_and_cycle_status(result_nodes, "root", False)
        duplicate_root = self._get_node_by_name_and_cycle_status(result_nodes, "root", True)

        self._assert_node_properties(
            node=original_root,
            expected_name="root",
            expected_object_id=100,
            expected_is_cycle_member=False,
            expected_is_root=True,
            expected_is_target=False,
        )

        self._assert_node_properties(
            node=duplicate_root,
            expected_name="root",
            expected_object_id=100,
            expected_is_cycle_member=True,
            expected_is_root=True,
            expected_is_target=False,
        )

        # Verify node1 nodes (should have original + 2 duplicates)
        node1_nodes = self._find_nodes_by_name(result_nodes, "node1")
        assert len(node1_nodes) == 3

        original_node1 = self._get_node_by_name_and_cycle_status(result_nodes, "node1", False)
        duplicate_node1s = [node for node in node1_nodes if node.is_cycle_member]
        assert len(duplicate_node1s) == 2

        self._assert_node_properties(
            node=original_node1,
            expected_name="node1",
            expected_object_id=200,
            expected_is_cycle_member=False,
            expected_is_root=False,
            expected_is_target=False,
        )

        for duplicate_node1 in duplicate_node1s:
            self._assert_node_properties(
                node=duplicate_node1,
                expected_name="node1",
                expected_object_id=200,
                expected_is_cycle_member=True,
                expected_is_root=False,
                expected_is_target=False,
            )

        # Verify other nodes
        node2_nodes = self._find_nodes_by_name(result_nodes, "node2")
        node2_node = one(node2_nodes)
        self._assert_node_properties(
            node=node2_node,
            expected_name="node2",
            expected_object_id=250,
            expected_is_cycle_member=False,
            expected_is_root=False,
            expected_is_target=False,
        )

        target1_nodes = self._find_nodes_by_name(result_nodes, "target1")
        target1_node = one(target1_nodes)
        self._assert_node_properties(
            node=target1_node,
            expected_name="target1",
            expected_object_id=300,
            expected_is_cycle_member=False,
            expected_is_root=False,
            expected_is_target=True,
        )

        target2_nodes = self._find_nodes_by_name(result_nodes, "target2")
        target2_node = one(target2_nodes)
        self._assert_node_properties(
            node=target2_node,
            expected_name="target2",
            expected_object_id=400,
            expected_is_cycle_member=False,
            expected_is_root=False,
            expected_is_target=True,
        )

        intermediate_nodes = self._find_nodes_by_name(result_nodes, "intermediate")
        intermediate_node = one(intermediate_nodes)
        self._assert_node_properties(
            node=intermediate_node,
            expected_name="intermediate",
            expected_object_id=500,
            expected_is_cycle_member=False,
            expected_is_root=False,
            expected_is_target=False,
        )

        # Verify graph edges (remember: edges are reversed in the printable graph)
        # Original: root -> node1, node2 (root has 2 referents)
        #           node1 -> target1, target2, intermediate (node1 has 3 referents)
        #           node2 -> intermediate
        # Reversed: target1 -> node1 (original), target2 -> node1 (duplicate1),
        #           intermediate -> node1 (duplicate2), node2, node1 -> root (original),
        #           node2 -> root (duplicate)

        # Verify successors based on the debug output
        self._verify_node_successors(result, target1_node, ["node1"])
        self._verify_node_successors(result, target2_node, ["node1"])
        self._verify_node_successors(result, intermediate_node, ["node2", "node1"])
        self._verify_node_successors(result, original_node1, ["root"])
        self._verify_node_successors(result, node2_node, ["root"])

        # All root nodes and cycle member node1s should have no successors
        self._verify_node_successors(result, original_root, [])
        self._verify_node_successors(result, duplicate_root, [])
        for duplicate_node1 in duplicate_node1s:
            self._verify_node_successors(result, duplicate_node1, [])

        # Verify predecessors based on the debug output
        self._verify_node_predecessors(result, original_root, ["node1"])
        self._verify_node_predecessors(result, duplicate_root, ["node2"])
        self._verify_node_predecessors(result, original_node1, ["target1"])

        # Find which duplicate node1 is pointed to by which node
        duplicate_node1_with_target2_pred = None
        duplicate_node1_with_intermediate_pred = None
        for dup_node1 in duplicate_node1s:
            predecessors = [pred.name for pred in result.predecessors(dup_node1)]
            if "target2" in predecessors:
                duplicate_node1_with_target2_pred = dup_node1
            elif "intermediate" in predecessors:
                duplicate_node1_with_intermediate_pred = dup_node1

        assert duplicate_node1_with_target2_pred is not None
        assert duplicate_node1_with_intermediate_pred is not None

        self._verify_node_predecessors(result, duplicate_node1_with_target2_pred, ["target2"])
        self._verify_node_predecessors(
            result, duplicate_node1_with_intermediate_pred, ["intermediate"]
        )
        self._verify_node_predecessors(result, node2_node, ["intermediate"])

        # Targets and intermediate should have no predecessors
        self._verify_node_predecessors(result, target1_node, [])
        self._verify_node_predecessors(result, target2_node, [])
        self._verify_node_predecessors(result, intermediate_node, [])

    def test_complex_graph_with_multiple_characteristics(self) -> None:
        """
        Test convert_graph_nodes_to_printable with a complex graph having multiple targets,
        roots, and cycle members.

        Graph shape: Complex graph combining multiple features.
        root1 -> shared_node -> target1
        root2 -> shared_node (same object)
        root3 -> target2, intermediate (root3 has multiple referent_ids)
        """
        # given
        nodes = [
            ReferrerNode(id=0, name="root1", object_id=100, referent_ids=[3]),
            ReferrerNode(id=1, name="root2", object_id=200, referent_ids=[3]),
            ReferrerNode(
                id=2, name="root3", object_id=250, referent_ids=[5, 6]
            ),  # Multiple referent_ids
            ReferrerNode(id=3, name="shared_node", object_id=300, referent_ids=[4]),
            ReferrerNode(id=4, name="target1", object_id=400, referent_ids=[]),
            ReferrerNode(id=5, name="target2", object_id=500, referent_ids=[]),
            ReferrerNode(id=6, name="intermediate", object_id=600, referent_ids=[]),
        ]
        referrer_graph = ReferrerGraph(target_ids={4, 5}, root_ids={0, 1, 2}, graph_nodes=nodes)

        # when
        result = utils.convert_graph_nodes_to_printable(referrer_graph)

        # then
        result_nodes = list(result.nodes())

        # Should have 8 nodes: original 7 + 1 duplicate for root3's second referent_id
        assert len(result_nodes) == 8

        # Verify node type counts
        self._verify_node_counts_by_type(
            nodes=result_nodes,
            expected_targets=2,  # target1, target2
            expected_roots=4,  # root1, root2, root3 (original), root3 (duplicate)
            expected_cycle_members=1,  # duplicate root3
            expected_regular=2,  # shared_node, intermediate
        )

        # Verify individual nodes
        root1_nodes = self._find_nodes_by_name(result_nodes, "root1")
        root1_node = one(root1_nodes)
        self._assert_node_properties(
            node=root1_node,
            expected_name="root1",
            expected_object_id=100,
            expected_is_cycle_member=False,
            expected_is_root=True,
            expected_is_target=False,
        )

        root2_nodes = self._find_nodes_by_name(result_nodes, "root2")
        root2_node = one(root2_nodes)
        self._assert_node_properties(
            node=root2_node,
            expected_name="root2",
            expected_object_id=200,
            expected_is_cycle_member=False,
            expected_is_root=True,
            expected_is_target=False,
        )

        # root3 should have 2 instances: original + duplicate (cycle member)
        root3_nodes = self._find_nodes_by_name(result_nodes, "root3")
        assert len(root3_nodes) == 2

        original_root3 = next(node for node in root3_nodes if not node.is_cycle_member)
        duplicate_root3 = next(node for node in root3_nodes if node.is_cycle_member)

        self._assert_node_properties(
            node=original_root3,
            expected_name="root3",
            expected_object_id=250,
            expected_is_cycle_member=False,
            expected_is_root=True,
            expected_is_target=False,
        )

        self._assert_node_properties(
            node=duplicate_root3,
            expected_name="root3",
            expected_object_id=250,
            expected_is_cycle_member=True,
            expected_is_root=True,
            expected_is_target=False,
        )

        shared_node_nodes = self._find_nodes_by_name(result_nodes, "shared_node")
        shared_node = one(shared_node_nodes)
        self._assert_node_properties(
            node=shared_node,
            expected_name="shared_node",
            expected_object_id=300,
            expected_is_cycle_member=False,
            expected_is_root=False,
            expected_is_target=False,
        )

        target1_nodes = self._find_nodes_by_name(result_nodes, "target1")
        target1_node = one(target1_nodes)
        self._assert_node_properties(
            node=target1_node,
            expected_name="target1",
            expected_object_id=400,
            expected_is_cycle_member=False,
            expected_is_root=False,
            expected_is_target=True,
        )

        target2_nodes = self._find_nodes_by_name(result_nodes, "target2")
        target2_node = one(target2_nodes)
        self._assert_node_properties(
            node=target2_node,
            expected_name="target2",
            expected_object_id=500,
            expected_is_cycle_member=False,
            expected_is_root=False,
            expected_is_target=True,
        )

        intermediate_nodes = self._find_nodes_by_name(result_nodes, "intermediate")
        intermediate_node = one(intermediate_nodes)
        self._assert_node_properties(
            node=intermediate_node,
            expected_name="intermediate",
            expected_object_id=600,
            expected_is_cycle_member=False,
            expected_is_root=False,
            expected_is_target=False,
        )

        # Verify graph edges (remember: edges are reversed in the printable graph)
        # Original: root1 -> shared_node -> target1, root2 -> shared_node -> target1,
        #           root3 -> target2, intermediate (root3 has multiple referent_ids)
        # Reversed: target1 -> shared_node -> root1, root2
        #           target2 -> root3 (original), intermediate -> root3 (duplicate)
        self._verify_node_successors(result, target1_node, ["shared_node"])
        self._verify_node_successors(result, target2_node, ["root3"])
        self._verify_node_successors(result, shared_node, ["root1", "root2"])
        self._verify_node_successors(result, intermediate_node, ["root3"])

        # All root nodes should have no successors
        self._verify_node_successors(result, root1_node, [])
        self._verify_node_successors(result, root2_node, [])
        self._verify_node_successors(result, original_root3, [])
        self._verify_node_successors(result, duplicate_root3, [])

        # Verify predecessors
        self._verify_node_predecessors(result, root1_node, ["shared_node"])
        self._verify_node_predecessors(result, root2_node, ["shared_node"])
        self._verify_node_predecessors(result, original_root3, ["target2"])
        self._verify_node_predecessors(result, duplicate_root3, ["intermediate"])
        self._verify_node_predecessors(result, shared_node, ["target1"])
        self._verify_node_predecessors(result, target1_node, [])
        self._verify_node_predecessors(result, target2_node, [])
        self._verify_node_predecessors(result, intermediate_node, [])

    def _find_nodes_by_object_id(
        self, nodes: List[PrintableReferrerNode], object_id: int
    ) -> List[PrintableReferrerNode]:
        """
        Helper method to find all nodes with a specific object_id.
        """
        return [node for node in nodes if node.object_id == object_id]

    def _find_nodes_by_name(
        self, nodes: List[PrintableReferrerNode], name: str
    ) -> List[PrintableReferrerNode]:
        """
        Helper method to find all nodes with a specific name.
        """
        return [node for node in nodes if node.name == name]

    def _assert_node_properties(
        self,
        node: PrintableReferrerNode,
        expected_name: str,
        expected_object_id: int,
        expected_is_cycle_member: bool,
        expected_is_root: bool,
        expected_is_target: bool,
    ) -> None:
        """
        Helper method to assert all properties of a PrintableReferrerNode.
        """
        assert node.name == expected_name
        assert node.object_id == expected_object_id
        assert node.is_cycle_member == expected_is_cycle_member
        assert node.is_root == expected_is_root
        assert node.is_target == expected_is_target

    def _verify_node_counts_by_type(
        self,
        nodes: List[PrintableReferrerNode],
        expected_targets: int,
        expected_roots: int,
        expected_cycle_members: int,
        expected_regular: int,
    ) -> None:
        """
        Helper method to verify counts of different node types.
        """
        target_nodes = [node for node in nodes if node.is_target]
        root_nodes = [node for node in nodes if node.is_root]
        cycle_member_nodes = [node for node in nodes if node.is_cycle_member]
        regular_nodes = [
            node for node in nodes if not (node.is_target or node.is_root or node.is_cycle_member)
        ]

        assert len(target_nodes) == expected_targets
        assert len(root_nodes) == expected_roots
        assert len(cycle_member_nodes) == expected_cycle_members
        assert len(regular_nodes) == expected_regular

    def _verify_edge_exists(
        self, graph: nx.DiGraph, from_node: PrintableReferrerNode, to_node: PrintableReferrerNode
    ) -> None:
        """
        Helper method to verify that an edge exists between two nodes.
        """
        successors = list(graph.successors(from_node))
        assert to_node in successors, (
            f"Expected edge from {from_node.name} to {to_node.name} not found"
        )

    def _verify_node_successors(
        self, graph: nx.DiGraph, node: PrintableReferrerNode, expected_successor_names: List[str]
    ) -> None:
        """
        Helper method to verify that a node has exactly the expected successors.
        """
        successors = list(graph.successors(node))
        actual_successor_names = [succ.name for succ in successors]
        actual_successor_names.sort()
        expected_successor_names.sort()
        assert actual_successor_names == expected_successor_names, (
            f"Node {node.name} expected successors {expected_successor_names}, "
            f"but got {actual_successor_names}"
        )

    def _verify_node_predecessors(
        self, graph: nx.DiGraph, node: PrintableReferrerNode, expected_predecessor_names: List[str]
    ) -> None:
        """
        Helper method to verify that a node has exactly the expected predecessors.
        """
        predecessors = list(graph.predecessors(node))
        actual_predecessor_names = [pred.name for pred in predecessors]
        actual_predecessor_names.sort()
        expected_predecessor_names.sort()
        assert actual_predecessor_names == expected_predecessor_names, (
            f"Node {node.name} expected predecessors {expected_predecessor_names}, "
            f"but got {actual_predecessor_names}"
        )

    def _get_node_by_name_and_cycle_status(
        self, nodes: List[PrintableReferrerNode], name: str, is_cycle_member: bool
    ) -> PrintableReferrerNode:
        """
        Helper method to get a specific node by name and cycle member status.
        Useful when there are duplicate nodes with the same name.
        """
        matching_nodes = [
            node for node in nodes if node.name == name and node.is_cycle_member == is_cycle_member
        ]
        return one(matching_nodes)


class TestGetBudget:
    """
    Tests for the `get_budget` function.
    """

    @pytest.mark.parametrize(
        "object_type_counts,total_budget,expected_budget",
        [
            pytest.param(
                {},
                10,
                {},
                id="Empty types dictionary",
            ),
            pytest.param(
                {str: 1, int: 1, list: 1, dict: 1, tuple: 1},
                5,
                {str: 1, int: 1, list: 1, dict: 1, tuple: 1},
                id="Types equal to budget",
            ),
            pytest.param(
                {str: 1, int: 1, list: 1, dict: 1, tuple: 1, set: 1},
                5,
                {str: 1, int: 1, list: 1, dict: 1, tuple: 1, set: 1},
                id="More types than budget",
            ),
            pytest.param(
                {str: 1},
                10,
                {str: 10},
                id="Single type with budget larger than needed",
            ),
            pytest.param(
                {str: 1, list: 1},
                10,
                {str: 5, list: 5},
                id="Multiple types with budget larger than needed",
            ),
            pytest.param(
                {str: 20, int: 4},
                10,
                {str: 8, int: 2},
                id="Two types with proportional distribution",
            ),
            pytest.param(
                {str: 100, int: 50, list: 25},
                20,
                {str: 11, int: 6, list: 3},
                id="Three types with proportional distribution",
            ),
            pytest.param(
                {str: 10, int: 10},
                10,
                {str: 5, int: 5},
                id="Two types with equal counts",
            ),
            pytest.param(
                {str: 1000, int: 1},
                10,
                {str: 9, int: 1},
                id="Highly skewed distribution",
            ),
        ],
    )
    def test_get_object_type_budgets(
        self,
        object_type_counts: dict[type, int],
        total_budget: int,
        expected_budget: dict[type, int],
    ) -> None:
        """
        Tests that get_budget calculates the correct budget for object types.
        """
        budget = utils.get_object_type_budgets(
            object_type_counts=object_type_counts, total_budget=total_budget
        )
        assert budget == expected_budget
