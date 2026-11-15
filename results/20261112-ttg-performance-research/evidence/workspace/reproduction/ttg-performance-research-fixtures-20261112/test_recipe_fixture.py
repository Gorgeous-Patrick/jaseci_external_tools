"""DB-free oracle/topology regressions; no native acceptance or timing claims."""
import copy
import unittest
from recipe_fixture import build_fixture, RecipeOracle, validate_graph, workload, digest, ERRORS, assert_report, write_fixture


class RecipeFixtureTests(unittest.TestCase):
    def fixture(self, **changes):
        return build_fixture(**dict(dict(ingredients=3,recipes=2,meals=6,cooked_meals=2),**changes))

    def test_repeatable_distinct_seed(self):
        self.assertEqual(self.fixture(), self.fixture())
        self.assertNotEqual(digest(self.fixture()), digest(self.fixture(seed=43)))

    def test_actual_initial_scale(self):
        a=self.fixture()
        b=self.fixture(ingredients=12,recipes=8,meals=24,cooked_meals=8)
        self.assertEqual(b['shape']['logical_nodes'],4*a['shape']['logical_nodes'])
        self.assertEqual(b['shape']['logical_edges'],4*a['shape']['logical_edges'])
        self.assertEqual(b['shape']['root_edges'],44)
        self.assertEqual(b['shape']['planned'],16)
        self.assertEqual(b['shape']['cooked'],8)
        self.assertEqual(workload(a)['operation_count'],workload(b)['operation_count'])

    def test_independent_closed_form_quantity(self):
        # Seed42, recipe0 amounts1,2,3; recipe1 amounts2,3,1.
        # Six servings3,4,1,2,3,4; cooked indices2,5.
        state=RecipeOracle(self.fixture())
        self.assertEqual([x['required'] for x in state.shopping()],[18,30,24])
        self.assertEqual([x['consumed'] for x in state.board()['ingredients']],[9,14,7])
        self.assertEqual([x['initial'] for x in state.board()['ingredients']],[9,14,7])

    def test_all_planned_and_all_cooked(self):
        for count in (0,6):
            value=self.fixture(cooked_meals=count)
            self.assertEqual(value['shape']['cooked'],count)
            state=RecipeOracle(value)
            if count==6:
                self.assertTrue(all(x['required']==0 and x['shortage']==0 for x in state.shopping()))
            else:
                self.assertTrue(all(x['required']>0 for x in state.shopping()))

    def test_rejections_preserve_graph(self):
        state=RecipeOracle(self.fixture());before=digest(state.graph)
        cases=[('CookMeal',{'meal_id':'meal:0'},ERRORS['stock'],{}),
               ('CookMeal',{'meal_id':'meal:2'},ERRORS['cooked'],{}),
               ('BuyIngredient',{'ingredient_id':'ingredient:0','quantity':0},ERRORS['buy'],{}),
               ('PlanMeal',{'recipe_id':'recipe:0','name':' ','servings':2},ERRORS['plan'],{}),
               ('CookMeal',{'meal_id':'meal:0'},ERRORS['ownership'],{'owner':'user:1'}),
               ('CookMeal',{'meal_id':'ingredient:0'},ERRORS['ownership'],{})]
        for walker,body,error,options in cases:
            self.assertEqual(state.apply(walker,body,**options),dict(ok=False,error=error))
            self.assertEqual(digest(state.graph),before)

    def test_positive_business_state_and_duplicates(self):
        state=RecipeOracle(self.fixture())
        for i,q in enumerate((3,6,9)):
            self.assertEqual(state.apply('BuyIngredient',dict(ingredient_id=f'ingredient:{i}',quantity=q)),dict(ok=True))
        self.assertEqual(state.apply('CookMeal',dict(meal_id='meal:0')),dict(ok=True))
        self.assertEqual([x['units'] for x in state.board()['ingredients']],[0,0,0])
        shape=validate_graph(state.graph)
        self.assertEqual(shape['node_types']['Purchase'],3)
        self.assertEqual(shape['node_types']['Consumption'],9)
        before=digest(state.graph)
        self.assertFalse(state.apply('CookMeal',dict(meal_id='meal:0'))['ok'])
        self.assertEqual(digest(state.graph),before)
        result=state.apply('PlanMeal',dict(recipe_id='recipe:0',name=' New meal ',servings=2),created_id='meal:created')
        self.assertEqual(result,dict(ok=True,meal_id='meal:created'))
        self.assertEqual(state.graph['nodes']['meal:created']['fields']['name'],'New meal')
        self.assertIn('meal:created',state.graph['root_attachments']['user:0'])

    def test_full_workflow_read_write_and_negative(self):
        result=workload(self.fixture())
        self.assertEqual(result['operation_count'],14)
        self.assertEqual(result['final_shape']['cooked'],3)
        errors=[r for r in result['steps'] if isinstance(r['expected_report'],dict) and r['expected_report'].get('ok') is False]
        self.assertEqual(len(errors),5)
        self.assertTrue(all(r['state_unchanged'] for r in errors))

    def test_topology_corruptions(self):
        good=self.fixture()['graph']
        variants=[]
        g=copy.deepcopy(good);g['root_attachments']['user:0'].pop();variants.append(g)
        g=copy.deepcopy(good);g['root_attachments']['user:0'].append('ingredient:0');variants.append(g)
        g=copy.deepcopy(good);g['edges'].append(copy.deepcopy(g['edges'][0]));variants.append(g)
        g=copy.deepcopy(good);g['edges'][1]['target']='recipe:0';variants.append(g)
        g=copy.deepcopy(good);g['nodes']['ingredient:0']['fields']['units']+=1;variants.append(g)
        for graph in variants:
            with self.assertRaises(ValueError):validate_graph(graph)

    def test_invalid_config(self):
        for changes in [dict(ingredients=True),dict(cooked_meals=7),dict(requirements_per_recipe=4),
                        dict(ingredients=20),dict(recipes=7),dict(seed=-1),dict(meals=0)]:
            with self.assertRaises(ValueError):self.fixture(**changes)

    def test_declared_table_order_only(self):
        state=RecipeOracle(self.fixture());expected=state.board();actual=copy.deepcopy(expected)
        actual['ingredients'].reverse();actual['meals'].reverse()
        assert_report('PantryBoard',actual,expected)
        actual['ingredients'].append(copy.deepcopy(actual['ingredients'][0]))
        with self.assertRaises(ValueError):assert_report('PantryBoard',actual,expected)
        actual=copy.deepcopy(expected);actual['ingredients'][0]['units']=False
        with self.assertRaises(ValueError):assert_report('PantryBoard',actual,expected)
        actual=copy.deepcopy(expected);actual['ingredients'][0]['name']='changed'
        with self.assertRaises(AssertionError):assert_report('PantryBoard',actual,expected)
        with self.assertRaises(AssertionError):assert_report('Other',[2,1],[1,2])

    def test_all_cooked_export(self):
        import tempfile
        from pathlib import Path
        import json
        with tempfile.TemporaryDirectory() as directory:
            output=Path(directory)/'dataset'
            manifest=write_fixture(output,self.fixture(cooked_meals=6))
            self.assertEqual(manifest['shape']['planned'],0)
            self.assertEqual(json.loads((output/'oracle-workload.json').read_text())['operation_count'],2)
            with self.assertRaises(FileExistsError):write_fixture(output,self.fixture())


if __name__=='__main__':
    unittest.main()
