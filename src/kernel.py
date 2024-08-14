import semantic_kernel as sk
from semantic_kernel.connectors.ai.open_ai import AzureChatCompletion
import os
import config as config

kernel=sk.Kernel()
service_id = "default"
kernel.add_service(
    AzureChatCompletion(
        service_id=service_id,
        deployment_name=config.DEPLOYMENT,
        endpoint=config.ENDPOINT,
        api_key=config.API_KEY,
        api_version="2024-04-01-preview"
    )
)

