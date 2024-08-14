import logging

logging.basicConfig(level=logging.INFO, filemode='a', format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)