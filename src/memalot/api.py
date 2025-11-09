"""
The public api of Memalot. Functions in this module are imported into the main
`__init__.py` file, along with the interfaces defined in `interface.py`.
"""

import functools
from pathlib import Path
from typing import AbstractSet, Any, Callable, Optional, ParamSpec, TypeVar, overload

from memalot.interface import LeakMonitor, Stoppable
from memalot.monitors import FilteringObjectGetter, LeakMonitorImpl, LeakMonitorThread
from memalot.objects import gc_and_get_objects
from memalot.options import Options
from memalot.output import RichOutput, get_output_writer
from memalot.reports import get_report_writer
from memalot.snapshots import MemalotSnapshotManager
from memalot.themes import FUNCTION_NAME
from memalot.utils import pluralize


def start_leak_monitoring(
    max_object_lifetime: float,
    warmup_time: float | None = None,
    included_type_names: AbstractSet[str] = frozenset(),
    excluded_type_names: AbstractSet[str] = frozenset(),
    max_types_in_leak_summary: int = 500,
    compute_size_in_leak_summary: bool = False,
    max_untracked_search_depth: int = 3,
    check_referrers: bool = True,
    max_object_details: int = 30,
    referrers_max_depth: int | None = 50,
    referrers_search_timeout: float | None = 60.0 * 5,
    single_object_referrer_limit: int | None = 100,
    referrers_module_prefixes: Optional[AbstractSet[str]] = None,
    referrers_max_untracked_search_depth: int = 30,
    save_reports: bool = True,
    report_directory: Path | None = None,
    str_func: Callable[[Any, int], str] | None = None,
    str_max_length: int = 100,
    force_terminal: bool | None = None,
    output_func: Callable[[str], None] | None = None,
    tee_console: bool = False,
    color: bool = True,
) -> Stoppable:
    """
    Starts monitoring for memory leaks. After the warmup period of `warmup_time` seconds,
    objects surviving for more than `max_object_lifetime` seconds will be identified as
    potential leaks.

    A memory leak report is printed to the console every `max_object_lifetime` seconds.

    The `warmup_time` parameter can be changed to control how long Memalot will wait before
    starting to look for leaks. For example, if the program being monitored creates a lot
    of data on startup, this can be used to ignore that data. This defaults to
    `max_object_lifetime`.

    :param max_object_lifetime: The maximum time in seconds that an object can live before
        it is considered a potential leak.

    :param warmup_time: The number of seconds to wait before starting to look for leaks.
        This defaults to `max_object_lifetime`.

    :param included_type_names: The types of objects to include in the report. By default,
        all types are checked, but this can be limited to a subset of types. Inclusion is based
        on substring matching of the fully-qualified type name (the name of the type and its
        module). For example, if `included_type_names` is set to `{"numpy"}`, *all* NumPy types
        will be included in the report.

    :param excluded_type_names: The types of objects to exclude from the report.
        By default, no types are excluded. Exclusion is based on substring matching of the
        fully-qualified type name (the name of the type and its module). For example,
        if `excluded_type_names` is set to `{"numpy"}`, *all* NumPy types will be excluded from
        the report.

    :param max_types_in_leak_summary: The maximum number of types to include in the leak summary.

    :param compute_size_in_leak_summary: Computes the (shallow) size of all objects in the
        leak summary. Note: the shallow size of an object may not be particularly meaningful,
        since most objects refer to other objects, and often don't contain much data themselves.

    :param max_untracked_search_depth: The maximum search depth when looking for leaked objects
        that are not tracked by the garbage collector. Untracked objects include, for example,
        mutable objects and collections containing only immutable objects in CPython.
        This defaults to 3, which is enough to find most untracked objects. However, this may not
        be sufficient to find some untracked objects, like nested tuples. Increase this if you
        have nested collections of immutable objects (like tuples). However, note that increasing
        this may impact speed.

    :param check_referrers: Whether to check for referrers of leaked objects. Defaults to `True`.
        Note: this option may cause significant slow-down (but provides useful information).

    :param max_object_details: The maximum number of objects for which to print details.
        Defaults to `30`. We try to check the same number of objects for each type, within this
        limit. For example, if there are 10 types of objects, and `max_referrers` is 30, then
        we check 3 objects for each type.

    :param referrers_max_depth: The maximum depth to search for referrers. The default is 50.
        Specify `None` to search to unlimited depth (but be careful with this: it may take a
        long time).

    :param referrers_search_timeout: The maximum time to spend searching for referrers for an
        individual object. If this time is exceeded, a partial graph is displayed and the
        referrer graph will contain a node containing the text "Timeout of N seconds exceeded".
        Note that this timeout is approximate, and may not be effective if the search is blocked
        by a long-running operation. The default is 5 minutes. Setting this to `None` will
        disable the timeout.

    :param single_object_referrer_limit: The maximum number of referrers to include in the graph
        for an individual object instance. If the limit is exceeded, the referrer graph will
        contain a node containing the text "Referrer limit of N exceeded". Note that this limit
        is approximate and does not apply to all referrer types. Specifically, it only applies
        to object references. Additionally, this limit does not apply to immortal objects.

    :param referrers_module_prefixes: The prefixes of the modules to search for module-level
        variables when looking for referrers. If this is not specified, the top-level package of
        the calling code is used.

    :param referrers_max_untracked_search_depth: The maximum depth to search for referrers of
        untracked objects. This is the depth that referents will be searched from the roots (
        locals and globals). The default is 30. If you are missing referrers of untracked
        objects, you can increase this value.

    :param save_reports: Whether to save reports to disk. This is useful for inspecting them later.
        Reports are written to the `report_directory`, or the default directory if this is not
        specified.

    :param report_directory: The directory to write the report data to. Individual report data
        is written to a subdirectory of this directory.
        If this is `None` (the default), the default directory will be used. This is the
        `.memalot/reports` directory in the user's home directory.
        To turn off saving of reports entirely, use the `save_reports` option.

    :param str_func: A function for outputting the string representation of an object.
        The first argument is the object, and the second argument is the length to truncate the
        string to, as specified by `str_max_length`. If this is not supplied, the object's
        `__str__` is used.

    :param str_max_length: The maximum length of object string representations, as passed to
    `str_func`.

    :param force_terminal: Forces the use of terminal control codes, which enable colors and
        other formatting. Defaults to `False`, as this is normally detected automatically.
        Set this to `True` if you are missing colors or other formatting in the output, as
        sometimes (like when running in an IDE) the terminal is not detected correctly.
        This must be set to `False` if `output_func` is set and `tee_console` is `False`.

    :param output_func: A function that writes reports. If this is not provided,
        reports are printed to the console. This option can be used to, for example,
        write reports to a log file.
        If this option is specified, then output is *not* written to the console, unless
        `tee_console` is set to `True`.

    :param tee_console: If this is set to `True`, output is written to the console as well as
        to the function specified by `output_func`. If `output_func` is not specified (the
        default), then this option has no effect.

    :param color: Specifies whether colors should be printed to the console.
        Note: in certain consoles (like when running in an IDE), colors are not printed by
        default. Try setting `force_terminal` to `True` if this happens.

    :return: A stoppable object that can be used to stop the monitoring by calling the
        `stop()` method.
    """
    if warmup_time is None:
        warmup_time = max_object_lifetime
    options = Options(
        included_type_names=included_type_names,
        excluded_type_names=excluded_type_names,
        max_types_in_leak_summary=max_types_in_leak_summary,
        compute_size_in_leak_summary=compute_size_in_leak_summary,
        max_untracked_search_depth=max_untracked_search_depth,
        check_referrers=check_referrers,
        max_object_details=max_object_details,
        referrers_max_depth=referrers_max_depth,
        referrers_search_timeout=referrers_search_timeout,
        single_object_referrer_limit=single_object_referrer_limit,
        referrers_module_prefixes=referrers_module_prefixes,
        referrers_max_untracked_search_depth=referrers_max_untracked_search_depth,
        save_reports=save_reports,
        report_directory=report_directory,
        str_func=str_func,
        str_max_length=str_max_length,
        force_terminal=force_terminal,
        output_func=output_func,
        tee_console=tee_console,
        color=color,
    )
    writer = get_output_writer(options=options)
    report_writer = get_report_writer(options=options)
    all_objects_manager = MemalotSnapshotManager(
        report_id=report_writer.report_id,
    )
    new_objects_manager = MemalotSnapshotManager(
        report_id=report_writer.report_id,
    )
    object_getter = FilteringObjectGetter(
        get_objects_func=gc_and_get_objects,
        options=options,
        snapshot_managers=[all_objects_manager, new_objects_manager],
    )
    leak_monitor_thread = LeakMonitorThread(
        max_object_lifetime=max_object_lifetime,
        warmup_time=warmup_time,
        writer=writer,
        report_writer=report_writer,
        options=options,
        all_objects_manager=all_objects_manager,
        new_objects_manager=new_objects_manager,
        object_getter=object_getter,
    )
    leak_monitor_thread.start()
    writer.write(
        RichOutput(
            f"Memalot is performing time-based leak monitoring. After a warmup period of"
            f" {warmup_time} seconds, objects surviving for more than {max_object_lifetime} "
            f"seconds will be identified as potential leaks."
        )
    )
    return leak_monitor_thread


P = ParamSpec("P")
R = TypeVar("R")


# Overload for when called with parentheses
@overload
def leak_monitor(
    func: None = None,
    warmup_calls: int = 1,
    max_object_age_calls: int = 1,
    included_type_names: AbstractSet[str] = frozenset(),
    excluded_type_names: AbstractSet[str] = frozenset(),
    max_types_in_leak_summary: int = 500,
    compute_size_in_leak_summary: bool = False,
    max_untracked_search_depth: int = 3,
    check_referrers: bool = True,
    max_object_details: int = 30,
    referrers_max_depth: int | None = 50,
    referrers_search_timeout: float | None = 60.0 * 5,
    single_object_referrer_limit: int | None = 100,
    referrers_module_prefixes: Optional[AbstractSet[str]] = None,
    referrers_max_untracked_search_depth: int = 30,
    save_reports: bool = True,
    report_directory: Path | None = None,
    str_func: Callable[[Any, int], str] | None = None,
    str_max_length: int = 100,
    force_terminal: bool | None = None,
    output_func: Callable[[str], None] | None = None,
    tee_console: bool = False,
    color: bool = True,
) -> Callable[[Callable[P, R]], Callable[P, R]]: ...


# Overload for when called without parentheses
@overload
def leak_monitor(
    func: Callable[P, R] | None = None,
    warmup_calls: int = 1,
    max_object_age_calls: int = 1,
    included_type_names: AbstractSet[str] = frozenset(),
    excluded_type_names: AbstractSet[str] = frozenset(),
    max_types_in_leak_summary: int = 500,
    compute_size_in_leak_summary: bool = False,
    max_untracked_search_depth: int = 3,
    check_referrers: bool = True,
    max_object_details: int = 30,
    referrers_max_depth: int | None = 50,
    referrers_search_timeout: float | None = 60.0 * 5,
    single_object_referrer_limit: int | None = 100,
    referrers_module_prefixes: Optional[AbstractSet[str]] = None,
    referrers_max_untracked_search_depth: int = 30,
    save_reports: bool = True,
    report_directory: Path | None = None,
    str_func: Callable[[Any, int], str] | None = None,
    str_max_length: int = 100,
    force_terminal: bool | None = None,
    output_func: Callable[[str], None] | None = None,
    tee_console: bool = False,
    color: bool = True,
) -> Callable[P, R]: ...


def leak_monitor(
    func: Callable[P, R] | None = None,
    warmup_calls: int = 1,
    max_object_age_calls: int = 1,
    included_type_names: AbstractSet[str] = frozenset(),
    excluded_type_names: AbstractSet[str] = frozenset(),
    max_types_in_leak_summary: int = 500,
    compute_size_in_leak_summary: bool = False,
    max_untracked_search_depth: int = 3,
    check_referrers: bool = True,
    max_object_details: int = 30,
    referrers_max_depth: int | None = 50,
    referrers_search_timeout: float | None = 60.0 * 5,
    single_object_referrer_limit: int | None = 100,
    referrers_module_prefixes: Optional[AbstractSet[str]] = None,
    referrers_max_untracked_search_depth: int = 30,
    save_reports: bool = True,
    report_directory: Path | None = None,
    str_func: Callable[[Any, int], str] | None = None,
    str_max_length: int = 100,
    force_terminal: bool | None = None,
    output_func: Callable[[str], None] | None = None,
    tee_console: bool = False,
    color: bool = True,
) -> Callable[P, R] | Callable[[Callable[P, R]], Callable[P, R]]:
    """
    Decorator to monitor for memory leaks. After `warmup_calls` warmup calls, object that are
    created while the decorated function is being called and are still alive after
    `max_object_age_calls` calls will be identified as a potential leak.

    A memory leak report is printed to the console every `max_object_age_calls` calls to the
    decorated function.

    By default, `warmup_calls` and `max_object_age_calls` are both set to `1`, so after the first
    call, leaks will be identified on every call.

    The `warmup_calls` parameter can be changed if data is created on some number of initial calls
    to the decorated function, but not created after that.

    The `max_object_age_calls` parameter can be changed if data created by the decorated function
    is permitted to live for a certain number of calls. Only objects that have lived for
    `max_object_age_calls` calls will be reported as potential leaks. For example, if
    `max_object_age_calls` is set to `2`, objects must live for two calls to be considered as
    potential leaks.

    Note: this decorator will not work well if other threads are creating objects outside the
    function while it is being called. Consider using the `start_leak_monitoring` function
    instead if this is the case.

    :param func: The function to decorate

    :param warmup_calls: The number of warmup calls. No leaks will be detected until this
        many calls have been made to the decorated function.

    :param max_object_age_calls: The number of calls to the decorated function that an object
        must survive for to be considered a potential leak.

    :param included_type_names: The types of objects to include in the report. By default,
        all types are checked, but this can be limited to a subset of types. Inclusion is based
        on substring matching of the fully-qualified type name (the name of the type and its
        module). For example, if `included_type_names` is set to `{"numpy"}`, *all* NumPy types
        will be included in the report.

    :param excluded_type_names: The types of objects to exclude from the report.
        By default, no types are excluded. Exclusion is based on substring matching of the
        fully-qualified type name (the name of the type and its module). For example,
        if `excluded_type_names` is set to `{"numpy"}`, *all* NumPy types will be excluded from
        the report.

    :param max_types_in_leak_summary: The maximum number of types to include in the leak summary.

    :param compute_size_in_leak_summary: Computes the (shallow) size of all objects in the
        leak summary. Note: the shallow size of an object may not be particularly meaningful,
        since most objects refer to other objects, and often don't contain much data themselves.

    :param max_untracked_search_depth: The maximum search depth when looking for leaked objects
        that are not tracked by the garbage collector. Untracked objects include, for example,
        mutable objects and collections containing only immutable objects in CPython.
        This defaults to 3, which is enough to find most untracked objects. However, this may not
        be sufficient to find some untracked objects, like nested tuples. Increase this if you
        have nested collections of immutable objects (like tuples). However, note that increasing
        this may impact speed.

    :param check_referrers: Whether to check for referrers of leaked objects. Defaults to `True`.
        Note: this option may cause significant slow-down (but provides useful information).

    :param max_object_details: The maximum number of objects for which to print details.
        Defaults to `30`. We try to check the same number of objects for each type, within this
        limit. For example, if there are 10 types of objects, and `max_referrers` is 30, then
        we check 3 objects for each type.

    :param referrers_max_depth: The maximum depth to search for referrers. The default is 50.
        Specify `None` to search to unlimited depth (but be careful with this: it may take a
        long time).

    :param referrers_search_timeout: The maximum time to spend searching for referrers for an
        individual object. If this time is exceeded, a partial graph is displayed and the
        referrer graph will contain a node containing the text "Timeout of N seconds exceeded".
        Note that this timeout is approximate, and may not be effective if the search is blocked
        by a long-running operation. The default is 5 minutes. Setting this to `None` will
        disable the timeout.

    :param single_object_referrer_limit: The maximum number of referrers to include in the graph
        for an individual object instance. If the limit is exceeded, the referrer graph will
        contain a node containing the text "Referrer limit of N exceeded". Note that this limit
        is approximate and does not apply to all referrer types. Specifically, it only applies
        to object references. Additionally, this limit does not apply to immortal objects.

    :param referrers_module_prefixes: The prefixes of the modules to search for module-level
        variables when looking for referrers. If this is not specified, the top-level package of
        the calling code is used.

    :param referrers_max_untracked_search_depth: The maximum depth to search for referrers of
        untracked objects. This is the depth that referents will be searched from the roots (
        locals and globals). The default is 30. If you are missing referrers of untracked
        objects, you can increase this value.

    :param save_reports: Whether to save reports to disk. This is useful for inspecting them later.
        Reports are written to the `report_directory`, or the default directory if this is not
        specified.

    :param report_directory: The directory to write the report data to. Individual report data
        is written to a subdirectory of this directory.
        If this is `None` (the default), the default directory will be used. This is the
        `.memalot/reports` directory in the user's home directory.
        To turn off saving of reports entirely, use the `save_reports` option.

    :param str_func: A function for outputting the string representation of an object.
        The first argument is the object, and the second argument is the length to truncate the
        string to, as specified by `str_max_length`. If this is not supplied, the object's
        `__str__` is used.

    :param str_max_length: The maximum length of object string representations, as passed to
    `str_func`.

    :param force_terminal: Forces the use of terminal control codes, which enable colors and
        other formatting. Defaults to `False`, as this is normally detected automatically.
        Set this to `True` if you are missing colors or other formatting in the output, as
        sometimes (like when running in an IDE) the terminal is not detected correctly.
        This must be set to `False` if `output_func` is set and `tee_console` is `False`.

    :param output_func: A function that writes reports. If this is not provided,
        reports are printed to the console. This option can be used to, for example,
        write reports to a log file.
        If this option is specified, then output is *not* written to the console, unless
        `tee_console` is set to `True`.

    :param tee_console: If this is set to `True`, output is written to the console as well as
        to the function specified by `output_func`. If `output_func` is not specified (the
        default), then this option has no effect.

    :param color: Specifies whether colors should be printed to the console.
        Note: in certain consoles (like when running in an IDE), colors are not printed by
        default. Try setting `force_terminal` to `True` if this happens.
    """

    def decorator_func(target_func: Callable[P, R]) -> Callable[P, R]:
        decorated_function_name = target_func.__name__
        monitor = create_leak_monitor(
            warmup_calls=warmup_calls,
            max_object_age_calls=max_object_age_calls,
            included_type_names=included_type_names,
            excluded_type_names=excluded_type_names,
            max_types_in_leak_summary=max_types_in_leak_summary,
            compute_size_in_leak_summary=compute_size_in_leak_summary,
            max_untracked_search_depth=max_untracked_search_depth,
            check_referrers=check_referrers,
            max_object_details=max_object_details,
            referrers_max_depth=referrers_max_depth,
            referrers_search_timeout=referrers_search_timeout,
            single_object_referrer_limit=single_object_referrer_limit,
            referrers_module_prefixes=referrers_module_prefixes,
            referrers_max_untracked_search_depth=referrers_max_untracked_search_depth,
            save_reports=save_reports,
            report_directory=report_directory,
            str_func=str_func,
            str_max_length=str_max_length,
            force_terminal=force_terminal,
            output_func=output_func,
            tee_console=tee_console,
            color=color,
            function_name=decorated_function_name,
        )

        @functools.wraps(target_func)
        def memalot_decorator_inner_wrapper(
            *memalot_decorator_inner_args: P.args, **memalot_decorator_inner_kwargs: P.kwargs
        ) -> R:
            with monitor:
                return target_func(*memalot_decorator_inner_args, **memalot_decorator_inner_kwargs)

        return memalot_decorator_inner_wrapper

    if func is None:
        # Called with parentheses: @leak_monitor()
        return decorator_func
    else:
        # Called without parentheses: @leak_monitor
        return decorator_func(func)


def create_leak_monitor(
    warmup_calls: int = 1,
    max_object_age_calls: int = 1,
    included_type_names: AbstractSet[str] = frozenset(),
    excluded_type_names: AbstractSet[str] = frozenset(),
    max_types_in_leak_summary: int = 500,
    compute_size_in_leak_summary: bool = False,
    max_untracked_search_depth: int = 3,
    check_referrers: bool = True,
    max_object_details: int = 30,
    referrers_max_depth: int | None = 50,
    referrers_search_timeout: float | None = 60.0 * 5,
    single_object_referrer_limit: int | None = 100,
    referrers_module_prefixes: Optional[AbstractSet[str]] = None,
    referrers_max_untracked_search_depth: int = 30,
    save_reports: bool = True,
    report_directory: Path | None = None,
    str_func: Callable[[Any, int], str] | None = None,
    str_max_length: int = 100,
    force_terminal: bool | None = None,
    output_func: Callable[[str], None] | None = None,
    tee_console: bool = False,
    color: bool = True,
    function_name: str | None = None,
) -> LeakMonitor:
    """
    Creates a monitor for memory leaks. This can be used as a context manager as follows::

      monitor = create_leak_monitor()
      with monitor:
        # Code that leaks memory here

    After `warmup_calls` warmup calls, any object that is created within the context manager and
    is still alive after `max_object_age_calls` calls will be identified as a potential leak.

    A memory leak report is printed to the console every `max_object_age_calls` calls to the
    decorated function.

    By default, `warmup_calls` and `max_object_age_calls` are both set to `1`, so after the first
    call, leaks will be identified on every call.

    The `warmup_calls` parameter can be changed if data is created on some number of initial calls
    to the decorated function, but not created after that.

    The `max_object_age_calls` parameter can be changed if data created by the decorated function
    is permitted to live for a certain number of calls. Only objects that have lived for
    `max_object_age_calls` calls will be reported as potential leaks. For example, if
    `max_object_age_calls` is set to `2`, objects must live for two calls to be considered as
    potential leaks.

    Note: this context manager will not work well if other threads are creating objects
    outside the scope of the context manager while it is being called. Consider using the
    `start_leak_monitoring` function instead if this is the case.

    :param warmup_calls: The number of warmup calls. No leaks will be detected until this
        many calls have been made to the decorated function.

    :param max_object_age_calls: The number of calls to the decorated function that an object
        must survive for to be considered a potential leak.

    :param included_type_names: The types of objects to include in the report. By default,
        all types are checked, but this can be limited to a subset of types. Inclusion is based
        on substring matching of the fully-qualified type name (the name of the type and its
        module). For example, if `included_type_names` is set to `{"numpy"}`, *all* NumPy types
        will be included in the report.

    :param excluded_type_names: The types of objects to exclude from the report.
        By default, no types are excluded. Exclusion is based on substring matching of the
        fully-qualified type name (the name of the type and its module). For example,
        if `excluded_type_names` is set to `{"numpy"}`, *all* NumPy types will be excluded from
        the report.

    :param max_types_in_leak_summary: The maximum number of types to include in the leak summary.

    :param compute_size_in_leak_summary: Computes the (shallow) size of all objects in the
        leak summary. Note: the shallow size of an object may not be particularly meaningful,
        since most objects refer to other objects, and often don't contain much data themselves.

    :param max_untracked_search_depth: The maximum search depth when looking for leaked objects
        that are not tracked by the garbage collector. Untracked objects include, for example,
        mutable objects and collections containing only immutable objects in CPython.
        This defaults to 3, which is enough to find most untracked objects. However, this may not
        be sufficient to find some untracked objects, like nested tuples. Increase this if you
        have nested collections of immutable objects (like tuples). However, note that increasing
        this may impact speed.

    :param check_referrers: Whether to check for referrers of leaked objects. Defaults to `True`.
        Note: this option may cause significant slow-down (but provides useful information).

    :param max_object_details: The maximum number of objects for which to print details.
        Defaults to `30`. We try to check the same number of objects for each type, within this
        limit. For example, if there are 10 types of objects, and `max_referrers` is 30, then
        we check 3 objects for each type.

    :param referrers_max_depth: The maximum depth to search for referrers. The default is 50.
        Specify `None` to search to unlimited depth (but be careful with this: it may take a
        long time).

    :param referrers_search_timeout: The maximum time to spend searching for referrers for an
        individual object. If this time is exceeded, a partial graph is displayed and the
        referrer graph will contain a node containing the text "Timeout of N seconds exceeded".
        Note that this timeout is approximate, and may not be effective if the search is blocked
        by a long-running operation. The default is 5 minutes. Setting this to `None` will
        disable the timeout.

    :param single_object_referrer_limit: The maximum number of referrers to include in the graph
        for an individual object instance. If the limit is exceeded, the referrer graph will
        contain a node containing the text "Referrer limit of N exceeded". Note that this limit
        is approximate and does not apply to all referrer types. Specifically, it only applies
        to object references. Additionally, this limit does not apply to immortal objects.

    :param referrers_module_prefixes: The prefixes of the modules to search for module-level
        variables when looking for referrers. If this is not specified, the top-level package of
        the calling code is used.

    :param referrers_max_untracked_search_depth: The maximum depth to search for referrers of
        untracked objects. This is the depth that referents will be searched from the roots (
        locals and globals). The default is 30. If you are missing referrers of untracked
        objects, you can increase this value.

    :param save_reports: Whether to save reports to disk. This is useful for inspecting them later.
        Reports are written to the `report_directory`, or the default directory if this is not
        specified.

    :param report_directory: The directory to write the report data to. Individual report data
        is written to a subdirectory of this directory.
        If this is `None` (the default), the default directory will be used. This is the
        `.memalot/reports` directory in the user's home directory.
        To turn off saving of reports entirely, use the `save_reports` option.

    :param str_func: A function for outputting the string representation of an object.
        The first argument is the object, and the second argument is the length to truncate the
        string to, as specified by `str_max_length`. If this is not supplied, the object's
        `__str__` is used.

    :param str_max_length: The maximum length of object string representations, as passed to
    `str_func`.

    :param force_terminal: Forces the use of terminal control codes, which enable colors and
        other formatting. Defaults to `False`, as this is normally detected automatically.
        Set this to `True` if you are missing colors or other formatting in the output, as
        sometimes (like when running in an IDE) the terminal is not detected correctly.
        This must be set to `False` if `output_func` is set and `tee_console` is `False`.

    :param output_func: A function that writes reports. If this is not provided,
        reports are printed to the console. This option can be used to, for example,
        write reports to a log file.
        If this option is specified, then output is *not* written to the console, unless
        `tee_console` is set to `True`.

    :param tee_console: If this is set to `True`, output is written to the console as well as
        to the function specified by `output_func`. If `output_func` is not specified (the
        default), then this option has no effect.

    :param color: Specifies whether colors should be printed to the console.
        Note: in certain consoles (like when running in an IDE), colors are not printed by
        default. Try setting `force_terminal` to `True` if this happens.

    :param function_name: Optionally, the name of a function that is being decorated
        by the leak monitor, if a decorator is being used. If this is None then we assume that
        the leak monitor is being used as a context manager, not a decorator.

    """
    options = Options(
        included_type_names=included_type_names,
        excluded_type_names=excluded_type_names,
        max_types_in_leak_summary=max_types_in_leak_summary,
        compute_size_in_leak_summary=compute_size_in_leak_summary,
        max_untracked_search_depth=max_untracked_search_depth,
        check_referrers=check_referrers,
        max_object_details=max_object_details,
        referrers_max_depth=referrers_max_depth,
        referrers_search_timeout=referrers_search_timeout,
        single_object_referrer_limit=single_object_referrer_limit,
        referrers_module_prefixes=referrers_module_prefixes,
        referrers_max_untracked_search_depth=referrers_max_untracked_search_depth,
        save_reports=save_reports,
        report_directory=report_directory,
        str_func=str_func,
        str_max_length=str_max_length,
        force_terminal=force_terminal,
        output_func=output_func,
        tee_console=tee_console,
        color=color,
    )
    writer = get_output_writer(options=options)
    report_writer = get_report_writer(options=options)
    snapshot_manager = MemalotSnapshotManager(
        report_id=report_writer.report_id,
    )
    object_getter = FilteringObjectGetter(
        get_objects_func=gc_and_get_objects,
        options=options,
        snapshot_managers=[snapshot_manager],
    )
    monitor = LeakMonitorImpl(
        writer=writer,
        report_writer=report_writer,
        warmup_calls=warmup_calls,
        calls_per_report=max_object_age_calls,
        options=options,
        snapshot_manager=snapshot_manager,
        object_getter=object_getter,
        function_name=function_name,
    )
    if function_name is not None:
        writer.write(
            RichOutput(
                f"Memalot is performing leak monitoring for the "
                f"[{FUNCTION_NAME}]{function_name}[/{FUNCTION_NAME}] function. "
                f"After {warmup_calls} warmup {pluralize('call', max_object_age_calls)}, "
                f"objects that are created while this function is being called and are still alive "
                f"after {max_object_age_calls} {pluralize('call', max_object_age_calls)} will "
                f"be identified as potential leaks."
            )
        )
    else:
        writer.write(
            RichOutput(
                f"Memalot is performing leak monitoring using a context manager. "
                f"After {warmup_calls} warmup {pluralize('call', max_object_age_calls)}, objects "
                f"that are created while the context manager is being called and are still "
                f"alive after {max_object_age_calls} {pluralize('call', max_object_age_calls)} "
                f"will be identified as potential leaks."
            )
        )

    return monitor
