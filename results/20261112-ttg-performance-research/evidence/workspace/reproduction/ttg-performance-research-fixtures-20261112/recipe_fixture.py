"""Deterministic RecipePantry graph scale and independent relational oracle.

Standard library only. No Jac imports, process execution, database access, or timers.
Logical IDs must be bound bijectively to native IDs by the external native adapter.
"""
from collections import Counter, defaultdict
from copy import deepcopy
import hashlib
import json

NODE_TYPES = ('Ingredient', 'Recipe', 'Requirement', 'Meal', 'Purchase', 'Consumption')
EDGE_TYPES = ('Needs', 'IngredientRef', 'RecipeRef', 'Bought', 'Consumed')
PRESETS = {
    'tiny': dict(ingredients=3, recipes=2, meals=6, cooked_meals=2),
    'small': dict(ingredients=12, recipes=8, meals=24, cooked_meals=8),
    'large': dict(ingredients=120, recipes=80, meals=240, cooked_meals=80),
}
ERRORS = {
    'plan': 'Select a recipe, meal name and positive servings',
    'buy': 'Select an ingredient and positive purchase quantity',
    'ownership': 'Meal is not available to this user',
    'cooked': 'Meal has already been cooked',
    'stock': 'Buy missing ingredients before cooking',
}


def encoded(value):
    return (json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False) + '\n').encode()


def digest(value):
    return hashlib.sha256(encoded(value)).hexdigest()


def _integer(name, value, minimum=0):
    if type(value) is not int or value < minimum:
        raise ValueError(f'{name} must be an integer >= {minimum}')
    return value


def _node(nodes, key, kind, **fields):
    if key in nodes:
        raise ValueError('Duplicate logical node identity')
    nodes[key] = dict(id=key, type=kind, fields=fields)
    return key


def _edge(edges, source, kind, target):
    edges.append(dict(source=source, type=kind, target=target))


def build_fixture(*, ingredients, recipes, meals, cooked_meals,
                  requirements_per_recipe=3, seed=42):
    """Grow the initial graph itself; cooked meals have real consumption history.

    Each recipe references distinct ingredients, including ingredients shared with
    other recipes. Every ingredient and recipe is reachable by an initial meal.
    Initial remaining inventory is zero, so a planned meal needs a real purchase.
    """
    for name, value in [('ingredients', ingredients), ('recipes', recipes), ('meals', meals)]:
        _integer(name, value, 1)
    _integer('cooked_meals', cooked_meals)
    _integer('requirements_per_recipe', requirements_per_recipe, 1)
    _integer('seed', seed)
    k = requirements_per_recipe
    if cooked_meals > meals or k > ingredients or recipes * k < ingredients or meals < recipes:
        raise ValueError('Require cooked<=meals, requirements<=ingredients, recipes*requirements>=ingredients, meals>=recipes')
    nodes, edges, roots = {}, [], []
    for i in range(ingredients):
        key = _node(nodes, f'ingredient:{i}', 'Ingredient', name=f'Ingredient {i:04}', initial=0, units=0)
        roots.append(key)
    recipe_requirements = {}
    for r in range(recipes):
        recipe = _node(nodes, f'recipe:{r}', 'Recipe', name=f'Recipe {r:04}')
        roots.append(recipe)
        rows = []
        for j in range(k):
            ingredient = f'ingredient:{(r * k + j + seed) % ingredients}'
            quantity = 1 + (r + j + seed) % 3
            requirement = _node(nodes, f'requirement:{r}:{j}', 'Requirement', units=quantity)
            _edge(edges, recipe, 'Needs', requirement)
            _edge(edges, requirement, 'IngredientRef', ingredient)
            rows.append((ingredient, quantity))
        recipe_requirements[recipe] = rows
    # Evenly distributed deterministic status mix; exactly cooked_meals are cooked.
    cooked = {m for m in range(meals) if ((m + 1) * cooked_meals // meals) > (m * cooked_meals // meals)}
    for m in range(meals):
        recipe = f'recipe:{m % recipes}'
        servings = 1 + (m + seed) % 4
        meal = _node(nodes, f'meal:{m}', 'Meal', name=f'Meal {m:04}', servings=servings,
                     status='cooked' if m in cooked else 'planned')
        roots.append(meal)
        _edge(edges, meal, 'RecipeRef', recipe)
        if m in cooked:
            for j, (ingredient, units) in enumerate(recipe_requirements[recipe]):
                quantity = servings * units
                row = _node(nodes, f'consumption:initial:{m}:{j}', 'Consumption', units=quantity)
                _edge(edges, ingredient, 'Consumed', row)
                nodes[ingredient]['fields']['initial'] += quantity
    config = dict(ingredients=ingredients, recipes=recipes, meals=meals, cooked_meals=cooked_meals,
                  requirements_per_recipe=k, seed=seed)
    result = dict(app='recipe_pantry', config=config,
                  graph=dict(nodes=nodes, edges=edges, root_attachments={'user:0': roots}),
                  root_attachment_contract='Generic native root edges, exactly one for each listed Ingredient/Recipe/Meal; no Requirement/history root edges',
                  ordering_contract='PantryBoard ingredient/recipe/meal tables and ShoppingList have no source ORDER BY. Compare exact rows keyed by unique logical id, preserving cardinality; do not sort arbitrary lists or strings.')
    result['shape'] = validate_graph(result['graph'])
    result['initial_graph_sha256'] = digest(result['graph'])
    return result


def validate_graph(graph):
    """Independent topology/cardinality/conservation proof; raises on corruption."""
    nodes, edges = graph['nodes'], graph['edges']
    roots = graph['root_attachments']
    if set(roots) != {'user:0'}:
        raise ValueError('Exactly one declared fixture owner root required')
    attached = roots['user:0']
    expected = {k for k, n in nodes.items() if n['type'] in ('Ingredient', 'Recipe', 'Meal')}
    if len(attached) != len(set(attached)) or set(attached) != expected:
        raise ValueError('Root attachments differ, including duplicates')
    links = defaultdict(list)
    domains = {'Needs': ('Recipe', 'Requirement'), 'IngredientRef': ('Requirement', 'Ingredient'),
               'RecipeRef': ('Meal', 'Recipe'), 'Bought': ('Ingredient', 'Purchase'),
               'Consumed': ('Ingredient', 'Consumption')}
    incoming = Counter()
    for e in edges:
        a, b, kind = e['source'], e['target'], e['type']
        if a not in nodes or b not in nodes or kind not in domains:
            raise ValueError('Unknown/dangling graph link')
        if (nodes[a]['type'], nodes[b]['type']) != domains[kind]:
            raise ValueError('Wrong typed graph endpoints')
        links[a, kind].append(b)
        incoming[b, kind] += 1
    for key, n in nodes.items():
        if n['id'] != key or n['type'] not in NODE_TYPES:
            raise ValueError('Invalid node identity/type')
        kind, f = n['type'], n['fields']
        if kind == 'Requirement':
            if len(links[key, 'IngredientRef']) != 1 or incoming[key, 'Needs'] != 1:
                raise ValueError('Requirement must join one recipe and one ingredient')
            _integer('requirement units', f['units'], 1)
        elif kind == 'Meal':
            if len(links[key, 'RecipeRef']) != 1 or f['status'] not in ('planned', 'cooked'):
                raise ValueError('Meal must reference exactly one recipe with valid status')
            _integer('servings', f['servings'], 1)
        elif kind == 'Recipe':
            req = links[key, 'Needs']
            target = [links[x, 'IngredientRef'][0] for x in req]
            if not req or len(target) != len(set(target)):
                raise ValueError('Recipe requires nonempty distinct ingredient targets')
        elif kind in ('Purchase', 'Consumption'):
            _integer('history units', f['units'], 1)
            if incoming[key, 'Bought' if kind == 'Purchase' else 'Consumed'] != 1:
                raise ValueError('History node must have exactly one ingredient owner')
        elif kind == 'Ingredient':
            _integer('remaining units', f['units'])
            _integer('initial units', f['initial'])
            bought = sum(nodes[x]['fields']['units'] for x in links[key, 'Bought'])
            consumed = sum(nodes[x]['fields']['units'] for x in links[key, 'Consumed'])
            if f['initial'] + bought != f['units'] + consumed:
                raise ValueError('Inventory conservation failed')
    return dict(passed=True,logical_nodes=len(nodes),logical_edges=len(edges),
                root_edges=len(attached),node_types=dict(Counter(n['type'] for n in nodes.values())),
                edge_types=dict(Counter(e['type'] for e in edges)),
                planned=sum(n['type']=='Meal' and n['fields']['status']=='planned' for n in nodes.values()),
                cooked=sum(n['type']=='Meal' and n['fields']['status']=='cooked' for n in nodes.values()))


class RecipeOracle:
    """Relational expected results and exact poststate, without application execution."""
    def __init__(self, fixture):
        self.graph = deepcopy(fixture['graph'])
        validate_graph(self.graph)
        self.sequence = 0

    def _relations(self):
        by_kind = defaultdict(dict)
        for key, node in self.graph['nodes'].items():
            by_kind[node['type']][key] = node['fields']
        joins = defaultdict(list)
        for e in self.graph['edges']:
            joins[e['source'], e['type']].append(e['target'])
        return by_kind, joins

    def _requirements(self, meal):
        tables, joins = self._relations()
        recipe, = joins[meal, 'RecipeRef']
        servings = tables['Meal'][meal]['servings']
        # Relational RecipeRef JOIN Needs JOIN IngredientRef, then quantity product.
        return [(joins[r, 'IngredientRef'][0], tables['Requirement'][r]['units'] * servings)
                for r in joins[recipe, 'Needs']]

    def shopping(self):
        tables, _ = self._relations()
        required = Counter()
        for key, row in tables['Meal'].items():
            if row['status'] == 'planned':
                for ingredient, quantity in self._requirements(key):
                    required[ingredient] += quantity
        return [dict(id=key, name=f['name'], required=required[key],
                     shortage=max(0, required[key] - f['units']))
                for key, f in tables['Ingredient'].items()]

    def board(self):
        tables, joins = self._relations()
        return dict(ingredients=[dict(id=k, name=f['name'], initial=f['initial'], units=f['units'],
                                      purchased=sum(tables['Purchase'][p]['units'] for p in joins[k,'Bought']),
                                      consumed=sum(tables['Consumption'][p]['units'] for p in joins[k,'Consumed']))
                                  for k,f in tables['Ingredient'].items()],
                    recipes=[dict(id=k, name=f['name']) for k,f in tables['Recipe'].items()],
                    meals=[dict(id=k, name=f['name'], servings=f['servings'], status=f['status'])
                           for k,f in tables['Meal'].items()])

    def apply(self, walker, body=None, *, created_id=None, owner='user:0'):
        """Return exact report; declared business rejection must leave graph identical."""
        body = dict(body or {})
        before = digest(self.graph)
        nodes, edges = self.graph['nodes'], self.graph['edges']
        owned = set(self.graph['root_attachments']['user:0']) if owner == 'user:0' else set()
        tables, _ = self._relations()
        self.sequence += 1
        op = self.sequence
        if walker == 'PantryBoard':
            return self.board() if owner == 'user:0' else dict(ingredients=[],recipes=[],meals=[])
        if walker == 'ShoppingList':
            return self.shopping() if owner == 'user:0' else []
        if walker == 'PlanMeal':
            key = body['recipe_id']
            if key not in owned or key not in tables['Recipe'] or not body['name'].strip() or body['servings'] < 1:
                result = dict(ok=False,error=ERRORS['plan'])
            else:
                if created_id is None:
                    raise ValueError('A new logical identity must be declared before PlanMeal')
                _node(nodes,created_id,'Meal',name=body['name'].strip(),servings=body['servings'],status='planned')
                _edge(edges,created_id,'RecipeRef',key)
                self.graph['root_attachments']['user:0'].append(created_id)
                result = dict(ok=True,meal_id=created_id)
        elif walker == 'BuyIngredient':
            key = body['ingredient_id']
            if key not in owned or key not in tables['Ingredient'] or body['quantity'] < 1:
                result = dict(ok=False,error=ERRORS['buy'])
            else:
                quantity = body['quantity']
                nodes[key]['fields']['units'] += quantity
                history = _node(nodes,f'purchase:operation:{op}','Purchase',units=quantity)
                _edge(edges,key,'Bought',history)
                result = dict(ok=True)
        elif walker == 'CookMeal':
            key = body['meal_id']
            if key not in owned or key not in tables['Meal']:
                result = dict(ok=False,error=ERRORS['ownership'])
            elif tables['Meal'][key]['status'] != 'planned':
                result = dict(ok=False,error=ERRORS['cooked'])
            else:
                amounts = self._requirements(key)
                if any(tables['Ingredient'][k]['units'] < q for k,q in amounts):
                    result = dict(ok=False,error=ERRORS['stock'])
                else:
                    for j,(ingredient,quantity) in enumerate(amounts):
                        nodes[ingredient]['fields']['units'] -= quantity
                        history=_node(nodes,f'consumption:operation:{op}:{j}','Consumption',units=quantity)
                        _edge(edges,ingredient,'Consumed',history)
                    nodes[key]['fields']['status']='cooked'
                    result=dict(ok=True)
        else:
            raise ValueError('Unsupported business operation')
        if not result['ok'] and digest(self.graph) != before:
            raise AssertionError('Business rejection changed persistent state')
        validate_graph(self.graph)
        return result


def workload(fixture):
    """Fixed-size business sequence; scaled reads touch the initial enlarged graph."""
    state = RecipeOracle(fixture)
    planned = [k for k,n in state.graph['nodes'].items() if n['type']=='Meal' and n['fields']['status']=='planned']
    if not planned:
        raise ValueError('Mixed workflow requires at least one planned meal; all-cooked is a read-only control')
    meal = planned[0]
    recipe = next(e['target'] for e in state.graph['edges'] if e['source']==meal and e['type']=='RecipeRef')
    operations = [dict(walker='PantryBoard',input={}),dict(walker='ShoppingList',input={}),
                  dict(walker='CookMeal',input={'meal_id':meal}),
                  dict(walker='BuyIngredient',input={'ingredient_id':'ingredient:0','quantity':0}),
                  dict(walker='PlanMeal',input={'recipe_id':recipe,'name':'  ','servings':1}),
                  dict(walker='PlanMeal',input={'recipe_id':recipe,'name':'  Added meal  ','servings':2},created_id='meal:created:0')]
    for ingredient,quantity in state._requirements(meal):
        operations.append(dict(walker='BuyIngredient',input={'ingredient_id':ingredient,'quantity':quantity}))
    operations += [dict(walker='CookMeal',input={'meal_id':meal}),
                   dict(walker='CookMeal',input={'meal_id':meal}),
                   dict(walker='CookMeal',input={'meal_id':meal},owner='user:1'),
                   dict(walker='PantryBoard',input={}),dict(walker='ShoppingList',input={})]
    steps=[]
    for operation in operations:
        pre=digest(state.graph)
        report=state.apply(operation['walker'],operation['input'],created_id=operation.get('created_id'),owner=operation.get('owner','user:0'))
        steps.append(dict(operation=operation,expected_report=report,prestate_sha256=pre,poststate_sha256=digest(state.graph),
                          state_unchanged=pre==digest(state.graph)))
    return dict(steps=steps,final_graph=state.graph,final_shape=validate_graph(state.graph),
                operation_count=len(steps),note='Operation count depends on requirements_per_recipe only, not graph scale; mixed fixture needed. Native restart/actor/HTTP/physical acceptance remains external.')


def canonical_report(walker, report):
    """Normalize ONLY declared unordered business tables; reject duplicate IDs.

    Caller first maps native UUIDs bijectively to independently declared logical
    identities. Every field/type and row multiplicity remains significant.
    """
    schemas = {
        'ingredients': dict(id=str,name=str,initial=int,units=int,purchased=int,consumed=int),
        'recipes': dict(id=str,name=str),
        'meals': dict(id=str,name=str,servings=int,status=str),
        'shopping': dict(id=str,name=str,required=int,shortage=int),
    }
    def table(name, rows):
        if type(rows) is not list:
            raise ValueError('Business table must be a list')
        seen=set()
        for row in rows:
            if type(row) is not dict or set(row)!=set(schemas[name]):
                raise ValueError('Business table field set differs')
            if any(type(row[k]) is not typ for k,typ in schemas[name].items()):
                raise ValueError('Business table field type differs')
            if row['id'] in seen:
                raise ValueError('Duplicate logical identity in business table')
            seen.add(row['id'])
        return sorted(deepcopy(rows),key=lambda row:row['id'])
    if walker=='ShoppingList':
        return table('shopping',report)
    if walker=='PantryBoard':
        if type(report) is not dict or set(report)!=set(('ingredients','recipes','meals')):
            raise ValueError('PantryBoard field set differs')
        return {name:table(name,report[name]) for name in ('ingredients','recipes','meals')}
    return deepcopy(report)


def assert_report(walker, actual, expected):
    if encoded(canonical_report(walker,actual))!=encoded(canonical_report(walker,expected)):
        raise AssertionError('Business report differs from independent expected rows/values/types')


def write_fixture(directory, fixture):
    """Export importable JSONL and oracle records; refuses existing output."""
    from pathlib import Path
    directory=Path(directory)
    directory.mkdir(parents=True,exist_ok=False)
    graph=fixture['graph']
    for name,rows in [('nodes.jsonl',graph['nodes'].values()),('edges.jsonl',graph['edges'])]:
        (directory/name).write_bytes(b''.join(encoded(row) for row in rows))
    (directory/'root-attachments.json').write_bytes(encoded(graph['root_attachments']))
    (directory/'fixture.json').write_bytes(encoded(fixture))
    if fixture['shape']['planned']:
        plan=workload(fixture)
    else:
        state=RecipeOracle(fixture)
        plan=dict(steps=[dict(operation=dict(walker=w,input={}),expected_report=state.apply(w))
                         for w in ('PantryBoard','ShoppingList')],final_graph=state.graph,
                  final_shape=validate_graph(state.graph),operation_count=2,
                  note='All-cooked read-only control; no false missing-stock/cook-success claim.')
    (directory/'oracle-workload.json').write_bytes(encoded(plan))
    files={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in directory.iterdir() if p.is_file()}
    manifest=dict(app='recipe_pantry',stage='Pure preparation only; native import/HTTP/restart/physical checks pending',
                  config=fixture['config'],shape=fixture['shape'],files=files,
                  source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                  native_source_changes=[],root_attachment_file='root-attachments.json')
    (directory/'manifest.json').write_bytes(encoded(manifest))
    return manifest


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',required=True)
    parser.add_argument('--preset',choices=tuple(PRESETS),default='small')
    for name in ('ingredients','recipes','meals','cooked-meals','requirements-per-recipe','seed'):
        parser.add_argument('--'+name,type=int,default=None)
    args=parser.parse_args()
    config=PRESETS[args.preset].copy()
    for name in ('ingredients','recipes','meals','cooked_meals','requirements_per_recipe','seed'):
        if getattr(args,name) is not None:config[name]=getattr(args,name)
    result=write_fixture(args.output,build_fixture(**config))
    print(json.dumps(dict(stage=result['stage'],config=result['config'],shape=result['shape']),indent=2))
