# Usar la imagen oficial de Python como base
FROM python:3.10-slim

# Establecer el directorio de trabajo en el contenedor
WORKDIR /app

# Copiar el archivo requirements.txt en el directorio de trabajo
COPY requirements.txt .

# Instalar las dependencias
RUN pip install --no-cache-dir -r requirements.txt

# Copiar todo el contenido del proyecto en el directorio de trabajo
COPY . .

# Establecer las variables de entorno
ENV AZURE_OPENAI_DEPLOYMENT_NAME=MegaVoceroChatgpt4o
ENV AZURE_OPENAI_ENDPOINT=https://megavocero-chatgpt.openai.azure.com/
ENV AZURE_OPENAI_API_KEY=378b9a649cfd46e181db0701c204e615
ENV YOUTUBE_API_KEY=AIzaSyBQVpwXah-uuQbOPpPGojQwFUDxkD1m7PY
ENV GOOGLE_SPEECH_CLIENT=service_acc_speech_key.json
ENV GOOGLE_STORAGE_CLIENT=service_acc_storage_key.json
ENV TELEGRAM_BOT_KEY=7310246126:AAHzuADFSrNaG_huUN-VZ6W_b2XCtkovnSE

# Exponer el puerto que usará la aplicación
EXPOSE 8000

# Comando para ejecutar la aplicación
CMD ["python3.10","router.py"]