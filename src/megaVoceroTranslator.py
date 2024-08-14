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
import requests
import asyncio
import time
import subprocess
import soundfile as sf
import numpy as np
from pydub import AudioSegment
from google.oauth2 import service_account
from google.cloud import speech, storage
from time import sleep
import config as config
from kernel import kernel
from datetime import datetime, timezone
from logger import logger

CHANNEL_ID = 'UCCSbOixo2xpZc_oToqeq2jQ'
PLAYLIST_ID = 'PLnpld8uKYZVpXU628alq6Ib5Ubi1rzRRa'
OUTPUT_FILE = "/tmp"
FINAL_AUDIO_FILE = "/tmp/final_audio.wav"
EXPECTED_AUDIO_ROUTE = "tmp\Conferencia.wav"
CLIENT_FILE = config.GOOGLE_SPEECH_CLIENT

GS_URI = "gs://conferencias_vocero/audio_conferencia"


storage_client = storage.Client()

def get_latest_video_id(api_key: str, channel_id: str):
    youtube = build('youtube', 'v3', developerKey=api_key)
    
    # Realizar la petición para obtener los videos del canal
    request = youtube.search().list(
        part='snippet',
        channelId=channel_id,
        maxResults=10,
        order='date'
    )
    response = request.execute()

    for video in response.get('items',[]):
        logger.info(f"Video data: {video}\n")
        if "Conferencia de prensa" in video.get('snippet',{}).get('title',''):
            video_id = video['id']['videoId']
            publish_time = video['snippet']['publishedAt']
            return video_id, publish_time
    return None, None

def is_video_today(publish_time):
    video_date = datetime.fromisoformat(publish_time[:-1]).replace(tzinfo=timezone.utc)
    today_date = datetime.now(timezone.utc).date()
    return video_date.date() == today_date


def download_audio_from_video_v2(video_url, output_path, final_audio_file):
    ffmpeg_path = os.path.join(os.getcwd(), 'bin', 'ffmpeg')  # Ruta a ffmpeg
    ffprobe_path = os.path.join(os.getcwd(), 'bin', 'ffprobe')  # Ruta a ffprobe
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
            #asyncio.sleep(1)
            #Paso el audio a mono
            command = [ffmpeg_path, '-i', audio_file, '-ac', '1', final_audio_file]
            subprocess.run(command, check=True)


    except Exception as ex:
        logger.info(f"Error with yt_dlp library, ex: {ex}")
        return None
     
    return final_audio_file


async def upload_file_to_google(blob_name,file_path,bucket_name):
    try:
        bucket = storage_client.get_bucket(bucket_name)
        blob = bucket.blob(blob_name)
        logger.info(f"Blob is: {blob}")
        blob.upload_from_filename(filename=file_path)
        return True
    except Exception as ex:
        logger.info(f"Couldnt access google storage, ex: {ex}")
        return False


async def transcribe_audio_to_text_google(file_uri):
    clien_file = CLIENT_FILE
    credential = service_account.Credentials.from_service_account_file(clien_file)
    client = speech.SpeechClient(credentials=credential)
    gcs_uri = 'URI'
    config = speech.RecognitionConfig(
        encoding=speech.RecognitionConfig.AudioEncoding.LINEAR16,
        language_code='es-AR' 
    )
    audio = speech.RecognitionAudio(uri=file_uri)
    operation = client.long_running_recognize(config=config,audio=audio)

    logger.info("Starting traduction")
    response = operation.result()
    final_traduction = []
    for result in response.results:
        final_traduction.append(result.alternatives[0].transcript)
    return ' '.join(final_traduction)
    

async def get_telegram_groups_ids():
    url = f"https://api.telegram.org/bot{config.TELEGRAM_BOT_KEY}/getUpdates"
    response = requests.get(url)
    updates = response.json()
    #logger.info(f"Update response: {updates}")
    groups_id_set = set()
    for update in updates['result']:
        chat = update.get("message",{}).get("chat",None)
        if chat:
            groups_id_set.add(chat.get("id",""))
    return groups_id_set


def split_message_for_telegram(text, max_length=4080):
    result = []
    while len(text) > max_length:
        # Encontrar el último \n antes de max_length
        split_point = text.rfind('\n', 0, max_length)
        if split_point == -1:
            # Si no hay \n, dividir en el max_length
            split_point = max_length
        # Agregar el segmento al resultado
        result.append(text[:split_point])
        # Reducir el texto restante
        text = text[split_point:]
        # Eliminar el \n inicial si existe
        if text.startswith('\n'):
            text = text[1:]
        logger.info(f"Remaining text is: {text}")
    # Agregar el texto restante
    result.append(text)
    return result


def split_message_for_telegram_v2(text, separator="---------------------------------------"):
    # Dividir el mensaje por el separador
    parts = text.split(separator)
    # Eliminar espacios en blanco al principio y al final de cada parte
    parts = [part.strip().replace('-', '') for part in parts if part.strip()]
    return parts

async def send_message_to_telegram_groups(chat_id: str, message: str):
    url = f"https://api.telegram.org/bot{config.TELEGRAM_BOT_KEY}/sendMessage"
    message_list = split_message_for_telegram(text=message)
    for message in message_list:
        payload = {
            'chat_id': chat_id,
            'text': message,
            'parse_mode': 'HTML'
        }
        response = requests.post(url, data=payload)
        logger.info(f"Api post response: {response.json()}")


async def send_message_to_telegram_channel(message: str):
    url = f"https://api.telegram.org/bot{config.TELEGRAM_BOT_KEY}/sendMessage"
    message_list = split_message_for_telegram_v2(text=message)
    channel_id = "-1002221722110"
    for message in message_list:
        payload = {
            'chat_id': channel_id,
            'text': message,
            'parse_mode': 'HTML'
        }
        response = requests.post(url, data=payload)
        logger.info(f"Api post response: {response.json()}")

async def run():
    logger.info("Executin MegaVoeroTranlator function")
    latest_video_id, latest_video_publish_time = get_latest_video_id(api_key=config.YOUTUBE_API_KEY, channel_id=CHANNEL_ID)
    logger.info(f"The video id is : {latest_video_id} and the publish_time is {latest_video_publish_time}")
    if not latest_video_id or not is_video_today(latest_video_publish_time):
        return JSONResponse(status_code=500, content="This HTTP triggered function failed. The last video in channel is not from today."), False

    #latest_video_id = "4QGUNAKU7uM"     #HARDCODEO EL VIDEO ID POR PRUEBAS MAS CORTAS
    audio_file = download_audio_from_video_v2(latest_video_id,OUTPUT_FILE,FINAL_AUDIO_FILE)
    #audio_file = os.path.join('D:\Proyectos\Manu\Mega-Vocero-Adorni-Api-V\\tmp','audio_prueba.wav') 
    if not audio_file:
        return JSONResponse(status_code=500, content="This HTTP triggered function failed. The last video could not be downloaded."), False
    logger.info(f"The downloaded audio file is: {audio_file}")
    logger.info("Uploading file to google storage")
    if not await upload_file_to_google(blob_name="audio_conferencia",file_path=audio_file,bucket_name="conferencias_vocero"):
        return JSONResponse(status_code=500, content="This HTTP triggered function failed. The audio could not be upload to google."), False

    logger.info("Transcribing with google")
    
    text_traduction = await transcribe_audio_to_text_google(GS_URI)
    if not text_traduction:
        return JSONResponse(status_code=500, content="This HTTP triggered function failed. The audio could not be translated."), False
    logger.info(f"The text traduction is: {text_traduction}")
    
    textToNarrationPlugin = kernel.import_plugin_from_prompt_directory("./plugins", "SummerizeConference")
    arguments = KernelArguments()  
    arguments["conferencia"] = text_traduction  
    summarization = await kernel.invoke(textToNarrationPlugin["Summerization"],arguments)
    logger.info(f"Summarization result : {str(summarization)}")
    await send_message_to_telegram_channel(message=str(summarization))

    logger.info(f"Se ejecuto la funcion!")
    return JSONResponse(status_code=200, content="This HTTP triggered function was executed correctly."),True
    

#group_ids = await get_telegram_groups_ids()
    #for group_id in group_ids:
    #    logger.info(f"Telegram post response: {str(await send_message_to_telegram_groups(group_id,str(summarization)))}")    
    


"""Buen día vas a encontrar más de 400 capacitaciones propias y en Alianza con actores privados de reconocida trayectoria si quiere competir capacitante más info en argentina.gob.ar barra capacitar  Pero bueno bueno ahora sí Buen día recuerden silenciar los teléfonos celulares gracias hola hola hola  bueno Buen día a todos buen viernes en primer lugar contarles que el banco nación otorgado créditos por 1.6 billones de pesos a familias micro pequeñas medianas y grandes empresas durante Julio lo que representa 743% de aumento con respecto al mismo mes o sea el mismo Julio de 2023 cuando Sergio mazaira ministro de economía los datos desagregados reflejan que 1.3 billones de pesos 
                        se destinarán a financiar inversiones y capital de trabajo para empresas de todo el país mientras que otros 300,00 iones de peso se destinan a préstamos personales para familias argentinas Por supuesto que para nosotros el crédito es símbolo de Progreso e incluso las naciones más prósperas efectivamente lo que hacen es fomentar el acceso al crédito y Argentina por suerte se ha sumado a esta  Ahí está tendencia en otro orden de cosas contarles a todos los jubilados pensionados titulares de asignaciones que paga anses que a partir de hoy van a poder elegir libremente En dónde cobrar sus 
                        haberes el trámite para revisar Este cambio se puede hacer online a través de la aplicación bueno de la web del organismo etcétera como también lo pueden hacer de manera de manera presencial pero no es necesario que se acerquen personalmente a las oficinas de anses bueno el cambio se va a ser efectivo a partir de los 60 días los temas administrativos que por supuesto están todos informados en la página por otro comentarles que en el primer 
                        semestre del año la producción de gas en Argentina fue la más alta en los últimos 17 años y representa un 5 coma 2% respecto al mismo periodo del año del año pasado la  son de petróleo también marco un nuevo récord siendo la más alta de los últimos 15 años con un aumento del 8.2% interanual después de años de abandono el sector energético de Argentina volvió al camino del desarrollo y como siempre hago cuando hablo de energía Le agradezco no solo a todo el equipo económico sino también a parte también del equipo por supuesto señor Cirilo que ha hecho tamaño tamaño trabajo para que esto para que esto así así ocurra Bueno listo por mi parte los escucho Tati argentino el presidente Mauricio expresidente Mauricio macri sostuvo que se 
                        le puede decir presidenta sí o no hay problema con cuarzo el pro y sostuvo que el presidente Javier milei sigue teniendo pendiente armar  conformar 
                        un equipo de gestión de gobierno además sostuvo que fue un desafío ayudar a que no está dispuesto a ser ayudado y dijo que el propuso colaborar con 
                        el gobierno a pesar de su entorno le quería consultar Cómo reciben por parte del gobierno está apreciación por parte del expresidente Incluso si teniendo en cuenta de que se reunieron el lunes el ex presidente Mauricio macri les adelanto o le adelanto al presidente este está visión que tiene el 
                        sobre su gestión Gracias bueno con respecto a lo que dijo el presidente ayer lo cierto es que el ocio el camino que ha tomado el presidente milei Así que estamos profundamente agradecidos y con respecto a las definiciones sobre el equipo no somos orgullosos del equipo que el paciente está orgulloso del equipo que tiene y todos los que lo conformamos estamos orgullosos de trabajar en el presidente y consideramos que somos un equipo no solo sólido sino que además hemos logrado grandes hitos sendas  poquito tiempo la baja de la inflación que conllevó el que se haya evitado la hiperinflación ni hablar temas de inseguridad o de narcotráfico Cómo ocurre Pero qué ocurría una manera absolutamente descontrolada en Rosario y tantas otras cosas que fuimos corrigiendo que van desde el orden público Está bueno un relanzamiento de crédito empezamos a ver que la actividad empieza a tomar un curso que todos deseamos Qué es el decrecimiento bueno la verdad que estamos el presidente está orgulloso del equipo y somos un equipo demás que que se destaca por no solo por su capacidad de trabajo por los resultados Pero además por su solidez y por lo bien que nos llevamos entre nosotros así que no hay mucho más para decir que eso y cree que es la crítica por la falta de conformación de equipos responde a la falta de agentes o dirigentes del Pro dentro de las primeras filas de LOL  batalla de Patricia bullrich y Luis petri que yo sabemos que forman parte pero otros equipos académicos No lo sé se lo tendría que preguntar a él nosotros pero de todas maneras nombraste como algo menor lo de Patricia lo de la doctora bullrich doctor petri y son dos ministerios de mucha relevancia Además de que nosotros tenemos un equipo de un cabinete de pocos ministerios Así que efectivamente el resto de lo que te genere dudas de lo que haya dicho más Grisel o vas a tener que preguntar  Voceros cómo le va Buen día como Rodríguez Jorge de radio mitre Muy bien gracias Me alegro mucho algunos aspectos si puede puntualizar respecto de la temática macri digo entiendo la importancia de un Aliado como el ex presidente macri específicamente lo que dijo el relanzamiento del Pro y también a la noche en una nota periodística sobre aspectos centrales del gobierno dijo macri hay gente de masa y la cámpora lugares centrales del gobierno si usted puede especificar En qué áreas todavía el gobierno de Javier milei tiene gente de la cámpora y si es así sí ratifica a ese personal o si lo piensan desplazar y segundo tema que no es menor 
                        Qué es la candidatura de Ariel hijo como miembro de la Corte Suprema macri lo calificó como un error y ratifican ustedes la nominación y en general 
                        como toma la declaración de macri la tomas como un halago como un elogio reciente dijo un elogio pero en realidad se escucharon muchas críticas no al rumbo económico pero si en la conformación de equipo dentro del gobierno gracias  bueno la última pregunta va en línea con lo que pregunto con lo 
                        que pregunto tarde y recién no me parece que efectivamente lo de los equipos o la opinión que tiene macri sobre los equipos hay que mandársela él él Porque hizo odiosa definición y efectivamente para nosotros como elogio al presidente mira y ayer la verdad es que nos dio mucho mucho placer y mucho mucho gusto pero pero no está se lo tienen que preguntar al ex presidente macri yo no tengo para no hablo por él No no tengo nada para decir de lo que de lo que él puede llegar a pensar incluso con respecto a los equipos amasa a quien sea a la cámpora O quién sea nosotros estamos por supuesto que hace 8 meses de que asumimos por supuesto que hay un montón de lugares que unos que siguen en evaluación los mismos empleados públicos el famoso universo empleados que se sigue evaluando trimestralmente Y por supuesto que hay cargos que se siguen que se siguen en revisión y nosotros el presidente lo dijo  nosotros no nos encerramos en nosotros mismos sino que efectivamente si hay gente que es que tiene determinados valores actitudes o 
                        expertis no tienen porque no formar parte la hora que alguien se refería no lo no lo sé pero se lo tiene que preguntar a el eso de la como dice Mauricio macri gente de la cámpora de No pregúntaselo a él eso no no no está en el gobierno Bueno entonces no sé dónde tendrá el dato no no no lo sé pregúntaselo a él porque A quién a quién hizo referencia no a nosotros no nos consta que eso sea así Y sí efectivamente hay gente de gestiones anteriores ser agente o que tiene el expertis para estar o qué llegado el llegado el momento de la de que de que llegue mosa estaríamos a evaluar ese perfil y no coincida con nosotros pretendemos efectivamente será reemplazado hijo pero esto fue siempre así desde el 10 de diciembre que estés así por eso me sorprende mucho  la pregunta de amor no no porque esté mal hecha ni mucho menos sino porque efectivamente este es la metodología de trabajo persona que sirve se queda persona que no sirve se va el hijo es una opinión del ex presidente macri está muy bien y nosotros no no no calificamos la opinión del ingeniero macri nos parece muy bien y te repito nosotros al revés no está sumado mucho valor que el expresidente nos haya elogiado cómo nos elogio Bueno me sume al tren no pero como elogio al presidente Emily por lo que por lo que venimos haciendo y por el cambio que estamos llevando adelante una opinión del presidente macri Manuel qué tal Silvia mercado radiojai Cómo andás ando muy bien Pero cuánto me alegro vos yo ando bárbaro eres mi mejor momento me doy cuenta la canciller hace  minutos posteo un tweet donde dice que está en condiciones de confirmar Sin lugar a ninguna duda que legítimo ganador y presidente electo es Edmundo González Aquí hay una posición firme podríamos decir ya sin vueltas en relación a Venezuela y a la situación de las últimas elecciones en Venezuela Quisiera saber al respecto si esto está conversado con los otros países de la región y qué expectativas hay entonces para la resolución de los problemas gravísimos en Venezuela porque el dictador Nicolás Maduro no quiere entregar el poder  van hacer para que esto que afirma el gobierno argentino sede en la práctica Gracias o cómo se va a resolver Por supuesto que es difícil saber lo difícil hacer futurología ante la presencia de un dictador muy difícil entender que es lo que ver sucediendo a partir de lo obvio que es que efectivamente El dictador maduro perdió las elecciones y que nunca aparecieron las actas famosas donde él iba a demostrar que había ganado por el algo más del 51% de los votos no hay mucho más para para decir con respecto a eso entendemos que la comunidad internacional en su mayoría se va a ir pegando a aceptar que efectivamente ha sido todo un gran fraude y el dictador maduro tiene que correr se El Poder y dar paso de una buena vez a las acciones  épicas ya no que todos sabemos y entendemos que quiere poner venezolano Qué es vivir en paz y por sobre todas las cosas también en democracia Cuál era la otra pregunta Perdóname si hubo coordinación con otros países de la región para que ahora definitivamente la Argentina diga el ganador ha sido 
                        Edmundo González Urrutia para reconocer para reconocer esto no hace falta ningún tipo de coordinación  no existe pidal Manuel muy buenos días Miguel Muy bien hecho comentarios dentro de su equipo de trabajo el presidente Javier milei sobre esta decisión del gobierno de Finalmente consagrar la fórmula opositora ganadora en Venezuela algún tipo de comentarios que pueda hacerte atender mañana llega a los representantes argentinos y diplomáticos a nuestro país serán recibidos por la canciller Diana mondino serán recibidos también por el presidente Javier milei existe la posibilidad de ponerlos a disposición de la prensa El próximo lunes para que salen con nosotros sobre los momentos vividos son están las inquietudes que dejó bueno primeramente Dios llegan el sábado y por supuesto que lo es en un horario determinado que han pedido o han acordado con cancillería no divulgar lo simplemente por un tema de  de seguridad y de qué de Bueno hay que le llega al país era lo más tranquila posible lo de la prensa la verdad es que será una decisión que tomara que tomarán ellos acompañado seguramente por la canciller mondino no te lo puedo contestar eso porque realmente no lo sé sé definirá seguramente No lo sé porque no está definido de definidad seguramente al regreso y y después de que Diana mondino de primera mano y en persona se entere de los detalles y de todos los últimos acontecimientos ocurridos y con respecto a la elección que me habías preguntado algo de Julio Discúlpame sí está bien me late me late hay tus comentarios que sobró en los comentarios bueno Fueron por supuesto Siempre durante toda la durante estos últimos días desde Buenos Aires tuvo por supuesto con todo juntos el día martes en gabinete la posición siempre fue muy clara de todo no es un dictador falsificando datos electorales de una manera extrema  Amén de vida en de porque ese es increíble que hasta hayan sido tan burro sean tan ineficientes hasta para truchar datos de una manera tan obvia que inmediatamente uno se daba cuenta que algo raro pasaba Y después el tiempo confirmo que festivamente lo que decía El dictador maduro no tenía ningún sustento ningún formalismo ni ninguna ninguna documentación que avale la lo que estaba diciendo Así que la posición ha sido siempre muy clara la hemos conversado como el contado acá en mismo martes en gabinete y la posición el presidente siempre fue la misma y opino y siempre opinamos que maduro era simplemente un dictador  qué tal Manuel Cómo estás Muy bien bueno me alegro que 
                        Toñito de vos vinimos con como color comunista comunista por un lado contra la envidia por otro Eso es un tema que corre por vos yo no te envío bueno volviendo con el tema del doctor el hijo después de lo que dijo macri  y en virtud de la cantidad de senadores que tiene la libertad avanza libertad esto significa que van a tener que conversar con la gente de Unión por la patria está contemplado eso han iniciado conversaciones sino no dan los números Félix Primero deja déjame repetir algo las declaraciones del ex presidente macri corren por cuenta del ex presidente macri la palabra del presidente macri del ex presidente macri no interfieren en en nada en medio milímetro en la acción de gobierno y el trámite legislativo siempre son complicados para una fuerza que entres o que tiene 38 diputados y 7 senadores todo lo demás queda a criterio del poder legislativo y tendrán que debatirlo discutirlo en tal caso el  te propone y el congreso dispone no hay mucho más para no hagan un mundo de algo que no que no que no lo amerita y 
                        respecto del doctor García mansilla Ustedes han conversado ya con el con el doctor maqueda que tendría que dejar el cargo En diciembre es un tema ajeno a nosotros y que tiene que resolver casi se nos mata un fotógrafo es un tema que repito el presidente propone y los propios procesos y lo el resto de los poderes después dispondrá no Ay no no no vamos Repito no damos un mundo de algo que no no lo amerita  qué tal Vocero el otro día leí en su Twitter vulturi quesito textualmente muchas veces puede ocurrir que se elige a través del voto el comienzo Un gobierno comunista lo que rara vez ocurre es que a través del voto se logre que dejen de hacerlo si era el Día de las elecciones en Venezuela donde ya conocíamos que había un fraude está claro que hay muchas personas que cada mes se preguntan que si la diplomacia internacional no sirve para acabar como un régimen como el de Maduro 
                        que se podría sugerir una intervención militar de Chuy al presidente del Salvador ya criticado duramente a la olla por dar impunidad los criminales 
                        y está sugiriendo no sabía me gustaría preguntarle cuál es la solución para acabar con maduro en el caso de que la vía diplomática al control a ellos todos los resortes ya no entender de las normas internacionales cuál sería si ustedes apoyarían una intervención militar para proteger a la víctima sea su representado a los disidentes y esa persona  qué tal siendo secuestrada por el simple hecho de haber sido testigo de una mesa electoral y también me gustaría preguntarle cómo padre y también como representante del gobierno que sintió cuando ayer el gobernador de Buenos Aires kiciloff uso un jardín de infancia para delante de bebés arengar y adoctrinar contra Javier milei hacer política algo que en Europa está prohibido que no estamos acostumbrado Y sí tendrían previsto dentro de la ley de Educación prohibir ese tipo de actos sobre todo en guardería donde lo menor de edad no tienen culpa Ni deben estar creo aprendiendo de políticas reto cuando tienen 3 4 años no muchas gracias por haberme barranco por el final la verdad es que yo la verdad que el video no lo viví algún comentario que si son las redes con respecto a ese supuesto adoctrinamiento bueno cada uno sabrá lo 
                        que hace porque lo hace la verdad es que no es la arengar niños en el caso de que haya ocurrido en la verdad es que  es algo nefasto es pero bueno el el gobernador kiciloff está claro que está está perdido ya montadas y un camino que nosotros no compartimos y y tal vez lo que ocurre es que empezó a leer que la gente que lo que pasó porque el problema es que hay un sector de la oposición creo que kiciloff tal vez pertenezca ese grupo de oposición que no termina de entender que es lo que pasó en las elecciones del año pasado y mucho peor aún no entiende qué es lo que la gente desea y necesita de la Argentina y bueno en esa confusión tal vez cometió el repito así fue así porque no lo vi siempre hago está aclaración cuando no no ve un video tal vez en esa gran confusión cometió el error de involucrar política en un acto donde donde prevalecía prevalecían los niños y no me lo sé otro que no debe pasar esas cosas no no no no pueden pasar  y ojalá que que no se repitan los gobernantes se tienen que dedicar a gobernar y a tratar de que cuando uno se vaya del poder las cosas estén mejorando un ingreso al por ahí por mejorar un poco la realidad la gente y me parece que este tipo de actos no colabora con que la gente esté mejor no hacer política con niños la verdad es que no es no es algo que no no no es algo que uno puede hablar y con respecto al tema el tema Venezuela Bueno es un tema extremadamente sensible nosotros no vamos a hacer absolutamente ninguna declaración con respecto a lo que puedo pasar el futuro de Venezuela si lo que podemos transmitir lo que decíamos no en el mundo no puede existir un dictador gobernando un pueblo eso no puede ocurrir Y lamentablemente es lo que ocurre menos de hace mucho tiempo no ahora hubo una nueva elección fraudulenta predigo el chavín  hace bastantes años que viene destruyendo a Venezuela para que no lo sabe el chavismo expulsado a millones de venezolanos De su tierra y empobrecido al 90% de su población entonces Y además es un gobierno dictatorial que hoy el pueblo venezolano decidió rechazarlo y el dictador maduro tiene que hacerse un lado después Cómo se desenvuelvan los hechos Que decida el pueblo venezolano como como la historia castigue a castigar maduro bueno ser un tema que no no no Hoy no podemos hacer absolutamente ninguna precisión y ninguna ninguna declaración última pregunta Buen día Manuel Cómo andás lautaro spadavecchia para la universidad fasta Hola Perdóname Hoy no vino de la universidad  pasta de mar del plata Así que andabas por acá andaba por acá en acreditaron Sí así que aprovechamos para que pidió Solicito venir Así que no hemos invitado a que en representación de 
                        la universidad por supuesto de mar del plata pueda puede estar aquí en pasta en la universidad fasta Así es Muchas gracias por favor bueno como soy 
                        a mar del plata quería preguntarle por dos Pilares de mar del plata que toca nación cómo son la seguridad y el turismo voy a empezar por la pregunta de turismo quería consultarle en las vacaciones de invierno se vio una caída en el turismo del 3,3 porciento respecto al año pasado quería preguntarle cómo plantea el gobierno el verano si va a dar algún incentivo si crees que los números van a ser superadores respecto años anteriores Y respecto a seguridad Qué es responsabilidad de la provincia de Buenos Aires la ministra bullrich En 2019 envío 500 gendarmes que fueron retirados por el ex presidente Alberto Fernández Ni bien asumió el  2 milésimos en diciembre se habló de que ella lo prometió en campaña que si era presidente iban a volver esos 500 gendarmes a la ciudad porque ella vio que realmente era un apoyo necesario la ciudad por la cantidad de gente que tiene Y tal vez por los pocos recursos de la policía provincial o la falta de intención de actuar No lo sé así que quería saber si se van en llenar mes para el turismo en nuestra secretaría de turismo bueno deportes y turismo lo que hace en tal caso es que el sector privado incentivar de manera digamos promocional A qué efectiva mente los argentinos visitemos la Argentina no recordamos la Argentina Cómo se ha hecho incluso para las vacaciones de invierno Pero no entiendo qué te referís algún esquema de previaje digamos estado estos esquemas que había en el pasado  No no va a pasar en general cualquier tipo de acción del gobierno que promueve el turismo y promover el turismo secretaría a la secretaría de turismo con respecto a la seguridad vos hablás de mar del plata pero yo te hablo a lo largo y a lo ancho del país y más hay que efectivamente no es nuestra juridicción y que la seguridad es responsabilidad efectivamente de cada una de las jurisdicciones las 23 provincias y la ciudad Autónoma de Buenos Aires la doctora bullrich el Ministerio de seguridad que comanda por supuesto que está disposición de donde se requiera seguridad y cionar brindar el apoyo de las fuerzas federales que sean necesarios el caso que me planteas sí efectivamente el gobernador kiciloff solicita refuerzos efectivamente cómo hacemos siempre o cómo hace siempre la doctora bullrich Lo valora y si lo considera necesario así ocurrida digo pero eso pasa Te repito en todas las jurisdicciones donde  se retiran a fuerzas adicionales Y si en vez del gobernador kiciloff fuera el intendente Montenegro que lo solicitó porque realmente hubo una reunión en los 
                        personajes de un par de meses que se reunió con Patricia bullrich le planteó la necesidad de los gendarmes y no llegaron de hecho había trascendido 
                        en el mar del plata que se estaba hablando de que iban a llegar y no no Arriba no no bueno eso puntualmente de eso que me comentas no tengo no tengo información y aún no me consta Pero en tal caso Bueno ahí ahí hay algo que no me no me no me no me termina de cerrar en lo que me decís que que efectivamente porque no se lo solicita al gobernador kiciloff que quién es responsable de la policía de la provincia Buenos Aires no habría que habría 
                        que ver bien qué es lo que me estás planteando con esa con ese pedido no no yo no digo que no lo haya solicitado kiciloff que tengo entendido que no fue así sino que si lo solicitó Montenegro y los persona de prensa de que habló con la ministra bullrich ela  puntajes si lo solicita el intendente y no el gobernador se pueden enviar reconozco reconozco los pormenores jurídicos pero pero salimos con nosotros A ver una doctora bullrich y después la nadie tiene tu contacto informamos buena pero muy buena pregunta se termina el fin de semana"""

""" ### RESUMEN DEL DISCURSO INICIAL:
Manuel Adorni, vocero presidencial, comenzó la conferencia destacando varios logros del gobierno. Mencionó que el Banco Nación otorgó créditos por 1.6 billones de pesos en julio, un aumento del 743% respecto al mismo mes del año anterior. De estos, 1.3 billones se destinaron a inversiones y capital de trabajo para empresas, y 300 mil millones a préstamos personales para familias. También anunció que los jubilados y pensionados podrán elegir libremente dónde cobrar sus haberes, trámite que puede realizarse online o presencialmente. Además, resaltó que la producción de gas en Argentina alcanzó su nivel más alto en 17 años y la producción de petróleo fue la más alta en 15 años. Agradeció al equipo económico y al señor Cirilo por su trabajo en el sector energético.

### PREGUNTAS Y RESPUESTAS:

**Pregunta de Tati Argentino:**
- **Pregunta:** El expresidente Mauricio Macri sostuvo que el presidente Javier Milei sigue teniendo pendiente armar un equipo de gestión de gobierno. ¿Cómo reciben esta apreciación por parte del gobierno?
- **Resumen de la respuesta:** Adorni expresó que el presidente Milei está orgulloso de su equipo, destacando logros como la baja de la inflación y 
mejoras en seguridad. Afirmó que el equipo es sólido y trabaja bien en conjunto. Sobre la crítica de Macri, sugirió que se le pregunte directamente 
a él.

**Repregunta de Tati Argentino:**
- **Pregunta:** ¿Cree que la crítica por la falta de conformación de equipos responde a la falta de agentes del Pro dentro del gobierno?
- **Resumen de la respuesta:** Adorni mencionó que Patricia Bullrich y Luis Petri son parte del equipo y tienen roles relevantes. Reiteró que cualquier duda sobre las declaraciones de Macri debería ser dirigida a él.

**Pregunta de Jorge Rodríguez (Radio Mitre):**
- **Pregunta:** Macri mencionó que hay gente de Massa y La Cámpora en lugares centrales del gobierno. ¿Puede especificar en qué áreas y si piensan desplazar a ese personal? Además, ¿ratifican la nominación de Ariel Hijo a la Corte Suprema?
- **Resumen de la respuesta:** Adorni indicó que cualquier opinión sobre los equipos debe ser dirigida a Macri. Afirmó que el gobierno sigue evaluando a los empleados públicos y que aquellos que no cumplan con los estándares serán reemplazados. Sobre Ariel Hijo, reiteró que la opinión de Macri es personal y no interfiere en las decisiones del gobierno.

**Pregunta de Silvia Mercado (Radio Jai):**
- **Pregunta:** La canciller confirmó que Edmundo González es el legítimo ganador y presidente electo de Venezuela. ¿Qué expectativas tienen para la resolución de los problemas en Venezuela?
- **Resumen de la respuesta:** Adorni afirmó que es difícil prever el futuro bajo un dictador como Maduro. Espera que la comunidad internacional reconozca el fraude y que Maduro ceda el poder. No se necesita coordinación con otros países para reconocer a González como ganador.

**Pregunta de Miguel Pidal:**
- **Pregunta:** ¿Hubo comentarios dentro del equipo de trabajo del presidente Milei sobre la decisión de consagrar la fórmula opositora ganadora en 
Venezuela?
- **Resumen de la respuesta:** Adorni mencionó que siempre han tenido una posición clara sobre Maduro, considerándolo un dictador. Afirmó que la falsificación de datos electorales fue evidente y que la posición del presidente siempre ha sido la misma.

**Pregunta de Toñito:**
- **Pregunta:** ¿Apoyarían una intervención militar en Venezuela para proteger a las víctimas del régimen de Maduro? Además, ¿qué opinan sobre el uso de un jardín de infancia para hacer política en Buenos Aires?
- **Resumen de la respuesta:** Adorni calificó de nefasto el supuesto adoctrinamiento en el jardín de infancia y criticó a Kiciloff por no entender 
las necesidades de la gente. Sobre Venezuela, afirmó que no harán declaraciones sobre una posible intervención militar, pero reiteró que Maduro es un dictador que debe ceder el poder.

**Pregunta de Lautaro Spadavecchia (Universidad FASTA):**
- **Pregunta:** ¿Cómo plantea el gobierno el verano en términos de turismo y seguridad en Mar del Plata?
- **Resumen de la respuesta:** Adorni mencionó que la Secretaría de Turismo promoverá el turismo interno, pero no habrá esquemas como el Previaje. Sobre la seguridad, afirmó que es responsabilidad de cada jurisdicción, pero que el Ministerio de Seguridad está dispuesto a brindar apoyo donde sea 
necesario.

"""