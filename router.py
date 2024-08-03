from fastapi import FastAPI,HTTPException
from fastapi.responses import JSONResponse
import uvicorn
import logging
import shutil
from megaVoceroTranslator import run
app = FastAPI(title="MegaVoceroApi")

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
    logging.info('Python HTTP trigger function processed a request.')

    try:
        response = await run()
        #clean_up_tmp_folder()
        return response
    except Exception as ex:
        logging.info(f"Error occured: \n{ex}")
        #clean_up_tmp_folder()
        return JSONResponse(status_code=500, content="Internal Error")
    
if __name__ == "__main__":
    logging.info("Starting API")
    uvicorn.run(app, host="0.0.0.0", port=8080)
