import os

DEPLOYMENT=os.environ.get("AZURE_OPENAI_DEPLOYMENT_NAME","MegaVoceroChatgpt4o")
ENDPOINT=os.environ.get("AZURE_OPENAI_ENDPOINT", "https://megavocero-chatgpt.openai.azure.com/")
API_KEY=os.environ.get("AZURE_OPENAI_API_KEY", "")
YOUTUBE_API_KEY=os.environ.get("YOUTUBE_API_KEY","")
GOOGLE_SPEECH_CLIENT=os.environ.get("GOOGLE_SPEECH_CLIENT","service_acc_speech_key.json")
GOOGLE_STORAGE_CLIENT=os.environ.get("GOOGLE_STORAGE_CLIENT","service_acc_storage_key.json")
TELEGRAM_BOT_KEY=os.environ.get("TELEGRAM_BOT_KEY","")
os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = GOOGLE_STORAGE_CLIENT