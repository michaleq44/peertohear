SERVER_BUFFER_SIZE = 4 * 1024
SERVER_PORT = 3571
SERVER_HOST = '0.0.0.0'
SERVER_MAX_CONNECTIONS = 10
SERVER_MUSIC_DIRECTORY = "/home/michaleq/Music/albums"
SERVER_INDEX_PATH = 'index.json'
SERVER_FILE_ID_LENGTH = 5

from enum import IntEnum

class RequestType(IntEnum):
    SEARCH = 1
    DOWNLOAD = 2