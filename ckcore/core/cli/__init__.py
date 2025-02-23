from typing import TypeVar, Union, Coroutine, Any, Callable, AsyncIterator

from aiostream.core import Stream
from parsy import Parser, regex

from core.model.graph_access import Section
from core.parse_util import (
    make_parser,
    literal_dp,
    equals_dp,
    json_value_dp,
    space_dp,
    double_quote_dp,
    double_quoted_string_part_or_esc_dp,
    single_quoted_string_part_or_esc_dp,
    single_quote_dp,
)
from core.types import JsonElement

T = TypeVar("T")
# Allow the function to return either a coroutine or the result directly
Result = Union[T, Coroutine[Any, Any, T]]
JsGen = Union[Stream, AsyncIterator[JsonElement]]
# A sink function takes a stream and creates a result
Sink = Callable[[JsGen], Coroutine[Any, Any, T]]


@make_parser
def key_value_parser() -> Parser:
    key = yield literal_dp
    yield equals_dp
    value = yield json_value_dp
    return key, value


# name=value test=true -> {name: value, test: true}
key_values_parser: Parser = key_value_parser.sep_by(space_dp).map(dict)
# anything that is not: | " ' ; \
cmd_token = regex("[^|\"';\\\\]+")
# double quoted string is maintained with quotes: "foo" -> "foo"
double_quoted_string = double_quote_dp + double_quoted_string_part_or_esc_dp + double_quote_dp
# single quoted string is parsed without surrounding quotes: 'foo' -> foo
single_quoted_string = single_quote_dp >> single_quoted_string_part_or_esc_dp << single_quote_dp
# parse \| \" \' \; and unescape it \| -> |
escaped_token = regex("\\\\[|\"';]").map(lambda x: x[1])
# a command are tokens until EOF or pipe
cmd_args_parser = (escaped_token | double_quoted_string | single_quoted_string | cmd_token).at_least(1).concat()


def strip_quotes(string: str, strip: str = '"') -> str:
    s = string.strip()
    ls = len(strip)
    return s[ls : len(s) - ls] if s.startswith(strip) and s.endswith(strip) else s  # noqa: E203


# check if a is a json node element
def is_node(a: Any) -> bool:
    return "id" in a and Section.reported in a if isinstance(a, dict) else False
