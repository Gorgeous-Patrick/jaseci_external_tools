"""Controlled diagnostic transformations of captured SQL; production uses SQL AST."""
import re

# Match only the exact graph_types correlation emitted by baseline85026d.
PATTERN = re.compile(
    r'EXISTS \(SELECT CAST\(:p\d+ AS bigint\) AS "one" FROM "graph_types" AS "(?P<g>_t\d+)" '
    r'WHERE \(\("(?P=g)"\."type_name" = "(?P<t>_t\d+)"\."arch_type"\) '
    r'AND \("(?P=g)"\."ancestor" = (?P<p>CAST\(:p\d+ AS text\))\)\)\)')


def type_membership(sql):
    def replace(match):
        g, t, p = match.group('g', 't', 'p')
        return (f'("{t}"."arch_type" IN (SELECT "{g}"."type_name" '
                f'FROM "graph_types" AS "{g}" WHERE "{g}"."ancestor" = {p}))')
    result, count = PATTERN.subn(replace, sql)
    if count == 0:
        raise ValueError('No exact baseline type predicate matched')
    return result, count
