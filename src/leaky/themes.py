from rich.color import Color
from rich.style import Style
from rich.theme import Theme

FUNCTION_NAME = "function_name"
MEMORY_ABSOLUTE = "memory_absolute"
MEMORY_INCREASE = "memory_increase"
MEMORY_DECREASE = "memory_decrease"
COUNT = "count"
OBJECT_DETAILS_TITLE = "object_graph_title"
SIZE_TITLE = "size_title"
REFERRERS_TITLE = "referrers_title"
STRING_REPR_TITLE = "string_repr_title"
REFERRER_NAME = "referrer_name"
REFERRER_SUFFIX_LEAF = "referrer_name_leaf"
REFERRER_SUFFIX_CYCLE = "referrer_name_cycle"
OBJECT_ID = "object_id"
TITLE = "title"
HEADING_BORDER = "heading_border"
TABLE_TITLE = "table_title"
TABLE_HEADER = "table_header"
TABLE_BORDER = "table_border"
END_OF_SECTION_TEXT = "end_of_section_text"
CLI_TABLE_TITLE = "cli_table_title"
CLI_TABLE_STYLE = "cli_table_style"
CLI_TABLE_HEADER = "cli_table_header"
CLI_LIST_REPORT_ID = "cli_list_report_id"
CLI_ITERATIONS_COLUMN = "cli_iterations_column"
CLI_NO_REPORTS_MESSAGE = "cli_no_reports_message"

DEFAULT_RICH_THEME = Theme(
    {
        FUNCTION_NAME: Style(color="blue"),
        MEMORY_ABSOLUTE: Style(color="cyan"),
        MEMORY_INCREASE: Style(color="red"),
        MEMORY_DECREASE: Style(color="green"),
        COUNT: Style(color="magenta"),
        OBJECT_DETAILS_TITLE: Style(),
        SIZE_TITLE: Style(color="yellow"),
        REFERRERS_TITLE: Style(color="yellow"),
        STRING_REPR_TITLE: Style(color="yellow"),
        REFERRER_NAME: Style(color=Color.default()),
        OBJECT_ID: Style(color="bright_black"),
        TITLE: Style(bold=True),
        HEADING_BORDER: Style(color="yellow"),
        TABLE_TITLE: Style(color="yellow"),
        TABLE_HEADER: Style(color=Color.default()),
        TABLE_BORDER: Style(color="yellow"),
        END_OF_SECTION_TEXT: Style(color="yellow"),
        REFERRER_SUFFIX_LEAF: Style(color="blue", italic=True),
        REFERRER_SUFFIX_CYCLE: Style(color="bright_black", italic=True),
        CLI_TABLE_TITLE: Style(color="yellow"),
        CLI_TABLE_STYLE: Style(color="yellow"),
        CLI_TABLE_HEADER: Style(color="yellow"),
        CLI_LIST_REPORT_ID: Style(color="cyan"),
        CLI_ITERATIONS_COLUMN: Style(color="magenta"),
        CLI_NO_REPORTS_MESSAGE: Style(color="yellow"),
    }
)
"""
The default theme for rich output.
"""
