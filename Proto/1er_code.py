from kubernetes import client, config


def load_k8s_config():
    """
    Charge la configuration Kubernetes locale.
    """
    config.load_kube_config()


def list_pods():
    """
    Retourne la liste des pods de tous les namespaces.
    """
    v1 = client.CoreV1Api()
    pods = v1.list_pod_for_all_namespaces()

    print("Liste des pods du cluster :")
    for pod in pods.items:
        namespace = pod.metadata.namespace
        name = pod.metadata.name
        status = pod.status.phase
        print(f"- {namespace} / {name} : {status}")


def list_deployments():
    """
    Retourne la liste des deployments de tous les namespaces.
    """
    apps_v1 = client.AppsV1Api()
    deployments = apps_v1.list_deployment_for_all_namespaces()

    print("Liste des deployments du cluster :")
    for dep in deployments.items:
        namespace = dep.metadata.namespace
        name = dep.metadata.name
        replicas = dep.spec.replicas
        available = dep.status.available_replicas
        print(f"- {namespace} / {name} : replicas = {replicas}, disponibles = {available}")

def list_services():
    """
    Retourne la liste des services de tous les namespaces.
    """
    v1 = client.CoreV1Api()
    services = v1.list_service_for_all_namespaces()

    print("Liste des services du cluster :")
    for svc in services.items:
        namespace = svc.metadata.namespace
        name = svc.metadata.name
        svc_type = svc.spec.type
        cluster_ip = svc.spec.cluster_ip

        print(f"- {namespace} / {name} : type = {svc_type}, clusterIP = {cluster_ip}")

def create_deployment(name="nginx-test", image="nginx", replicas=1, namespace="default"):
    """
    Crée un deployment Kubernetes.
    """
    apps_v1 = client.AppsV1Api()

    container = client.V1Container(
        name=name,
        image=image,
        ports=[client.V1ContainerPort(container_port=80)]
    )

    template = client.V1PodTemplateSpec(
        metadata=client.V1ObjectMeta(labels={"app": name}),
        spec=client.V1PodSpec(containers=[container])
    )

    spec = client.V1DeploymentSpec(
        replicas=replicas,
        selector=client.V1LabelSelector(match_labels={"app": name}),
        template=template
    )

    deployment = client.V1Deployment(
        api_version="apps/v1",
        kind="Deployment",
        metadata=client.V1ObjectMeta(name=name),
        spec=spec
    )

    response = apps_v1.create_namespaced_deployment(
        namespace=namespace,
        body=deployment
    )

    print(f"Deployment créé : {response.metadata.name}")

def delete_deployment(name, namespace="default"):
    """
    Supprime un deployment Kubernetes.
    """
    apps_v1 = client.AppsV1Api()

    response = apps_v1.delete_namespaced_deployment(
        name=name,
        namespace=namespace
    )

    print(f"Suppression demandée pour le deployment : {name}")

def scale_deployment(name, replicas, namespace="default"):
    """
    Modifie le nombre de replicas d'un deployment Kubernetes.
    """
    apps_v1 = client.AppsV1Api()

    body = {
        "spec": {
            "replicas": replicas
        }
    }

    response = apps_v1.patch_namespaced_deployment_scale(
        name=name,
        namespace=namespace,
        body=body
    )

    print(f"Deployment '{name}' mis à l'échelle à {replicas} replicas.")

if __name__ == "__main__":
    load_k8s_config()

    print("=" * 50)
    list_pods()

    print("=" * 50)
    list_deployments()

    print("=" * 50)
    list_services()

    print("=" * 50)
    scale_deployment("nginx", 2)