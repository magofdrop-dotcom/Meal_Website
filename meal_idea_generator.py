from flask import Flask, render_template, request, jsonify
import random
import json
import os
import threading

app = Flask(__name__)

VALID_CATEGORIES = {"breakfast", "lunch", "dinner", "dessert", "bread and muffins"}
DATA_FILE = "meals.json"
_lock = threading.Lock()


def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r") as f:
            data = json.load(f)
        meals_data = {k.lower(): v for k, v in data.get("meals", {}).items()}
        recipes_data = data.get("recipes", {})
        # Migrate old string-format recipes to dict format
        for name, recipe in recipes_data.items():
            if isinstance(recipe, str):
                recipes_data[name] = {
                    "ingredients": recipe,
                    "instructions": "",
                    "notes": ""
                }
        return meals_data, recipes_data
    return {cat: [] for cat in VALID_CATEGORIES}, {}


def save_data(meals, recipes):
    tmp = DATA_FILE + ".tmp"
    with open(tmp, "w") as f:
        json.dump({"meals": meals, "recipes": recipes}, f, indent=2)
    os.replace(tmp, DATA_FILE)  # atomic write — avoids corruption on crash


meals, recipes = load_data()


@app.route('/')
def home():
    return render_template('meal_website.html')


@app.route('/get_meal_idea', methods=['POST'])
def get_meal_idea():
    meal_type = request.json.get("meal_type", "").strip().lower()
    if meal_type not in VALID_CATEGORIES:
        return jsonify({"error": f"Invalid meal type. Choose from: {', '.join(sorted(VALID_CATEGORIES))}"}), 400
    with _lock:
        category_meals = meals.get(meal_type, [])
    if not category_meals:
        return jsonify({"error": f"No meals in {meal_type} yet. Try adding some first!"}), 404
    selected = random.choice(category_meals)
    recipe = recipes.get(selected, {})
    return jsonify({"meal": selected, "recipe": recipe})


@app.route('/add_meal', methods=['POST'])
def add_meal():
    data = request.json or {}
    meal_type = data.get("meal_type", "").strip().lower()
    meal_name = data.get("meal_name", "").strip()
    ingredients = data.get("ingredients", "").strip()
    instructions = data.get("instructions", "").strip()
    notes = data.get("notes", "").strip()

    if meal_type not in VALID_CATEGORIES:
        return jsonify({"error": f"Invalid meal type."}), 400
    if not meal_name:
        return jsonify({"error": "Meal name cannot be empty."}), 400
    if len(meal_name) > 100:
        return jsonify({"error": "Meal name is too long (max 100 characters)."}), 400

    with _lock:
        bucket = meals.setdefault(meal_type, [])
        if meal_name in bucket:
            return jsonify({"error": f"'{meal_name}' already exists in {meal_type}."}), 409
        bucket.append(meal_name)
        recipes[meal_name] = {
            "ingredients": ingredients,
            "instructions": instructions,
            "notes": notes
        }
        save_data(meals, recipes)

    return jsonify({"message": f"Successfully added {meal_name} to {meal_type}!"})


@app.route('/search_meal', methods=['POST'])
def search_meal():
    meal_name = (request.json or {}).get("meal_name", "").strip().lower()
    if not meal_name:
        return jsonify({"error": "Please enter a meal name to search."}), 400
    with _lock:
        for key, recipe in recipes.items():
            if key.lower() == meal_name:
                return jsonify({"meal": key, "recipe": recipe})
    return jsonify({"error": "Meal not found. Try adding it first!"}), 404


@app.route('/list_meals', methods=['GET'])
def list_meals():
    with _lock:
        return jsonify(meals)


@app.route('/remove_meal', methods=['POST'])
def remove_meal():
    meal_name = (request.json or {}).get("meal_name", "").strip()
    if not meal_name:
        return jsonify({"error": "Meal name is required."}), 400
    with _lock:
        found = False
        for meal_list in meals.values():
            if meal_name in meal_list:
                meal_list.remove(meal_name)
                found = True
                break
        if not found:
            return jsonify({"error": "Meal not found."}), 404
        recipes.pop(meal_name, None)
        save_data(meals, recipes)
    return jsonify({"message": f"Successfully removed {meal_name}."})


@app.route('/edit_meal', methods=['POST'])
def edit_meal():
    data = request.json or {}
    old_name = data.get("old_meal_name", "").strip()
    new_name = data.get("new_meal_name", "").strip()
    ingredients = data.get("ingredients", "").strip()
    instructions = data.get("instructions", "").strip()
    notes = data.get("notes", "").strip()

    if not old_name or not new_name:
        return jsonify({"error": "Both old and new meal names are required."}), 400
    if len(new_name) > 100:
        return jsonify({"error": "Meal name too long (max 100 characters)."}), 400

    with _lock:
        if old_name not in recipes:
            return jsonify({"error": "Original meal not found."}), 404
        if new_name != old_name and new_name in recipes:
            return jsonify({"error": f"'{new_name}' already exists. Choose a different name."}), 409

        # Update the name in the category list
        for meal_list in meals.values():
            if old_name in meal_list:
                idx = meal_list.index(old_name)
                meal_list[idx] = new_name
                break

        recipes.pop(old_name)
        recipes[new_name] = {
            "ingredients": ingredients,
            "instructions": instructions,
            "notes": notes
        }
        save_data(meals, recipes)

    return jsonify({"message": f"Successfully updated {new_name}."})


@app.route('/get_recipe', methods=['POST'])
def get_recipe():
    meal_name = (request.json or {}).get("meal_name", "").strip()
    with _lock:
        recipe = recipes.get(meal_name)
    if recipe is None:
        return jsonify({"error": "Recipe not found."}), 404
    return jsonify({"meal": meal_name, "recipe": recipe})


if __name__ == '__main__':
    app.run(debug=True)