import pytest

from memalot.options import InvalidOptionsError, Options


class TestOptions:
    def test_invalid_options(self) -> None:
        with pytest.raises(InvalidOptionsError):
            Options(output_func=lambda x: None, tee_console=False, force_terminal=True)
