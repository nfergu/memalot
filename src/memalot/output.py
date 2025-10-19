from abc import ABC, abstractmethod
from typing import Iterable

from rich.console import Console, RenderableType
from rich.console import NewLine as RichNewLine

from memalot.options import Options
from memalot.themes import DEFAULT_RICH_THEME


class Output(ABC):
    """
    An object that can be sent to an output sink. This may be the console, a file, etc.
    """

    @abstractmethod
    def to_renderables(self) -> Iterable[RenderableType]:  # pragma: no cover
        """
        Converts this object to a list of rich renderable objects.

        This is used when printing the object to the console, log files, etc.
        """
        pass


class RichOutput(Output):
    """
    An output object that returns the passed-in renderable object.
    """

    def __init__(self, renderable: RenderableType) -> None:
        self._renderable = renderable

    def to_renderables(self) -> Iterable[RenderableType]:
        return [self._renderable]


class NewLine(RichOutput):
    """
    A new line output object.
    """

    def __init__(self) -> None:
        super().__init__(RichNewLine())


class NewBlock(str):
    """
    A new block
    """


class OutputWriter(ABC):
    """
    A writer that sends objects to an output sink. This may be the console, a file, etc.
    """

    @abstractmethod
    def write(self, output: Output) -> None:  # pragma: no cover
        pass


class RichConsoleWriter(OutputWriter):
    def __init__(self, options: Options, console: Console) -> None:
        self._console = console
        self._options = options

    def write(self, output: Output) -> None:
        if self._options.output_func is not None:
            renderables = iter(output.to_renderables())
            exhausted = False
            while not exhausted:
                with self._console.capture() as captured:
                    try:
                        while True:
                            renderable = next(renderables)
                            if isinstance(renderable, NewBlock):
                                break
                            if type(renderable) is not RichNewLine and renderable != "\n":
                                self._console.print(
                                    RichNewLine(),
                                    soft_wrap=True,
                                    crop=False,
                                    overflow="ignore",
                                )
                                self._console.print(
                                    renderable,
                                    soft_wrap=True,
                                    crop=False,
                                    overflow="ignore",
                                )
                    except StopIteration:
                        exhausted = True
                        pass
                captured_str = captured.get()
                if captured_str.strip() != "":
                    self._options.output_func(captured_str)
        if self._options.output_func is None or self._options.tee_console:
            for renderable in output.to_renderables():
                self._console.print(renderable, soft_wrap=True, crop=False, overflow="ignore")


def get_output_writer(options: Options) -> OutputWriter:
    return RichConsoleWriter(
        options=options,
        console=Console(
            force_terminal=options.force_terminal,
            theme=DEFAULT_RICH_THEME,
            no_color=not options.color,
        ),
    )
