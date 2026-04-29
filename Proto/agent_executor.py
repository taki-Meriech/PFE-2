import json
import ollama
from k8s_module import load_k8s_config, create_deployment, scale_deployment

PROMPT_TEMPLATE = """
You are a strict JSON generator.

Convert Kubernetes commands into ONE JSON object only.

IMPORTANT RULES:
- Return ONLY valid JSON
- Never return explanations
- Never return markdown
- Never return arrays
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
- If unclear, return:
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

    try:
        return json.loads(raw_output)
    except json.JSONDecodeError:
        pass

    json_candidate = find_first_json(raw_output)
    if json_candidate:
        try:
            return json.loads(json_candidate)
        except json.JSONDecodeError:
            pass

    return None


def validate_command(data: dict):
    if not isinstance(data, dict):
        return False, "La sortie n'est pas un objet JSON."

    if "error" in data:
        return False, "Commande inconnue."

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
        if "replicas" not in data:
            return False, "Le champ 'replicas' est obligatoire pour scale."
        if not isinstance(data["replicas"], int):
            return False, "Le champ 'replicas' doit être un entier."

    return True, "Commande valide."


def execute_action(command_data: dict):
    action = command_data["action"]

    if action == "deploy":
        create_deployment(
            name=command_data["name"],
            image=command_data["image"],
            replicas=command_data["replicas"]
        )
        print("Action deploy exécutée avec succès.")

    elif action == "scale":
        scale_deployment(
            name=command_data["name"],
            replicas=command_data["replicas"]
        )
        print("Action scale exécutée avec succès.")


def main():
    user_command = input("Entre une commande Kubernetes : ")

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
        return

    print("\nJSON parsé :")
    print(parsed_output)

    is_valid, message = validate_command(parsed_output)
    print("\nRésultat de validation :")
    print(message)

    if not is_valid:
        return

    load_k8s_config()
    execute_action(parsed_output)


if __name__ == "__main__":
    main()