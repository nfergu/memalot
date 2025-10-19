"""
Integration test for the converging tree example.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import pytest

from memalot import leak_monitor
from tests_integration.utils import (
    assert_iteration_count,
    assert_object_details_types,
    assert_object_type_details,
    assert_referrer_graphs_have_root_names,
    assert_type_summaries,
    assert_warmup_iteration,
    read_single_report,
)


class TreeNode:
    """
    A node in a tree with a parent reference.
    """

    def __init__(self, parent: Optional["TreeNode"]):
        self.parent = parent


class RootNode(TreeNode):
    """
    A root node with no parent.
    """

    pass


class TreeNodeHolder:
    """
    A holder for multiple tree nodes (leaf nodes).
    """

    def __init__(self, node1: TreeNode, node2: TreeNode, node3: TreeNode, node4: TreeNode):
        self.node1 = node1
        self.node2 = node2
        self.node3 = node3
        self.node4 = node4


@pytest.mark.integration
class TestConvergingTreeExample:
    """
    Tests for the converging tree example.
    """

    def test_converging_tree_example(self, tmp_path: Path) -> None:
        """
        Tests that the converging tree example generates the expected report content.

        This test verifies that:
        - TreeNodes created in a converging tree structure are properly detected as leaks
        - Each iteration reports exactly 6 TreeNodes (1 root, 2 level1, 4 level2)
          and 1 TreeNodeHolder
        - Type summaries contain RootNode, TreeNode, and TreeNodeHolder types
        - Referrer graphs correctly identify roots and leaf_holders as roots
        """

        # given: a construct_converging_tree function with leak monitoring
        @leak_monitor(
            report_directory=tmp_path,
            max_object_details=4,
        )
        def construct_converging_tree(
            roots: list[RootNode], leaf_holders: list[TreeNodeHolder]
        ) -> None:
            root = RootNode(parent=None)
            level1_1 = TreeNode(parent=root)
            level1_2 = TreeNode(parent=root)
            level2_1 = TreeNode(parent=level1_1)
            level2_2 = TreeNode(parent=level1_1)
            level2_3 = TreeNode(parent=level1_2)
            level2_4 = TreeNode(parent=level1_2)
            roots.append(root)
            leaf_holder = TreeNodeHolder(
                node1=level2_1, node2=level2_2, node3=level2_3, node4=level2_4
            )
            leaf_holders.append(leaf_holder)

        roots: list[RootNode] = []
        leaf_holders: list[TreeNodeHolder] = []

        # when: we call construct_converging_tree 3 times to generate reports
        for _ in range(3):
            construct_converging_tree(roots, leaf_holders)

        # then: read the report from disk and verify
        full_report = read_single_report(tmp_path=tmp_path)
        assert_iteration_count(full_report=full_report, expected_count=3)

        # Iteration 1: warmup - no leaks reported
        iteration_1 = full_report.iterations[0]
        assert iteration_1.iteration_number == 1
        assert_warmup_iteration(iteration=iteration_1)

        # Iteration 2: exactly 1 RootNode, 4 TreeNodes, and 1 TreeNodeHolder
        iteration_2 = full_report.iterations[1]
        assert iteration_2.iteration_number == 2

        # Check type summaries
        type_summaries = iteration_2.leak_summary.type_summaries
        expected_types = {
            "tests_integration.test_converging_tree.RootNode",
            "tests_integration.test_converging_tree.TreeNode",
            "tests_integration.test_converging_tree.TreeNodeHolder",
        }
        # We expect 1 RootNode, 6 TreeNodes (2 level1 + 4 level2), 1 TreeNodeHolder
        assert_type_summaries(
            type_summaries=type_summaries, expected_types=expected_types, expected_counts={1, 6}
        )

        # Check object details
        object_details_list = list(iteration_2.object_details_list)
        assert_object_details_types(
            object_details_list=object_details_list, expected_types=expected_types
        )

        # Verify RootNode objects
        assert_object_type_details(
            object_details_list=object_details_list,
            object_type="tests_integration.test_converging_tree.RootNode",
            expected_count=1,
            expected_target_names={"RootNode (object)"},
        )

        # Verify TreeNode objects (sample of 2, since max_object_details=4)
        assert_object_type_details(
            object_details_list=object_details_list,
            object_type="tests_integration.test_converging_tree.TreeNode",
            expected_count=2,
            expected_target_names={"TreeNode (object)"},
        )

        # Verify TreeNodeHolder objects
        assert_object_type_details(
            object_details_list=object_details_list,
            object_type="tests_integration.test_converging_tree.TreeNodeHolder",
            expected_count=1,
            expected_target_names={"TreeNodeHolder (object)"},
        )

        # Verify root names for all objects
        expected_root_names = {
            "test_converging_tree_example.roots (local)",
            "test_converging_tree_example.leaf_holders (local)",
            "construct_converging_tree args (local)",
        }
        assert_referrer_graphs_have_root_names(
            object_details_list=object_details_list,
            expected_root_names=expected_root_names,
        )

        # Iteration 3: same as iteration 2
        iteration_3 = full_report.iterations[2]
        assert iteration_3.iteration_number == 3

        type_summaries_3 = iteration_3.leak_summary.type_summaries
        assert_type_summaries(
            type_summaries=type_summaries_3, expected_types=expected_types, expected_counts={1, 6}
        )
