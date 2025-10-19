from dataclasses import field
from pathlib import Path
from typing import AbstractSet, Any, Callable, Optional

from pydantic.dataclasses import dataclass


class InvalidOptionsError(Exception):
    """
    Raised when an option is invalid.
    """


@dataclass(frozen=True)
class Options:
    """
    Options for controlling the behavior of memalot. These are passed to the API as keyword
    arguments. For example::

        memalot.start(max_object_lifetime=60.0, force_terminal=True)

    In this case, the `force_terminal` argument matches a property in this class.
    """

    included_type_names: AbstractSet[str] = field(default_factory=set)
    """
    The types of objects to include in the report. By default all types are checked,
    but this can be limited to a subset of types.

    Inclusion is based on substring matching of the fully-qualified type name (the name of
    the type and its module). For example, if `included_type_names` is set to `{"numpy"}`,
    *all* NumPy types will be included in the report.
    """

    excluded_type_names: AbstractSet[str] = field(default_factory=set)
    """
    The types of objects to exclude from the report. By default no types are excluded.

    Exclusion is based on substring matching of the fully-qualified type name (the name of
    the type and its module). For example, if `excluded_type_names` is set to `{"numpy"}`,
    *all* NumPy types will be excluded from the report.
    """

    max_types_in_leak_summary: int = 500
    """
    The maximum number of types to include in the leak summary.
    """

    compute_size_in_leak_summary: bool = False
    """
    Computes the (shallow) size of all objects in the leak summary.

    Note: the shallow size of an object may not be particularly meaningful, since most
    objects refer to other objects, and often don't contain much data themselves.
    """

    max_untracked_search_depth: int = 3
    """
    The maximum search depth when looking for leaked objects that are not tracked by the
    garbage collector. Untracked objects include, for example, mutable objects and collections
    containing only immutable objects in CPython

    This defaults to 3, which is enough to find most untracked objects. However, this may not
    be sufficient to find some untracked objects, like nested tuples. Increase this if you
    have nested collections of immutable objects (like tuples). However, note that increasing
    this may impact speed.
    """

    check_referrers: bool = True
    """
    Whether to check for referrers of leaked objects. Defaults to `True`.

    This option may cause a significant slow-down (but provides useful information).
    Try setting this to `False` if Memalot is taking a long time to generate object details.
    Then, when you have an idea of what types of objects are leaking, you can generate reports
    with `check_referrers=True` and `included_type_names` set to the types of objects that you
    think may be leaking.
    """

    max_object_details: int = 30
    """
    The maximum number of objects for which to print details. Defaults to `30`.

    We try to check at least one object for each object type, within this limit. If the
    number of types exceeds this limit, then we check only the most common types. If the
    number of types is less than this limit, then we will check more objects for more
    common types.
    """

    referrers_max_depth: int | None = 50
    """
    The maximum depth to search for referrers. The default is 50. Specify `None` to search to
    unlimited depth (but be careful with this: it may take a long time).
    """

    referrers_search_timeout: float | None = 60.0 * 5
    """
    The maximum time to spend searching for referrers for an individual object. If this time
    is exceeded, a partial graph is displayed and the referrer graph will contain a node
    containing the text "Timeout of N seconds exceeded". Note that this timeout is approximate,
    and may not be effective if the search is blocked by a long-running operation. The default
    is 5 minutes. Setting this to `None` will disable the timeout.
    """

    single_object_referrer_limit: int | None = 100
    """
    The maximum number of referrers to include in the graph for an individual object instance.
    If the limit is exceeded, the referrer graph will contain a node containing the text
    "Referrer limit of N exceeded". Note that this limit is approximate and does not apply to all
    referrer types. Specifically, it only applies to object references. Additionally,
    this limit does not apply to immortal objects.
    """

    referrers_module_prefixes: Optional[AbstractSet[str]] = None
    """
    The prefixes of the modules to search for module-level variables when looking for referrers.
    If this is not specified, the top-level package of the calling code is used.
    """

    referrers_max_untracked_search_depth: int = 30
    """
    The maximum depth to search for referrers of untracked objects. This is the depth that
    referents will be searched from the roots (locals and globals). The default is 30. If you
    are missing referrers of untracked objects, you can increase this value.
    """

    save_reports: bool = True
    """
    Whether to save reports to disk. This is useful for inspecting them later.

    Reports are written to the `report_directory`, or the default directory if
    this is not specified.
    """

    report_directory: Path | None = None
    """
    The directory to write the report data to. Individual report data is written to
    a subdirectory of this directory.

    If this is `None` (the default), the default directory will be used. This is the
    `.memalot/reports` directory in the user's home directory.

    To turn off saving of reports entirely, use the `save_reports` option.
    """

    str_func: Callable[[Any, int], str] | None = None
    """
    A function for outputting the string representation of an object. The first argument
    is the object and the second argument is the length to truncate the string to,
    as specified by `str_max_length`.

    If this is not supplied the object's `__str__` is used.
    """

    str_max_length: int = 100
    """
    The maximum length of object string representations, as passed to `str_func`.
    """

    force_terminal: bool | None = None
    """
    Forces the use of terminal control codes, which enable colors and other formatting.
    Defaults to `False`, as this is normally detected automatically.

    Set this to `True` if you are missing colors or other formatting in the output, as
    sometimes (like when running in an IDE) the terminal is not detected correctly.

    This must be set to `False` if `output_func` is set and `tee_console` is `False`.
    """

    output_func: Callable[[str], None] | None = None
    """
    A function that writes reports. If this is not provided reports are
    printed to the console.

    This option can be used to, for example, write reports to a log file.

    If this option is specified then output is *not* written to the console, unless
    `tee_console` is set to `True`.
    """

    tee_console: bool = False
    """
    If this is set to `True`, output is written to the console as well as to the function
    specified by `output_func`. If `output_func` is not specified (the default) then this
    option has no effect.
    """

    color: bool = True
    """
    Specifies whether colors should be printed to the console.

    Note: in certain consoles (like when running in an IDE), colors are not printed by
    default. Try setting `force_terminal` to `True` if this happens.
    """

    def __post_init__(self) -> None:
        if self.output_func is not None and not self.tee_console and self.force_terminal:
            raise InvalidOptionsError(
                "If output_func is specified and tee_console is False, then force_terminal "
                "must be False."
            )
