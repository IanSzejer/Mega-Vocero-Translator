from googleapiclient.discovery import build
from fastapi.responses import JSONResponse
from semantic_kernel.functions.kernel_arguments import KernelArguments
import azure.cognitiveservices.speech as speechsdk
from azure.cognitiveservices.speech import SpeechConfig, AudioConfig, SpeechRecognizer, ResultReason
import yt_dlp
import uuid
import logging
import os
import io
from time import sleep
import config as config
from kernel import kernel
from datetime import datetime, timezone

CHANNEL_ID = 'UCCSbOixo2xpZc_oToqeq2jQ'
PLAYLIST_ID = 'PLnpld8uKYZVpXU628alq6Ib5Ubi1rzRRa'
OUTPUT_FILE = "/tmp"
EXPECTED_AUDIO_ROUTE = "tmp\Conferencia.wav"

def get_latest_video_id(api_key: str, channel_id: str):
    youtube = build('youtube', 'v3', developerKey=api_key)
    
    # Realizar la petición para obtener los videos del canal
    request = youtube.search().list(
        part='snippet',
        channelId=channel_id,
        maxResults=5,
        order='date'
    )
    response = request.execute()

    for video in response.get('items',[]):
        logging.info(f"Video data: {video}\n")
        if "Conferencia de prensa" in video.get('snippet',{}).get('title',''):
            video_id = video['id']['videoId']
            publish_time = video['snippet']['publishedAt']
            return video_id, publish_time
    return None, None

def is_video_today(publish_time):
    video_date = datetime.fromisoformat(publish_time[:-1]).replace(tzinfo=timezone.utc)
    today_date = datetime.now(timezone.utc).date()
    return video_date.date() == today_date


def download_audio_from_video_v2(video_url, output_path):
    ffmpeg_path = os.path.join(os.getcwd(), 'bin', 'ffmpeg.exe')  # Ruta a ffmpeg
    ffprobe_path = os.path.join(os.getcwd(), 'bin', 'ffprobe.exe')  # Ruta a ffprobe
    ydl_opts = {
        'format': 'bestaudio/best',
        'outtmpl': f'{output_path}/%(title)s.%(ext)s',
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'wav',
            'preferredquality': '192',
        }],
        'ffmpeg_location': ffmpeg_path,
        'ffprobe_location': ffprobe_path
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info_dict = ydl.extract_info(video_url, download=True)
            audio_file = ydl.prepare_filename(info_dict).replace(".webm", ".wav")
    except Exception as ex:
        logging.info(f"Error with yt_dlp library, ex: {ex}")
        return None
     
    return audio_file

def transcribe_audio_to_text(input_audio_file,speech_key, service_region):
    # Crear una configuración de reconocimiento de voz
    speech_config = speechsdk.SpeechConfig(subscription=speech_key, region=service_region)
    speech_config.speech_recognition_language = 'es-AR'  # Configurar el idioma a español (Argentina)
    speech_config.set_property(speechsdk.PropertyId.Speech_LogFilename, "logs_SDK")  

    

    # Configurar la fuente de audio desde un buffer de memoria
    audio_input = speechsdk.audio.AudioConfig(filename=input_audio_file)

    # Crear un objeto de reconocimiento de voz
    speech_recognizer = speechsdk.SpeechRecognizer(speech_config=speech_config, audio_config=audio_input)

    done = False
    transcription = []


    def recognized_cb(evt):
        if evt.result.reason == ResultReason.RecognizedSpeech:
            logging.info('RECOGNIZED: {}'.format(evt.result.text))
            transcription.append(evt.result.text)
        elif evt.result.reason == ResultReason.NoMatch:
            logging.info('NOMATCH: Speech could not be recognized: {}'.format(evt.result.no_match_details))

    def canceled_cb(evt):
        logging.error('CANCELED: {} ({})'.format(evt.reason, evt.error_details))
        nonlocal done
        done = True

    def stop_cb(evt: speechsdk.SessionEventArgs):
        print(f'CLOSING on {evt}')
        nonlocal done
        done = True
        speech_recognizer.stop_continuous_recognition()

    # Connect callbacks to the events fired by the speech recognizer
    speech_recognizer.recognizing.connect(lambda evt: print('RECOGNIZING: {}'.format(evt)))
    speech_recognizer.recognized.connect(recognized_cb)
    speech_recognizer.session_started.connect(lambda evt: print('SESSION STARTED: {}'.format(evt)))
    speech_recognizer.session_stopped.connect(lambda evt: print('SESSION STOPPED {}'.format(evt)))
    speech_recognizer.canceled.connect(canceled_cb)
    # Stop continuous recognition on either session stopped or canceled events
    speech_recognizer.session_stopped.connect(stop_cb)
    speech_recognizer.canceled.connect(stop_cb)

    # Start continuous speech recognition
    speech_recognizer.start_continuous_recognition()
    while not done:
        sleep(.5)

    return ' '.join(transcription)
    # </SpeechContinuousRecognitionWithFile>


async def run():
    logging.info("Executin MegaVoeroTranlator function")
    #DESCOMENTAR ESTO DESPUES
    #latest_video_id, latest_video_publish_time = get_latest_video_id(api_key=config.YOUTUBE_API_KEY, channel_id=CHANNEL_ID)
    #logging.info(f"The video id is : {latest_video_id} and the publish_time is {latest_video_publish_time}")
    #if not latest_video_id or not is_video_today(latest_video_publish_time):
    #    return func.HttpResponse(
    #        "This HTTP triggered function failed. The last video in channel is not from today.",
    #        status_code=400)
    #latest_video_id = "4QGUNAKU7uM"     #HARDCODEO EL VIDEO ID POR PRUEBAS MAS CORTAS
    #audio_file = download_audio_from_video_v2(latest_video_id,OUTPUT_FILE)
    audio_file = 'tmp\\Cómo te puede cambiar la vida una tragedia - Ee cambiar la vida una tragedia - El Hormiguero.wav'
    if not audio_file:
        return JSONResponse(status_code=500, content="This HTTP triggered function failed. The last video in channel is not from today.")
    logging.info(f"The downloaded audio file is: {audio_file}")
    audio_transcription = transcribe_audio_to_text(input_audio_file=audio_file, speech_key=config.SPEECH_KEY, service_region=config.SPEECH_REGION)
    logging.info(f"Transcription length is {len(audio_transcription)}")

    textToNarrationPlugin = kernel.import_plugin_from_prompt_directory("./plugins", "SummerizeConference")
    arguments = KernelArguments()  
    arguments["conferencia"] = audio_transcription  
    summarization = kernel.invoke(textToNarrationPlugin["Summerization"],arguments)
    logging.info(f"Summarization result : {str(summarization)}")
        
