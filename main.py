import logging
import socket

from server import Server
from config import *

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format='(%(asctime)s) [%(name)s]:[%(levelname)s] %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S',
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler("server.log", encoding="utf-8")
        ]
    )

    logger = logging.getLogger(__name__)
    logger.info(f"Music directory: {SERVER_MUSIC_DIRECTORY}")
    socket.setdefaulttimeout(5)
    server = Server()

    try:
        server.run()
    except KeyboardInterrupt:
        logger.info("Shutting down.")