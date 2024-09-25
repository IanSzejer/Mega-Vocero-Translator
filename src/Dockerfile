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
ENV AZURE_OPENAI_DEPLOYMENT_NAME=
ENV AZURE_OPENAI_ENDPOINT=
ENV AZURE_OPENAI_API_KEY=
ENV YOUTUBE_API_KEY=
ENV GOOGLE_SPEECH_CLIENT=service_acc_speech_key.json
ENV GOOGLE_STORAGE_CLIENT=service_acc_storage_key.json
ENV TELEGRAM_BOT_KEY=

# Exponer el puerto que usará la aplicación
EXPOSE 8000

# Comando para ejecutar la aplicación
CMD ["python3.10","router.py"]