from enum import IntEnum
from filetype import Type

CLIENT_HEADER_SIZE = 7

JSON_HEADER_SIZE = 4
DOWNLOAD_HEADER_SIZE = 13

class RequestType(IntEnum):
    SEARCH = 1
    DOWNLOAD = 2
    SEARCH_ALBUM = 3
    SHOW_ALBUM = 4
    DOWNLOAD_ALBUM = 5

class TagIndex(IntEnum):
    TITLE = 0
    ARTIST = 1
    ALBUM = 2
    ID = 3
    DURATION = 4
    TRACK = 5
    SIZE = 6
    TYPE = 7

class Opus(Type):
    MIME = 'audio/opus'
    EXTENSION = 'opus'
    def __init__(self):
        super().__init__(self.MIME, self.EXTENSION)

    def match(self, buf):
        if len(buf) > 36 and buf[0:4] == b"OggS":
            if buf[28:36] == b"OpusHead":
                return True
        return False

def bytes_si(size_bytes: int, decimal_places: int = 2, binary: bool = True) -> tuple[str, str]:
    if size_bytes == 0:
        return "0", "B"

    base = 1024 if binary else 1000
    suffixes = ["B", "KiB", "MiB"] if binary else ["B", "KB", "MB"]

    mag = 0
    while size_bytes >= base and mag < len(suffixes) - 1:
        size_bytes /= base
        mag += 1

    return f"{size_bytes:.{decimal_places}f}", suffixes[mag]