"""Non-null typed subquery membership, including duplicates and empty results."""
import jaclang.sql as q;
import sqlite3;


def members(nullable: bool = False) -> any {
    return q.table(
        'members',
        [q.field('value', q.nullable(q.int64_type()) if nullable else q.int64_type())]
    );
}


test "IN query accepts many rows and preserves empty and duplicate membership semantics" {
    db = sqlite3.connect(':memory:');
    try {
        db.execute('CREATE TABLE members (value INTEGER NOT NULL)');
        db.executemany('INSERT INTO members VALUES (?)', [(2, ), (2, ), (3, )]);
        source = members();
        field = q.field('value', q.int64_type());
        subquery = q.select([q.named('value', source.col(field))], source=source);
        expression = q.in_query(q.int64(2), subquery, field);
        compiled = q.compile_sql(q.select([q.named('member', expression)]));
        assert ' IN (SELECT ' in compiled.sql;
        assert db.execute(compiled.sql, compiled.params).fetchall() == [(1, )];
        db.execute('DELETE FROM members');
        assert db.execute(compiled.sql, compiled.params).fetchall() == [(0, )];
    } finally {
        db.close();
    }
}

test "IN query rejects nullable mismatched or multiple output columns" {
    source = members(True);
    field = q.field('value', q.nullable(q.int64_type()));
    subquery = q.select([q.named('value', source.col(field))], source=source);
    rejected = False;
    try {
        q.in_query(q.int64(2), subquery, q.field('value', q.int64_type()));
    } except q.SqlError {
        rejected = True;
    }
    assert rejected;
    rejected = False;
    try {
        multi = q.select([q.named('one', q.int64(1)), q.named('two', q.int64(2))]);
        q.in_query(q.int64(2), multi, q.field('one', q.int64_type()));
    } except q.SqlError {
        rejected = True;
    }
    assert rejected;
}
