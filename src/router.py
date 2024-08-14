from fastapi import FastAPI,HTTPException
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager
import uvicorn
import logging
import shutil
import pytz
import asyncio
from megaVoceroTranslator import run, send_message_to_telegram_channel
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
import time
from datetime import datetime
from logger import logger

argentina_tz = pytz.timezone('America/Argentina/Buenos_Aires')
video_found_today = False


def first_execution():
    logger.info("Se ejecuto call_endpoint")
    asyncio.run(main())

def second_execution():
    if video_found_today:
        return
    logger.info("Se ejecuto call_endpoint")
    asyncio.run(main())

def last_execution():
    global video_found_today
    if video_found_today:
        video_found_today = False
        return
    logger.info("Se ejecuto call_endpoint")
    asyncio.run(main())
    if not video_found_today:
        asyncio.run(send_message_to_telegram_channel(message="No hubo conferencia en el dia de la fecha"))
    else:
        video_found_today = False

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Se ejecuto lifespan")
    scheduler = BackgroundScheduler(timezone=argentina_tz)
    scheduler.add_job(first_execution, CronTrigger(hour=12, minute=0, day_of_week='mon-fri', timezone=argentina_tz))
    scheduler.add_job(second_execution, CronTrigger(hour=12, minute=30, day_of_week='mon-fri', timezone=argentina_tz))
    scheduler.add_job(last_execution, CronTrigger(hour=13, minute=0, day_of_week='mon-fri', timezone=argentina_tz))
    scheduler.start()
    yield
    scheduler.shutdown()

app = FastAPI(title="MegaVoceroApi", lifespan=lifespan)

def clean_up_tmp_folder():
    tmp_path = 'tmp'
    try:
        shutil.rmtree(tmp_path)
        logging.info(f"Successfully deleted {tmp_path}")
    except FileNotFoundError:
        logging.info(f"{tmp_path} does not exist")
    except Exception as e:
        logging.error(f"Error deleting {tmp_path}: {str(e)}")




@app.post('/megavocero/translate')
async def main() -> None:
    logger.info('Python HTTP trigger function processed a request.')

    try:
        response, completed = await run()
        global video_found_today
        video_found_today=completed
        clean_up_tmp_folder()
        return response
    except Exception as ex:
        logger.info(f"Error occured: \n{ex}")
        clean_up_tmp_folder()
        return JSONResponse(status_code=500, content="Internal Error")
    
if __name__ == "__main__":
    logger.info("Starting API")
    uvicorn.run(app, host="0.0.0.0", port=8000)
    
