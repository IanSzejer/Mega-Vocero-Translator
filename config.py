import os

DEPLOYMENT=os.environ.get("AZURE_OPENAI_DEPLOYMENT_NAME","MegaVocero-chatgpt")
ENDPOINT=os.environ.get("AZURE_OPENAI_ENDPOINT", "https://megavocero-chatgpt.openai.azure.com/")
API_KEY=os.environ.get("AZURE_OPENAI_API_KEY", "")
SPEECH_KEY=os.environ.get("AZURE_SPEECH_KEY","")
SPEECH_REGION=os.environ.get("AZURE_SPEECH_REGION", "eastus")
YOUTUBE_API_KEY=os.environ.get("YOUTUBE_API_KEY","")
