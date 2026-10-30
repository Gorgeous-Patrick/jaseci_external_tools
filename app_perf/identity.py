"""Order-preserving alpha-renaming for fresh-DB correctness comparisons.

One bijection persists across the ENTIRE ordered workload transcript. Fixture
logical IDs are installed as anchors before actions. Additional observed IDs
receive distinct labels in first-encounter order, never a shared placeholder.
Only UUID identity tokens change. Every dict field, list position, scalar,
embedded-ID reference and non-ID digest character is retained.
"""
import hashlib
import ast
import json
import re
from uuid import UUID

# A 64-hex digest is deliberately NOT an ID. Percent-encoded UUID hyphens are
# supported without decoding/re-encoding the rest of a URL or semantic string.
TOKEN = re.compile(r'(?<![0-9a-fA-F])(?:[0-9a-fA-F]{8}(?:-|%2[dD])[0-9a-fA-F]{4}(?:-|%2[dD])'
    r'[0-9a-fA-F]{4}(?:-|%2[dD])[0-9a-fA-F]{4}(?:-|%2[dD])[0-9a-fA-F]{12}|[0-9a-fA-F]{32})(?![0-9a-fA-F])')

def key(value):
    return UUID(re.sub('%2[dD]', '-', str(value))).hex

def encoded(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()

class Identities:
    def __init__(self, anchors=None, set_schema=None):
        self.mapping = {}
        self.set_schema=set_schema or {}
        for actual, logical in (anchors or {}).items():
            identity = key(actual)
            if identity in self.mapping or logical in self.mapping.values():
                raise ValueError('Fixture anchors must be a bijection')
            self.mapping[identity] = str(logical)

    def token(self, match):
        identity = key(match.group())
        if identity not in self.mapping:
            self.mapping[identity] = 'observed:' + str(len(self.mapping))
        return '<id:' + self.mapping[identity] + '>'

    def declared_set(self,value,schema):
        if schema.get('element_type')!='str':raise ValueError('Unsupported declared set element type')
        if not isinstance(value,str):raise ValueError('Declared set field must use the audited string-repr encoding')
        try:
            syntax=ast.parse(value,mode='eval').body
            parsed=ast.literal_eval(value)
        except (ValueError,SyntaxError,TypeError) as error:
            raise ValueError('Invalid declared set repr') from error
        if type(parsed) is not set:raise ValueError('Declared set repr did not parse to a set')
        if isinstance(syntax,ast.Set) and len(syntax.elts)!=len(parsed):raise ValueError('Duplicate elements in serialized set repr')
        members=[]
        for item in parsed:
            if type(item) is not str:raise ValueError('Declared set[str] contains a non-string member')
            if TOKEN.fullmatch(item):
                if key(item) not in self.mapping:raise ValueError('Declared set references an unknown UUID identity')
                members.append(TOKEN.sub(self.token,item))
            else:members.append(item)
        if len(set(members))!=len(parsed):raise ValueError('Set identity normalization collapsed distinct members')
        return {'__declared_set__':'str','members':sorted(members)}

    def normalize(self, value):
        if isinstance(value, dict):
            result = {}
            declared=self.set_schema.get(value.get('_jac_type'),{}) if value.get('_jac_archetype')=='walker' else {}
            for name in sorted(value):
                label = self.normalize(name)
                if label in result:
                    raise ValueError('Identity normalization collided dictionary keys')
                result[label] = self.declared_set(value[name],declared[name]) if name in declared else self.normalize(value[name])
            return result
        if isinstance(value, list):
            return [self.normalize(item) for item in value]
        if isinstance(value, tuple):
            return [self.normalize(item) for item in value]
        if isinstance(value, str):
            return TOKEN.sub(self.token, value)
        return value

    def digest(self, value):
        return hashlib.sha256(encoded(self.normalize(value))).hexdigest()
