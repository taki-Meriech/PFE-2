import json
import ollama

PROMPT_TEMPLATE = """
You are a strict JSON generator.

Convert Kubernetes commands into ONE JSON object only.

IMPORTANT RULES:
- Return ONLY valid JSON
- Never return explanations
- Never return markdown
- Never return arrays
- Never use None
- Never use null for name
- For scale, the name must be the deployment name from the command
- Use double quotes only

Allowed actions:
- deploy
- scale

Formats:

{
  "action": "deploy",
  "name": "...",
  "image": "...",
  "replicas": ...
}

{
  "action": "scale",
  "name": "...",
  "replicas": ...
}

Rules:
- For deploy, if name is missing, use image as name
- For deploy, if replicas is missing, use 1
- For unclear commands, return:
{
  "error": "unknown_command"
}

Command: "{TEXT}"

JSON:
"""

ALLOWED_ACTIONS = ["deploy", "scale"]


def build_prompt(user_text: str) -> str:
    return PROMPT_TEMPLATE.replace("{TEXT}", user_text)


def find_first_json(text: str):
    start = text.find("{")
    if start == -1:
        return None

    depth = 0
    for i in range(start, len(text)):
        char = text[i]
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return text[start:i + 1]
    return None


def parse_model_response(raw_output: str):
    raw_output = raw_output.strip()

    # petite correction des sorties pseudo-Python
    raw_output = raw_output.replace(": None", ': null')
    raw_output = raw_output.replace(": True", ': true')
    raw_output = raw_output.replace(": False", ': false')

    try:
        parsed = json.loads(raw_output)
        if isinstance(parsed, list) and len(parsed) == 1 and isinstance(parsed[0], dict):
            return parsed[0]
        return parsed
    except json.JSONDecodeError:
        pass

    json_candidate = find_first_json(raw_output)
    if json_candidate:
        json_candidate = json_candidate.replace(": None", ': null')
        json_candidate = json_candidate.replace(": True", ': true')
        json_candidate = json_candidate.replace(": False", ': false')
        try:
            return json.loads(json_candidate)
        except json.JSONDecodeError:
            pass

    return None


def validate_command(data: dict):
    if not isinstance(data, dict):
        return False, "La sortie n'est pas un objet JSON."

    if "error" in data:
        if data["error"] == "unknown_command":
            return False, "Commande inconnue."
        return False, "Erreur retournée par le modèle."

    if "action" not in data:
        return False, "Le champ 'action' est manquant."

    action = data["action"]

    if action not in ALLOWED_ACTIONS:
        return False, f"Action non autorisée : {action}"

    if action == "deploy":
        if "name" not in data:
            return False, "Le champ 'name' est obligatoire pour deploy."
        if "image" not in data:
            return False, "Le champ 'image' est obligatoire pour deploy."
        if "replicas" not in data:
            return False, "Le champ 'replicas' est obligatoire pour deploy."
        if not isinstance(data["replicas"], int):
            return False, "Le champ 'replicas' doit être un entier."

    if action == "scale":
        if "name" not in data:
            return False, "Le champ 'name' est obligatoire pour scale."
        if data["name"] is None or data["name"] == "":
            return False, "Le champ 'name' ne doit pas être vide pour scale."
        if "replicas" not in data:
            return False, "Le champ 'replicas' est obligatoire pour scale."
        if not isinstance(data["replicas"], int):
            return False, "Le champ 'replicas' doit être un entier."

    return True, "Commande valide."


test_commands = [
    "deploy nginx avec 3 replicas",
    "scale nginx à 2 replicas"
]

for user_command in test_commands:
    print("=" * 60)
    print(f"Commande utilisateur : {user_command}")

    prompt = build_prompt(user_command)

    response = ollama.chat(
        model="gemma2:2b",
        messages=[
            {
                "role": "user",
                "content": prompt
            }
        ]
    )

    raw_output = response["message"]["content"]
    print("\nRéponse brute du modèle :")
    print(raw_output)

    parsed_output = parse_model_response(raw_output)

    if parsed_output is None:
        print("\nErreur : impossible d'extraire un JSON valide.")
        continue

    print("\nJSON parsé :")
    print(parsed_output)

    is_valid, message = validate_command(parsed_output)

    print("\nRésultat de validation :")
    print(message)