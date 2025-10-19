from leaky.base import LeakyCount
from leaky.memory import (
    LeakyMemoryUsage,
    get_memory_usage,
)


class TestGetMemoryUsage:
    """
    Tests the `get_memory_usage` function.
    """

    def test_get_memory_usage(self) -> None:
        """
        Test get_memory_usage.
        """
        result = get_memory_usage(LeakyCount(11))

        # There isn't much we can check here, but we can at least make sure
        # the result is a MemoryUsage object and has the expected fields.
        assert isinstance(result, LeakyMemoryUsage)
        assert isinstance(result.current_rss_bytes, int)
        assert result.current_rss_bytes > 0
        assert isinstance(result.system_percent_used, float)
        assert 0 <= result.system_percent_used <= 100
        assert isinstance(result.peak_rss_bytes, int)
        assert result.peak_rss_bytes > 0
        assert result.iteration_number == 11
