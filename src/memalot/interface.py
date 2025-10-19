"""
Public interfaces used in memalot. These are imported into the main `__init__.py` file.
"""

from abc import ABC, abstractmethod
from typing import Any


class LeakMonitor(ABC):
    """
    A class that can be used as a context manager to monitor for memory leaks. The *second* time
    that the enclosed code is called, a summary of potential leaks will be printed to the console.
    """

    @abstractmethod
    def __enter__(self) -> None:  # pragma: no cover
        """
        Starts leak monitoring.
        """
        pass

    @abstractmethod
    def __exit__(
        self, exc_type: type[BaseException] | None, exc_value: BaseException | None, traceback: Any
    ) -> None:  # pragma: no cover
        """
        Ends leak monitoring and prints a summary of potential leaks.
        """
        pass

    def __call__(self) -> "LeakMonitor":  # pragma: no cover
        return self


class Stoppable(ABC):
    """
    An interface for objects that can be stopped, such as background monitoring threads.
    """

    @abstractmethod
    def stop(self) -> None:  # pragma: no cover
        """
        Signals the object to stop at the next safe opportunity.
        """
        pass

    @abstractmethod
    def join(self, timeout: float | None = None) -> None:  # pragma: no cover
        """
        Waits for the object to finish stopping.

        :param timeout: Maximum time to wait in seconds. If None, waits indefinitely.
        """
        pass
