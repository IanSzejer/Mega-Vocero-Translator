import os

DEPLOYMENT=os.environ.get("AZURE_OPENAI_DEPLOYMENT_NAME","MegaVocero-chatgpt")
ENDPOINT=os.environ.get("AZURE_OPENAI_ENDPOINT", "https://megavocero-chatgpt.openai.azure.com/")
API_KEY=os.environ.get("AZURE_OPENAI_API_KEY", "378b9a649cfd46e181db0701c204e615")
SPEECH_KEY=os.environ.get("AZURE_SPEECH_KEY","650c73019a3d4e238553038444844d96")
SPEECH_REGION=os.environ.get("AZURE_SPEECH_REGION", "eastus")
YOUTUBE_API_KEY=os.environ.get("YOUTUBE_API_KEY","AIzaSyBQVpwXah-uuQbOPpPGojQwFUDxkD1m7PY")