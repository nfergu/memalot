import dataclasses
import gc
import inspect
import logging
from collections.abc import Callable
from typing import Any, Dict, Mapping, Type

import networkx as nx
from referrers import ReferrerGraphNode
from rich.markup import escape

from memalot.base import ReferrerGraph, ReferrerNode
from memalot.themes import (
    MEMORY_ABSOLUTE,
    OBJECT_ID,
    REFERRER_NAME,
    REFERRER_SUFFIX_CYCLE,
    REFERRER_SUFFIX_LEAF,
)

LOG = logging.getLogger(__name__)

_PACKAGE_PREFIX = "memalot"

_KIB = 1024
_MIB = _KIB**2
_GIB = _KIB**3


def as_mib(num_bytes: int, tag: str = MEMORY_ABSOLUTE) -> str:
    """
    Returns a string representation of the number of byte1s in MiB, rounded to one decimal
    place.
    """
    return f"[{tag}]{num_bytes / 1024 / 1024:.1f}[/{tag}] MiB"


def as_mib_sf(num_bytes: int, tag: str = MEMORY_ABSOLUTE) -> str:
    """
    Returns a string representation of the number of bytes in MiB, rounded to three significant
    figures.
    """
    return f"[{tag}]{num_bytes / 1024 / 1024:.3g}[/{tag}] MiB"


def format_bytes(num_bytes: int, tag: str = MEMORY_ABSOLUTE) -> str:
    """
    Converts a size in bytes to a human-readable string in B, KiB, MiB, or GiB.

    This function takes an integer representing the number of bytes and returns
    a formatted string with the most appropriate unit. The rounding is adjusted
    based on the unit.
    """
    if not isinstance(num_bytes, int) or num_bytes < 0:
        raise ValueError("Input must be a non-negative integer.")

    if num_bytes == 0:
        return "0 B"

    if num_bytes < _KIB:
        # For bytes, no decimal places are needed
        return f"[{tag}]{num_bytes}[/{tag}] B"
    elif num_bytes < _MIB:
        # For KiB, one decimal place is appropriate
        kib_value = num_bytes / _KIB
        return f"[{tag}]{kib_value:.1f}[/{tag}] KiB"
    elif num_bytes < _GIB:
        # For MiB, two decimal places offer good precision
        mib_value = num_bytes / _MIB
        return f"[{tag}]{mib_value:.2f}[/{tag}] MiB"
    else:
        # For GiB, two decimal places are also suitable
        gib_value = num_bytes / _GIB
        return f"[{tag}]{gib_value:.2f}[/{tag}] GiB"


def get_full_type_name(obj_type: Type[Any]) -> str:
    """
    Gets the full type name of an object.
    """
    return f"{obj_type.__module__}.{obj_type.__name__}"


def get_module_prefix() -> str | None:
    """
    Determine the module prefix from the top-level package of the calling code.

    This is the first package that is not part of Memalot.
    """
    stack_frames = inspect.stack()
    for frame_info in stack_frames:
        frame_module = inspect.getmodule(frame_info.frame)
        if frame_module and not frame_module.__name__.startswith(_PACKAGE_PREFIX):
            # Use the top-level package of the calling code as the module prefix
            # (with a trailing dot). For example, if the calling code is in a module
            # called my_module.do_thing, the module prefix would be "my_module.".
            # In some cases (like Jupyter notebooks), there may not be a top-level
            # package, in which there won't be any module prefixes. We log a warning
            # in this case.
            return f"{frame_module.__name__.split('.')[0]}."
    else:  # pragma: no cover
        LOG.warning(
            "Could not determine the top-level package of the calling code. "
            "You can specify the referrers_module_prefixes parameter to set this explicitly."
        )
        return None


def get_objects(
    max_untracked_search_depth: int = 3, get_objects_func: Callable[[], list[Any]] = gc.get_objects
) -> list[Any]:
    """
    Gets all objects that are currently in memory in the Python process, that are not eligible
    for garbage collection.

    This is different from `gc.get_objects` in a few ways:

     - It always performs a garbage collection when it is called.
     - It finds untracked objects, as long as they are referred to (directly or indirectly) by
       tracked objects. Untracked objects include, for example, mutable objects and collections
       containing only immutable objects in CPython. The `max_untracked_search_depth` controls
       how deep this function searches for untracked objects if they are not referred to directly
       by tracked objects. Setting this to a higher value is more likely to find untracked
       objects but will take more time.
     - It ignores frame objects.
     - It removes duplicate objects.

    :param max_untracked_search_depth: The maximum depth to search for untracked objects. This
        defaults to 3, which is enough to find most untracked objects. For example, this
        will find objects in tuples that are in another collection. However, it may not find
        certain untracked objects, like nested tuples.
    """
    gc.collect()
    tracked_objects = get_objects_func()

    all_objects = []
    seen_ids = set()

    for obj in tracked_objects:
        try:
            if not _is_excluded(obj):
                obj_id = id(obj)
                if obj_id not in seen_ids:
                    all_objects.append(obj)
                    seen_ids.add(obj_id)
        except ReferenceError:  # pragma: no cover
            # Some objects might not be accessible (e.g., weak reference proxies
            # where the underlying object has been garbage collected)
            pass

    # Search the referents of the objects we have found, looking for untracked objects.
    objects_to_search = list(all_objects)
    for _ in range(max_untracked_search_depth):
        new_untracked_referents = []
        for obj in objects_to_search:
            try:
                referents = gc.get_referents(obj)
                # Go through all referents and add them to new_untracked_referents if we
                # haven't seen them before, and they are untracked (and not excluded).
                for referent in referents:
                    referent_id = id(referent)
                    if (
                        referent_id not in seen_ids
                        and not gc.is_tracked(referent)
                        and not _is_excluded(referent)
                    ):
                        new_untracked_referents.append(referent)
                        all_objects.append(referent)
                        seen_ids.add(referent_id)
            except ReferenceError:  # pragma: no cover
                # Some objects might not be accessible
                pass
        objects_to_search = new_untracked_referents

    return all_objects


def _is_excluded(obj: Any) -> bool:
    try:
        return inspect.isframe(obj)
    except ReferenceError:  # pragma: no cover
        # This can happen if the object is a weak reference proxy where the underlying
        # object has been garbage collected. We just ignore these objects.
        return True


def convert_graph_nodes(
    referrer_graph: nx.DiGraph, replacements: Mapping[str, str] | None = None
) -> ReferrerGraph:
    """
    Converts a networkx graph with ReferrerGraphNode nodes to a ReferrerGraph
    with ReferrerNode nodes, transferring node attributes.
    """
    unique_ids: Dict[ReferrerGraphNode, int] = {}
    graph_nodes: list[ReferrerNode] = []
    target_ids: set[int] = set()
    root_ids: set[int] = set()

    # First pass: create nodes and assign unique IDs
    for unique_id, node in enumerate(referrer_graph.nodes()):
        unique_ids[node] = unique_id
        if isinstance(node, ReferrerGraphNode):
            name = node.name
            if replacements is not None:
                for old_name, new_name in replacements.items():
                    name = name.replace(old_name, new_name)
            # We ignore type here, as it doesn't seem to add anything that isn't present
            # in the name
            referrer_node = ReferrerNode(
                id=unique_id,
                name=name,
                object_id=node.id,
                referent_ids=[],  # Will be populated in second pass
            )
            graph_nodes.append(referrer_node)

            # Track target and root nodes separately
            if node.is_target:
                target_ids.add(unique_id)
            is_root = referrer_graph.in_degree(node) == 0
            if is_root:
                root_ids.add(unique_id)

        else:
            raise ValueError(f"Unexpected type: {type(node)}")

    # Second pass: populate referent_ids based on edges
    for u, v in referrer_graph.edges():
        if isinstance(u, ReferrerGraphNode) and isinstance(v, ReferrerGraphNode):
            u_id = unique_ids[u]
            v_id = unique_ids[v]
            graph_nodes[u_id].referent_ids.append(v_id)
        else:  # pragma: no cover
            raise ValueError(f"Unexpected type: {type(u)} or {type(v)}")

    return ReferrerGraph(target_ids=target_ids, root_ids=root_ids, graph_nodes=graph_nodes)


def pluralize(base_string: str, num: int) -> str:
    """
    Very simple pluralization. This just adds an "s" if `num` != 1.
    """
    if num == 1:
        return base_string
    else:
        return f"{base_string}s"


# Note: this is not a pydantic data class
@dataclasses.dataclass(frozen=True)
class PrintableReferrerNode:
    unique_id: int
    """
    A unique ID for the node.
    """

    name: str
    """
    A meaningful name for the referrer. For example, if the referrer is a local variable,
    the name would be the variable name, suffixed with "(local)".
    """

    object_id: int
    """
    A unique ID for the referrer object. If the referrer is not an object then this is the
    ID of the object it refers to.
    """

    is_cycle_member: bool = False
    """
    Whether the referrer is part of a cycle in the graph. If this is `True`, the referrer
    will be the last node in a branch of the graph.
    """

    is_root: bool = False
    """
    Whether this node is a root in the graph.
    """

    is_target: bool = False
    """
    Whether this node is the target node (i.e. the object we are finding referrers for).
    """

    def __str__(self) -> str:
        if self.is_cycle_member:
            suffix = f"[{REFERRER_SUFFIX_CYCLE}](cycle member)[/{REFERRER_SUFFIX_CYCLE}]"
        elif self.is_root:
            suffix = f"[{REFERRER_SUFFIX_LEAF}](root)[/{REFERRER_SUFFIX_LEAF}]"
        else:
            suffix = ""
        return (
            f"[{REFERRER_NAME}]{escape(self.name)}[/{REFERRER_NAME}] "
            f"[{OBJECT_ID}](id={self.object_id})[/{OBJECT_ID}] "
            f"{suffix}"
        )


def convert_graph_nodes_to_printable(referrer_graph: ReferrerGraph) -> nx.DiGraph:
    """
    Converts a ReferrerGraph with ReferrerNode nodes, as produced by
    `utils.convert_graph_nodes` to a graph with `_PrintableReferrerNode`s.

    Cycles in the graph are broken by nodes with multiple children and marking all duplicated
    nodes as cycle members (except for the first, original, instance of the node).

    The edges in the returned graph are reversed, so that they point from the target object
    to the root objects (from referents to referrers). This makes it easier to visualise the
    graph when printed.
    """
    id_sequence = max(node.id for node in referrer_graph.graph_nodes) + 1

    id_graph = nx.DiGraph()

    # First pass: add all nodes to the ID graph to the new graph
    for node in referrer_graph.graph_nodes:
        id_graph.add_node(node.id, data=node, original_node_id=node.id)

    # Second pass: add edges to the ID graph, breaking cycles
    for node in referrer_graph.graph_nodes:
        # If this node has more than one referent, create a copy of the node for all but the
        # first referent, so that the graph is a tree. Mark the copies as cycle members.
        if node.referent_ids:
            id_graph.add_edge(node.id, node.referent_ids[0])
            for referrer_id in node.referent_ids[1:]:
                new_node = dataclasses.replace(node, id=id_sequence)
                id_graph.add_node(
                    id_sequence, data=new_node, is_cycle_member=True, original_node_id=node.id
                )
                id_graph.add_edge(id_sequence, referrer_id)
                id_sequence += 1

    # Now, create the printable graph, reversing the edges
    printable_graph = nx.DiGraph()
    id_to_printable_node: Dict[int, PrintableReferrerNode] = {}
    for node_id in id_graph.nodes():
        node_data = id_graph.nodes[node_id]["data"]
        is_cycle_member = id_graph.nodes[node_id].get("is_cycle_member", False)
        original_node_id = id_graph.nodes[node_id].get("original_node_id")
        is_root = original_node_id in referrer_graph.root_ids
        is_target = original_node_id in referrer_graph.target_ids
        printable_node = PrintableReferrerNode(
            unique_id=node_data.id,
            name=node_data.name,
            object_id=node_data.object_id,
            is_cycle_member=is_cycle_member,
            is_root=is_root,
            is_target=is_target,
        )
        printable_graph.add_node(printable_node)
        id_to_printable_node[node_id] = printable_node
    for u, v in id_graph.edges():
        printable_graph.add_edge(id_to_printable_node[u], id_to_printable_node[v])
    printable_graph = printable_graph.reverse(copy=False)

    return printable_graph


def get_object_type_budgets(
    object_type_counts: Mapping[type, int], total_budget: int
) -> Mapping[type, int]:
    """
    Calculate the budget for the most common object types.

    Each object type will get a budget of at least one. The remaining budget
    (based on `total_budget`) is distributed proportionally to the
    number of occurrences of each type.

    For example, if `total_budget` is set to 10 and type1 occurs 20 times and type2 occurs 4
    times, then the budget for type1 will be 8 and the budget
    for type2 will be 2.

    If there are as many types as `max_object_details`, then the budget for each
    type will be one.
    """
    num_types = len(object_type_counts)
    if num_types == 0:
        return {}

    if num_types >= total_budget:
        return dict.fromkeys(object_type_counts, 1)

    budget = dict.fromkeys(object_type_counts, 1)
    remaining_budget = total_budget - num_types

    total_count = sum(object_type_counts.values())

    for obj_type, count in object_type_counts.items():
        proportional_budget = round((count / total_count) * remaining_budget)
        budget[obj_type] += proportional_budget

    return budget
