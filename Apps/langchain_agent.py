from langchain_ollama import ChatOllama
from langchain.tools import tool
from langchain.agents import create_agent

from k8s_module import (
    load_k8s_config,
    create_deployment,
    scale_deployment
)

# Load Kubernetes config
load_k8s_config()

# Local Ollama model
llm = ChatOllama(model="gemma2:2b")


@tool
def deploy_app(input: str) -> str:
    """Deploy a Kubernetes application.
    Input format: name,image,replicas
    Example: nginx-test,nginx,1
    """
    try:
        name, image, replicas = input.split(",")
        create_deployment(
            name=name.strip(),
            image=image.strip(),
            replicas=int(replicas.strip())
        )
        return f"Deployment {name.strip()} created with {replicas.strip()} replicas."
    except Exception as e:
        return f"Deploy error: {e}"


@tool
def scale_app(input: str) -> str:
    """Scale a Kubernetes deployment.
    Input format: name,replicas
    Example: nginx-test,2
    """
    try:
        name, replicas = input.split(",")
        scale_deployment(
            name=name.strip(),
            replicas=int(replicas.strip())
        )
        return f"Deployment {name.strip()} scaled to {replicas.strip()} replicas."
    except Exception as e:
        return f"Scale error: {e}"


tools = [deploy_app, scale_app]

agent = create_agent(
    model=llm,
    tools=tools,
    system_prompt=(
        "You are a Kubernetes agent. "
        "Use the available tools to deploy or scale applications. "
        "When using deploy_app, pass input as: name,image,replicas. "
        "When using scale_app, pass input as: name,replicas. "
        "Do not explain tool usage unless needed."
    ),
)

query = "Deploy nginx-test6 with 1 replica using image nginx"

print("Commande :", query)

result = agent.invoke({"messages": [{"role": "user", "content": query}]})

print("\nRésultat agent :")
print(result)