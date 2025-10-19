from typing import List

from rich.console import Console, RenderableType
from rich.console import NewLine as RichNewLine
from rich.text import Text

from memalot.options import Options
from memalot.output import (
    NewBlock,
    NewLine,
    Output,
    RichConsoleWriter,
    RichOutput,
    get_output_writer,
)
from tests.utils_for_testing import create_mock


class TestsRichOutput:
    """
    Tests for the RichOutput class.
    """

    def test_rich_output_init(self) -> None:
        """
        Test that the RichOutput class is initialized correctly.
        """
        output = RichOutput(renderable=Text("Hello, world!"))
        assert output.to_renderables() == [Text("Hello, world!")]


class TestNewLine:
    """
    Tests for the NewLine class.
    """

    def test_new_line(self) -> None:
        """
        Test that the NewLine class functions as expected.
        """
        new_line = NewLine()
        renderables = list(new_line.to_renderables())
        assert len(renderables) == 1
        assert isinstance(renderables[0], RichNewLine)


class TestRichConsoleWriter:
    def test_write__no_output_func(self) -> None:
        """
        Test that the RichConsoleWriter class writes to the console when no output
        function is provided.
        """
        mock_console = create_mock(spec=Console)
        writer = RichConsoleWriter(options=Options(), console=mock_console)
        writer.write(RichOutput(renderable=Text("Hello, world!")))
        mock_console.print.assert_called_once_with(
            Text("Hello, world!"), soft_wrap=True, crop=False, overflow="ignore"
        )

    def test_write__with_output_func(self) -> None:
        """
        Test that the RichConsoleWriter class writes to the console when an output
        function is provided.
        """
        outputs: List[str] = []
        options = Options(output_func=outputs.append)
        writer = get_output_writer(options=options)
        writer.write(RichOutput(renderable=Text("Hello, world!")))
        assert outputs == ["\nHello, world!\n"]

    def test_write__with_output_func__newlines_ignored(self) -> None:
        """
        Test that the RichConsoleWriter class ignores newline renderables when an
        output function is provided.
        """
        outputs: List[str] = []
        options = Options(output_func=outputs.append)
        writer = get_output_writer(options=options)

        class MyOutput(Output):
            def to_renderables(self) -> List[RenderableType]:
                return [Text("Hello, world!"), RichNewLine(), "\n", RichNewLine(), "\n"]

        writer.write(MyOutput())
        assert outputs == ["\nHello, world!\n"]

    def test_write__with_new_block(self) -> None:
        """
        Test that the RichConsoleWriter handles NewBlock renderables correctly.
        """
        outputs: List[str] = []
        options = Options(output_func=outputs.append)
        writer = get_output_writer(options=options)

        class MyOutput(Output):
            def to_renderables(self) -> List[RenderableType]:
                return [Text("First block"), NewBlock("separator"), Text("Second block")]

        writer.write(MyOutput())
        # Should have two separate outputs due to NewBlock separator
        assert len(outputs) == 2
        assert "First block" in outputs[0]
        assert "Second block" in outputs[1]
