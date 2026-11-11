"""Original RecipePantry scenario plus two explicit read-only filter checks."""
from scenarios import Scenario

def begin(server, token, seed, directory, reader):
    case = Scenario(server, token, directory)
    case.call('Seed', {'seed': seed})
    board = case.call(reader, read=True)
    case.call('Seed', {'seed': seed})
    assert case.call(reader, read=True) == board, 'Seed must be idempotent'
    return case, board

def recipe_pantry(server, token, seed, directory):
    c, b = begin(server, token, seed, directory, 'PantryBoard')
    recipes = {r['name']: r['id'] for r in b['recipes']}
    assert len(b['ingredients']) == 3 and len(recipes) == 2
    meal = c.call('PlanMeal', {'recipe_id': recipes['Breakfast porridge'], 'name': 'Breakfast', 'servings': 4})['meal_id']
    pancake = c.call('PlanMeal', {'recipe_id': recipes['Pancakes'], 'name': 'Lunch', 'servings': 2})['meal_id']
    before = c.call('PantryBoard', read=True)
    c.call('CookMeal', {'meal_id': meal}, False)
    assert c.call('PantryBoard', read=True) == before
    shopping = c.call('ShoppingList', read=True)
    assert {r['name']: (r['required'], r['shortage']) for r in shopping} == {
        'Rolled oats': (8, 3-seed%3), 'Milk': (6, 4), 'Flour': (6, 0)}
    c.call('BuyIngredient', {'ingredient_id': b['ingredients'][0]['id'], 'quantity': 0}, False)
    for r in shopping:
        if r['shortage']: c.call('BuyIngredient', {'ingredient_id': r['id'], 'quantity': r['shortage']})
    c.call('CookMeal', {'meal_id': meal}); c.call('CookMeal', {'meal_id': meal}, False)
    mixed = c.call('ShoppingList', read=True)
    assert {r['name']: (r['required'], r['shortage']) for r in mixed} == {
        'Rolled oats': (0, 0), 'Milk': (2, 0), 'Flour': (6, 0)}
    c.call('CookMeal', {'meal_id': pancake})
    none_planned = c.call('ShoppingList', read=True)
    assert {r['name']: (r['required'], r['shortage']) for r in none_planned} == {
        'Rolled oats': (0, 0), 'Milk': (0, 0), 'Flour': (0, 0)}
    c.assert_private('PantryBoard', 'ingredients', 'CookMeal', {'meal_id': meal})
    result = c.finish('PantryBoard')
    for i in result['expected_board']['ingredients']:
        assert i['units'] == 0 and i['initial'] + i['purchased'] == i['units'] + i['consumed']
    return result

