"""Pure actual-auth-root lineage check; item mappings intentionally omit roots."""
from uuid import UUID


def require(value, message):
    if not value:
        raise ValueError(message)


def native_user_root(rows):
    roots = [(i,r) for i,r in enumerate(rows) if r.get('path')=='/walker/SuiteRoot']
    imports = [(i,r) for i,r in enumerate(rows) if r.get('path')=='/walker/SuiteImport']
    require(len(roots)==len(imports)==1, 'Exactly one actual SuiteRoot/SuiteImport pair required')
    root_index, root = roots[0]
    import_index, imported = imports[0]
    require(root_index<import_index, 'Native root report must precede fixture import')
    for row in (root,imported):
        require(row['http_status']==200 and row['output'].get('ok') is True
                and row['output'].get('error') is None, 'Root/import transport did not succeed')
    data = root['output'].get('data')
    require(type(data) is dict and type(data.get('reports')) is list and len(data['reports'])==1,
            'Exactly one native root report required')
    require(data.get('result',{}).get('reports')==data['reports'], 'Root envelope report copies differ')
    value = data['reports'][0]
    require(type(value) is str, 'Native root identity must be a UUID string')
    actor = UUID(value)
    supplied = imported['input'].get('roots')
    require(type(supplied) is dict and set(supplied)=={'user:0'}, 'Exactly one declared imported auth root required')
    require(type(supplied['user:0']) is str and UUID(supplied['user:0'])==actor,
            'SuiteImport user root differs from actual SuiteRoot report')
    return actor, dict(root_request=root['request'],import_request=imported['request'],
                       root_report=value,import_root=supplied['user:0'],single_auth_root=True)
