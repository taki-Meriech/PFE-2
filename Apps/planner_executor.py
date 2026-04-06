import json
import ollama
from k8s_module import (
    load_k8s_config,
    create_deployment,
    scale_deployment,
    delete_deployment,
    list_pods,
    list_deployments,
    list_services,
    is_cluster_available,
    deployment_exists
)
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
- delete
- list_pods
- list_deployments
- list_services

Each object MUST contain an "action" field.

Formats:

[
  {
    "action": "deploy",
    "name": "...",
    "image": "...",
    "replicas": ...
  }
]

[
  {
    "action": "scale",
    "name": "...",
    "replicas": ...
  }
]

[
  {
    "action": "delete",
    "name": "..."
  }
]

[
  {
    "action": "list_pods"
  }
]

[
  {
    "action": "list_deployments"
  }
]

[
  {
    "action": "list_services"
  }
]

Rules:
- If multiple steps, return multiple objects in a list
- If only one step, still return a list with one object
- For deploy, if replicas is missing, use 1
- For deploy, if name is missing, use image as name
- For scale, action must always be "scale"
- For delete, include the deployment name
- If the user asks to show pods, use "list_pods"
- If the user asks to show deployments, use "list_deployments"
- If the user asks to show services, use "list_services"
- If unclear, return []

Command: "{TEXT}"

JSON:
"""


def build_prompt(text):
    return PROMPT_TEMPLATE.replace("{TEXT}", text)


def extract_json_array(raw_text):
    raw_text = raw_text.strip()
    raw_text = raw_text.replace("```json", "").replace("```", "").strip()

    # essai direct
    try:
        return json.loads(raw_text)
    except json.JSONDecodeError:
        pass

    # extraire le premier tableau [...]
    start = raw_text.find("[")
    if start == -1:
        return None

    depth = 0
    candidate = None

    for i in range(start, len(raw_text)):
        ch = raw_text[i]
        if ch == "[":
            depth += 1
        elif ch == "]":
            depth -= 1
            if depth == 0:
                candidate = raw_text[start:i + 1]
                break

    if candidate is None:
        return None

    # essai 2 : parser tel quel
    try:
        return json.loads(candidate)
    except json.JSONDecodeError:
        pass

    # essai 3 : petites réparations fréquentes
    repaired = candidate

    # ajoute une virgule manquante entre deux champs JSON sur lignes séparées
    repaired = re.sub(r'("\s*)\n(\s*")', r'\1,\n\2', repaired)

    # corrige virgule manquante après une valeur string avant un nouveau champ
    repaired = re.sub(r'(":\s*"[^"]+")\s*\n(\s*")', r'\1,\n\2', repaired)

    # corrige virgule manquante après une valeur numérique avant un nouveau champ
    repaired = re.sub(r'(":\s*\d+)\s*\n(\s*")', r'\1,\n\2', repaired)

    try:
        return json.loads(repaired)
    except json.JSONDecodeError:
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

        action = step["action"]

        if action == "deploy":
            if "name" not in step:
                return False, f"L'étape {i} deploy n'a pas de 'name'."
            if "image" not in step:
                return False, f"L'étape {i} deploy n'a pas de 'image'."
            if "replicas" not in step:
                return False, f"L'étape {i} deploy n'a pas de 'replicas'."

        elif action == "scale":
            if "name" not in step:
                return False, f"L'étape {i} scale n'a pas de 'name'."
            if "replicas" not in step:
                return False, f"L'étape {i} scale n'a pas de 'replicas'."

        elif action == "delete":
            if "name" not in step:
                return False, f"L'étape {i} delete n'a pas de 'name'."

        elif action in ["list_pods", "list_deployments", "list_services"]:
            pass

        else:
            return False, f"L'étape {i} a une action inconnue : {action}"

    return True, "Plan valide."


def check_plan_consistency(plan):
    """
    Vérifie la cohérence logique d'un plan multi-étapes.
    """
    if not isinstance(plan, list) or len(plan) == 0:
        return False, "Plan vide ou invalide."

    deployed_names = set()
    seen_deploys = set()

    for i, step in enumerate(plan, start=1):
        action = step.get("action")
        name = step.get("name")

        if action == "deploy":
            if name in seen_deploys:
                return False, f"Le deployment '{name}' apparaît plusieurs fois en deploy."
            seen_deploys.add(name)
            deployed_names.add(name)

        elif action == "scale":
            if not name:
                return False, f"L'étape {i} scale n'a pas de nom."
            # autorisé si le même plan a déjà fait un deploy de ce nom
            # sinon on laisse passer aussi, car la ressource peut exister déjà dans le cluster
            # mais si le plan contient un deploy différent juste avant, on peut détecter une incohérence simple
            previous_deploys = [s.get('name') for s in plan[:i-1] if s.get('action') == 'deploy']
            if previous_deploys and name not in previous_deploys:
                return False, (
                    f"L'étape {i} scale cible '{name}', "
                    f"mais le plan a déployé auparavant {previous_deploys}."
                )

    return True, "Plan cohérent."


def check_plan_consistency(plan):
    """
    Vérifie la cohérence logique d'un plan multi-étapes.
    """
    if not isinstance(plan, list) or len(plan) == 0:
        return False, "Plan vide ou invalide."

    seen_deploys = set()

    for i, step in enumerate(plan, start=1):
        action = step.get("action")
        name = step.get("name")

        if action == "deploy":
            if name in seen_deploys:
                return False, f"Le deployment '{name}' apparaît plusieurs fois en deploy."
            seen_deploys.add(name)

        elif action == "scale":
            if not name:
                return False, f"L'étape {i} scale n'a pas de nom."
            previous_deploys = [s.get("name") for s in plan[:i-1] if s.get("action") == "deploy"]
            if previous_deploys and name not in previous_deploys:
                return False, (
                    f"L'étape {i} scale cible '{name}', "
                    f"mais le plan a déployé auparavant {previous_deploys}."
                )

        elif action == "delete":
            if not name:
                return False, f"L'étape {i} delete n'a pas de nom."

    return True, "Plan cohérent."

def validate_business_rules(plan):
    """
    Vérifie des règles métier simples avant exécution.
    """
    forbidden_names = {"", None}
    forbidden_image_tokens = {
        "your", "image", "name", "here", "placeholder", "example", "demo"
    }

    for i, step in enumerate(plan, start=1):
        action = step.get("action")
        name = step.get("name")
        image = step.get("image")

        if action == "deploy":
            if name in forbidden_names:
                return False, f"L'étape {i} deploy a un nom invalide."

            if image in {"", None}:
                return False, f"L'étape {i} deploy a une image vide ou absente."

            image_lower = str(image).lower()
            tokens = re.split(r"[-_/:\s]+", image_lower)

            if any(token in forbidden_image_tokens for token in tokens):
                return False, f"L'étape {i} deploy a une image placeholder invalide : {image}"

        elif action == "scale":
            if name in forbidden_names:
                return False, f"L'étape {i} scale a un nom invalide."

        elif action == "delete":
            if name in forbidden_names:
                return False, f"L'étape {i} delete a un nom invalide."

    return True, "Règles métier validées."

def execute_plan(plan):
    if not is_cluster_available():
        print("Cluster Kubernetes indisponible. Vérifie Docker et Minikube.")
        return

    for i, step in enumerate(plan, start=1):
        action = step["action"]
        print(f"\n--- Exécution étape {i}: {action} ---")

        if action == "deploy":
            name = step["name"]

            if deployment_exists(name):
                print(f"Le deployment '{name}' existe déjà. Deploy ignoré.")
                continue

            created = create_deployment(
                name=step["name"],
                image=step["image"],
                replicas=step["replicas"]
            )

            if created:
                print(f"Deploy exécuté pour {step['name']}")
            else:
                print(f"Deploy ignoré pour {step['name']}")

        elif action == "scale":
            name = step["name"]

            if not deployment_exists(name):
                print(f"Impossible de scaler : le deployment '{name}' n'existe pas.")
                continue

            scale_deployment(
                name=step["name"],
                replicas=step["replicas"]
            )
            print(f"Scale exécuté pour {step['name']} -> {step['replicas']} replicas")

        elif action == "delete":
            name = step["name"]

            if not deployment_exists(name):
                print(f"Impossible de supprimer : le deployment '{name}' n'existe pas.")
                continue

            delete_deployment(name=name)
            print(f"Delete exécuté pour {name}")

        elif action == "list_pods":
            list_pods()

        elif action == "list_deployments":
            list_deployments()

        elif action == "list_services":
            list_services()

        else:
            print(f"Action inconnue ignorée : {action}")

def auto_fix_plan(plan):
    """
    Tente de corriger certaines valeurs invalides avant validation métier.
    """
    if not isinstance(plan, list):
        return plan

    known_images = ["nginx", "redis", "httpd", "mysql", "mongodb"]

    for step in plan:
        if not isinstance(step, dict):
            continue

        action = step.get("action")
        name = str(step.get("name", "")).lower()
        image = str(step.get("image", "")).lower()

        if action == "deploy":
            invalid_images = {
                "", "none", "your_image", "your-image",
                "your-image-name", "your_image_here"
            }

            if image in invalid_images:
                for known in known_images:
                    if known in name:
                        step["image"] = known
                        break

    return plan

def main():
    user_command = input("Entre une commande complexe Kubernetes : ")

    response = ollama.chat(
        model="gemma2:2b",
        messages=[{"role": "user", "content": build_prompt(user_command)}]
    )

    raw = response["message"]["content"]

    print("\nRéponse brute :")
    print(raw)

    parsed = extract_json_array(raw)

    print("\nParsed :")
    print(parsed)

    if parsed is None:
        print("\nErreur : impossible d'extraire un tableau JSON.")
        return

    parsed = normalize_plan(parsed)

    print("\nPlan normalisé :")
    print(parsed)

    parsed = auto_fix_plan(parsed)

    print("\nPlan après correction automatique :")
    print(parsed)

    ok, msg = validate_plan(parsed)
    print("\nValidation :")
    print(msg)

    if not ok:
        return

    consistent, consistency_msg = check_plan_consistency(parsed)
    print("\nCohérence du plan :")
    print(consistency_msg)

    if not consistent:
        return

    business_ok, business_msg = validate_business_rules(parsed)
    print("\nValidation métier :")
    print(business_msg)

    if not business_ok:
        return

    load_k8s_config()
    execute_plan(parsed)

if __name__ == "__main__":
    main()