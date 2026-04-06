from kubernetes import client, config

# Charger la configuration Kubernetes locale (~/.kube/config)
config.load_kube_config()

# Créer un client pour l'API Core V1
v1 = client.CoreV1Api()

# Récupérer tous les pods de tous les namespaces
pods = v1.list_pod_for_all_namespaces()

print("Liste des pods du cluster :")
for pod in pods.items:
    print(f"- {pod.metadata.namespace} / {pod.metadata.name} : {pod.status.phase}")

