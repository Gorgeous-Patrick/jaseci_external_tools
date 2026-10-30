"""Meal requirements, shopping shortages and conserved pantry consumption."""
import from typing { cast }
node Ingredient {
    has name: str,
        initial: int,
        units: int;
}
node Recipe {
    has name: str;
}
node Requirement {
    has units: int;
}
node Meal {
    has name: str,
        servings: int,
        status: str = "planned";
}
node Purchase {
    has units: int;
}
node Consumption {
    has units: int;
}
edge Needs {}
edge IngredientRef {}
edge RecipeRef {}
edge Bought {}
edge Consumed {}
def _owns(item: object, kind: type) -> bool {
    return isinstance(item, kind) and jid(item) in [jid(n) for n in [root-->]];
}
def _requirements(meal: Meal) -> list[tuple[Ingredient, int]] {
    recipe = [meal->:RecipeRef:->[?:Recipe]][0];
    return [
        ([r->:IngredientRef:->[?:Ingredient]][0], r.units * meal.servings)
        for r in [recipe->:Needs:->[?:Requirement]]
    ];
}

walker Seed {
    has seed: int = 42;

    can seed with Root entry {
        if [-->[?:Recipe]] {
            report {"ok": True};
            return;
        }
        oats = here ++> Ingredient(
            name="Rolled oats", initial=5 + self.seed % 3, units=5 + self.seed % 3
        );
        milk = here ++> Ingredient(name="Milk", initial=2, units=2);
        flour = here ++> Ingredient(name="Flour", initial=6, units=6);
        porridge = here ++> Recipe(name="Breakfast porridge");
        pancakes = here ++> Recipe(name="Pancakes");
        for pair in [
            (porridge, oats, 2),
            (porridge, milk, 1),
            (pancakes, flour, 3),
            (pancakes, milk, 1)
        ] {
            requirement = pair[0] +>:Needs:+> Requirement(units=pair[2]);
            requirement +>:IngredientRef:+> pair[1];
        }
        report {"ok": True};
    }
}

walker PantryBoard {
    has ingredients: list[dict] = [],
        recipes: list[dict] = [],
        meals: list[dict] = [];

    can start with Root entry {
        visit [-->[?:Ingredient]];
        visit [-->[?:Recipe]];
        visit [-->[?:Meal]];
    }
    can ingredient with Ingredient entry {
        self.ingredients.append(
            {
                "id": jid(here),
                "name": here.name,
                "initial": here.initial,
                "units": here.units,
                "purchased": sum(p.units for p in [here->:Bought:->[?:Purchase]]),
                "consumed": sum(c.units for c in [here->:Consumed:->[?:Consumption]])
            }
        );
    }

    can recipe with Recipe entry {
        self.recipes.append({"id": jid(here), "name": here.name});
    }
    can meal with Meal entry {
        self.meals.append(
            {
                "id": jid(here),
                "name": here.name,
                "servings": here.servings,
                "status": here.status
            }
        );
    }
    can finish with Root exit {
        report {
            "ingredients": self.ingredients,
            "recipes": self.recipes,
            "meals": self.meals
        };
    }
}

walker PlanMeal {
    has recipe_id: str,
        name: str,
        servings: int;

    can plan with Root entry {
        recipe = jobj(self.recipe_id);
        if not _owns(recipe, Recipe) or not self.name.strip() or self.servings < 1 {
            report {
                "ok": False,
                "error": "Select a recipe, meal name and positive servings"
            };
            return;
        }
        meal = here ++> Meal(name=self.name.strip(), servings=self.servings);
        meal +>:RecipeRef:+> recipe;
        report {"ok": True, "meal_id": jid(meal)};
    }
}

walker ShoppingList {
    has required: dict = {};

    can start with Root entry {
        visit [-->[?:Meal, status=="planned"]];
    }
    can meal with Meal entry {
        for (ingredient, quantity) in _requirements(here) {
            self.required[jid(ingredient)] = self.required.get(jid(ingredient), 0)
                + quantity;
        }
    }
    can finish with Root exit {
        report [
            {
                "id": jid(i),
                "name": i.name,
                "required": self.required.get(jid(i), 0),
                "shortage": max(0, self.required.get(jid(i), 0) - i.units)
            } for i in [root-->[?:Ingredient]]
        ];
    }
}

walker BuyIngredient {
    has ingredient_id: str,
        quantity: int;

    can buy with Root entry {
        ingredient = jobj(self.ingredient_id);
        if not _owns(ingredient, Ingredient) or self.quantity < 1 {
            report {
                "ok": False,
                "error": "Select an ingredient and positive purchase quantity"
            };
            return;
        }
        ingredient = cast(Ingredient, ingredient);
        ingredient.units += self.quantity;
        ingredient +>:Bought:+> Purchase(units=self.quantity);
        report {"ok": True};
    }
}

walker CookMeal {
    has meal_id: str;

    can cook with Root entry {
        meal = jobj(self.meal_id);
        if not _owns(meal, Meal) {
            report {"ok": False, "error": "Meal is not available to this user"};
            return;
        }
        meal = cast(Meal, meal);
        if meal.status != "planned" {
            report {"ok": False, "error": "Meal has already been cooked"};
            return;
        }
        required = _requirements(meal);
        if any(i.units < q for (i, q) in required) {
            report {"ok": False, "error": "Buy missing ingredients before cooking"};
            return;
        }
        for (ingredient, quantity) in required {
            ingredient.units -= quantity;
            ingredient +>:Consumed:+> Consumption(units=quantity);
        }
        meal.status = "cooked";
        report {"ok": True};
    }
}
