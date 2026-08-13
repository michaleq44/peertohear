import logging

from server import Server
from datafetcher import *

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
    server = Server()
    print(server.fetcher.id_to_tags[server.fetcher.keeper.file_to_id['en/sepultura/roots/Sepultura - Dictatorshit ZzQZFP5EcbU.opus']])

    try:
        server.run()
    except KeyboardInterrupt:
        logger.info("Shutting down.")