"""
Performance test based on the barbell example.
"""

import random
from dataclasses import dataclass, field

import networkx as nx
import pytest
from pytest_benchmark.fixture import BenchmarkFixture

from memalot import leak_monitor


@dataclass
class Node:
    """
    A node in a graph.
    """

    value: int
    adjacent_nodes: list["Node"] = field(default_factory=list)


def create_graph(m1: int, m2: int) -> tuple[dict[str, Node], Node]:
    """
    Creates a barbell graph with m1 nodes in each complete graph and m2 nodes in the path.

    Returns a tuple of (cache, end_node).
    """
    graph = nx.barbell_graph(m1, m2)
    node_map = {node_id: Node(node_id) for node_id in graph.nodes()}
    for node_id, node_obj in node_map.items():
        for neighbor_id in graph.neighbors(node_id):
            neighbor_obj = node_map[neighbor_id]
            node_obj.adjacent_nodes.append(neighbor_obj)
    start_node = node_map[0]
    cache = {"start_node": start_node}
    end_node = node_map[max(node_map.keys())]
    return cache, end_node


@leak_monitor(
    check_referrers=True,
    max_object_age_calls=1,
    max_object_details=2,
    # Set output to nowhere
    output_func=lambda _: None,
)
def add_nodes_to_end(end_node: Node, num_new_nodes: int) -> None:
    """
    Adds new nodes to the end node.
    """
    for _ in range(num_new_nodes):
        new_node = Node(random.randint(1, 1000))
        end_node.adjacent_nodes.append(new_node)


@pytest.mark.performance
class TestBarbellPerformance:
    """
    Performance tests based on the barbell example.
    """

    def test_barbell(self, benchmark: BenchmarkFixture) -> None:
        """
        Test the performance of the barbell example with m1=30, m2=20, two iterations,
        and max_object_summaries=2.
        """

        def run_barbell() -> None:
            cache, end_node = create_graph(m1=30, m2=20)
            # Run for two iterations
            add_nodes_to_end(end_node, 3)
            add_nodes_to_end(end_node, 3)

        benchmark.pedantic(run_barbell, rounds=1)  # type: ignore

        # Based on preliminary testing, the test should complete in well under 200 seconds
        # on average, even on Github's workers (this is about 4x what it takes on a fast laptop).
        # This assertion allows for some variability but catches very significant performance
        # regressions.
        assert benchmark.stats is not None
        assert benchmark.stats.stats.mean < 200.0, (
            f"Performance regression detected: mean time {benchmark.stats.stats.mean:.2f}s "
            f"exceeds 200s"
        )
