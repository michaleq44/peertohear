from enum import IntEnum

class RequestType(IntEnum):
    SEARCH = 1
    DOWNLOAD = 2

class TagIndex(IntEnum):
    TITLE = 0
    ARTIST = 1
    ALBUM = 2
    DURATION = 3
    ID = 4