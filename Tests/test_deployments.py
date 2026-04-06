from kubernetes import client, config

# Charger la configuration locale Kubernetes
config.load_kube_config()

# Client pour l'API des Deployments
apps_v1 = client.AppsV1Api()

# Récupérer tous les deployments dans tous les namespaces
deployments = apps_v1.list_deployment_for_all_namespaces()

print("Liste des deployments du cluster :")
for dep in deployments.items:
    name = dep.metadata.name
    namespace = dep.metadata.namespace
    replicas = dep.spec.replicas
    available = dep.status.available_replicas

    print(f"- {namespace} / {name} : replicas demandées = {replicas}, disponibles = {available}")