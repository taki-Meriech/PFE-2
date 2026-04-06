import ollama
import json
import re

PROMPT_TEMPLATE = """
You are a Kubernetes planner AI.

Your job is to convert a user command into a LIST of JSON actions.

IMPORTANT RULES:
- Return ONLY valid JSON
- Return a JSON array []
- No markdown
- No explanations
- No comments
- No text outside JSON

Allowed actions:
- deploy
- scale

Each object MUST contain an "action" field.

Formats:

[
  {
    "action": "deploy",
    "name": "...",
    "image": "...",
    "replicas": ...
  },
  {
    "action": "scale",
    "name": "...",
    "replicas": ...
  }
]

Rules:
- If multiple steps, return multiple objects in a list
- If only one step, still return a list with one object
- For deploy, if replicas is missing, use 1
- For deploy, if name is missing, use image as name
- For scale, action must always be "scale"
- If unclear, return []

Command: "{TEXT}"

JSON:
"""

def build_prompt(text):
    return PROMPT_TEMPLATE.replace("{TEXT}", text)

def extract_json_array(raw_text):
    raw_text = raw_text.strip()

    # enlever les fences markdown
    raw_text = raw_text.replace("```json", "").replace("```", "").strip()

    # essayer de parser directement
    try:
        return json.loads(raw_text)
    except json.JSONDecodeError:
        pass

    # extraire le premier tableau [...]
    start = raw_text.find("[")
    if start == -1:
        return None

    depth = 0
    for i in range(start, len(raw_text)):
        ch = raw_text[i]
        if ch == "[":
            depth += 1
        elif ch == "]":
            depth -= 1
            if depth == 0:
                candidate = raw_text[start:i + 1]
                try:
                    return json.loads(candidate)
                except json.JSONDecodeError:
                    return None
    return None

def normalize_plan(plan):
    """
    Complète les champs manquants selon les règles métier.
    """
    if not isinstance(plan, list):
        return plan

    for step in plan:
        if not isinstance(step, dict):
            continue

        action = step.get("action")

        if action == "deploy":
            if "replicas" not in step:
                step["replicas"] = 1

            if "name" not in step and "image" in step:
                step["name"] = step["image"]

    return plan

def validate_plan(plan):
    if not isinstance(plan, list):
        return False, "La sortie n'est pas une liste JSON."

    for i, step in enumerate(plan, start=1):
        if not isinstance(step, dict):
            return False, f"L'étape {i} n'est pas un objet JSON."

        if "action" not in step:
            return False, f"L'étape {i} ne contient pas le champ 'action'."

        if step["action"] == "deploy":
            if "name" not in step:
                return False, f"L'étape {i} deploy n'a pas de 'name'."
            if "image" not in step:
                return False, f"L'étape {i} deploy n'a pas de 'image'."
            if "replicas" not in step:
                return False, f"L'étape {i} deploy n'a pas de 'replicas'."

        if step["action"] == "scale":
            if "name" not in step:
                return False, f"L'étape {i} scale n'a pas de 'name'."
            if "replicas" not in step:
                return False, f"L'étape {i} scale n'a pas de 'replicas'."

    return True, "Plan valide."

command = "deploy nginx puis scale à 3 replicas"

response = ollama.chat(
    model="gemma2:2b",
    messages=[{"role": "user", "content": build_prompt(command)}]
)

raw = response["message"]["content"]

print("Réponse brute :")
print(raw)

parsed = extract_json_array(raw)

print("\nParsed :")
print(parsed)

if parsed is not None:
    parsed = normalize_plan(parsed)

    print("\nPlan normalisé :")
    print(parsed)

    ok, msg = validate_plan(parsed)
    print("\nValidation :")
    print(msg)
else:
    print("\nValidation : impossible d'extraire un tableau JSON.")