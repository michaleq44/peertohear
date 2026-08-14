from enum import IntEnum

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