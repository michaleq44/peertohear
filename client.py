import socket
import struct
import json
import random
import string
import sys
import time
import os
import zipfile
import io
from traceback import format_exc
from colorama import init, Fore, Back, Style

from common import *

# format in filename:
#   {title}: the title
#   {artist}: the artist
#   {album}: the album
FILENAME_FMT = "{artist} - {title}"
ALBUM_NAME_FMT = "{artist} - {album}"
BUFFER_SIZE = 128 * 1024
SERVER_ADDRESS = "192.168.1.234"
SERVER_PORT = 3571
SOCKET_TIMEOUT = 5
MAX_NUMBER_RESULTS_SHOWN = 10

class SafeFormatter(string.Formatter):
    def get_value(self, key, args, kwargs):
        if isinstance(key, str) and key not in kwargs:
            return f"{{{key}}}"
        return super().get_value(key, args, kwargs)

def debug(*args, **kwargs):
    print(*args, file=sys.stderr, **kwargs)

def print_results(table: list[list[str | tuple[str, bool]]]):
    max_lens = [0 for _ in range(max(len(item) for item in table))]
    for item in table:
        for it in range(len(item)):
            col = item[it]
            max_lens[it] = max(max_lens[it], len(col if isinstance(col, str) else col[0]))
    for item in table:
        for it in range(len(item)):
            col = item[it]
            if isinstance(col, str):
                print(f"{col:<{max_lens[it]}} ", end="")
            else:
                if col[1]:
                    print(f"{col[0]:>{max_lens[it]}} ", end="")
                else:
                    print(f"{col[0]:<{max_lens[it]}} ", end="")
        print()

def save_file(data: bytes, tagslist: list, dest: str = ".") -> str:
    context_tags = {
        "title": tagslist[TagIndex.TITLE],
        "artist": tagslist[TagIndex.ARTIST],
        "album": tagslist[TagIndex.ALBUM]
    }

    formatter = SafeFormatter()
    try:
        fname = formatter.format(FILENAME_FMT, **context_tags)+f".{tagslist[TagIndex.TYPE]}"
    except ValueError:
        fname = f"{context_tags['title']}.{tagslist[TagIndex.TYPE]}"

    with open(os.path.join(dest, fname), "wb") as f:
        f.write(data)
    return fname

def save_album(data: bytes, tracktags: dict) -> str:
    firsttrack = next(iter(tracktags.values()))
    artist = firsttrack[TagIndex.ARTIST]
    album = firsttrack[TagIndex.ALBUM]
    context_tags = {
        "artist": artist,
        "album": album
    }

    formatter = SafeFormatter()
    try:
        dirname = formatter.format(ALBUM_NAME_FMT, **context_tags)
    except ValueError:
        dirname = f"{context_tags['album']}"
    os.makedirs(dirname, exist_ok=True)
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        files = []
        for info in zf.infolist():
            if not info.is_dir():
                data = zf.read(info.filename)
                files.append((info.filename, data))
    for fname, fdata in files:
        save_file(fdata, tracktags[fname], dirname)

    return dirname

def sendrq_header(sock: socket.socket, arg: str, rqtype: RequestType):
    tx_id = random.randint(1000, 9999)

    debug(f"TX: {tx_id} requesting {rqtype.name}")
    rq_header = struct.pack("!BHI", rqtype, len(arg), tx_id)
    sock.sendall(rq_header)
    sock.sendall(arg.encode('utf-8'))

def recv_json(sock: socket.socket) -> dict | None:
    header = sock.recv(4)
    if not header:
        debug("Connection closed by server")
        return None

    payload_size = struct.unpack("!I", header)[0]

    raw_payload = b""
    while len(raw_payload) < payload_size:
        chunk = sock.recv(min(BUFFER_SIZE, payload_size - len(raw_payload)))
        if not chunk:
            raise ConnectionError("Connection closed by server mid-transfer")
        raw_payload += chunk

    decoded_json = json.loads(raw_payload.decode("utf-8"))

    return decoded_json

def fetch_search_results(sock: socket.socket, arg: str):
    sendrq_header(sock, arg, RequestType.SEARCH)

    received = recv_json(sock)
    if received is None:
        return None

    final_list = [tuple(item) for item in received]
    return final_list

def fetch_album_search(sock: socket.socket, arg: str):
    sendrq_header(sock, arg, RequestType.SEARCH_ALBUM)

    received = recv_json(sock)
    if received is None:
        return None

    final_list = [tuple(item) for item in received]
    return final_list

def fetch_album_contents(sock: socket.socket, arg: str):
    sendrq_header(sock, arg, RequestType.SHOW_ALBUM)

    received = recv_json(sock)
    if received is None:
        return None

    final_list = [tuple(item) for item in received]
    return final_list

def fetch_download(sock: socket.socket, arg: str):
    sendrq_header(sock, arg, RequestType.DOWNLOAD)

    header = sock.recv(13)
    if not header:
        debug("Connection closed by server")
        return None, None

    error, fsize, tagsize = struct.unpack("!BQI", header)
    if not error:
        return None, None
    tagslist = json.loads(sock.recv(tagsize).decode("utf-8"))

    raw_payload = b""
    while len(raw_payload) < fsize:
        chunk = sock.recv(min(BUFFER_SIZE, fsize - len(raw_payload)))
        if not chunk:
            raise ConnectionError("Connection closed by server mid-transfer")
        raw_payload += chunk

    return tagslist, raw_payload

def fetch_album_download(sock: socket.socket, arg: str):
    sendrq_header(sock, arg, RequestType.DOWNLOAD_ALBUM)

    header = sock.recv(13)
    if not header:
        debug("Connection closed by server")
        return None, None

    error, fsize, tagsize = struct.unpack("!BQI", header)
    if not error:
        return None, None
    tagslist = json.loads(sock.recv(tagsize).decode("utf-8"))

    raw_payload = b""
    while len(raw_payload) < fsize:
        chunk = sock.recv(min(BUFFER_SIZE, fsize - len(raw_payload)))
        if not chunk:
            raise ConnectionError("Connection closed by server mid-transfer")
        raw_payload += chunk

    return tagslist, raw_payload

if __name__ == '__main__':
    init(autoreset=True)
    try:
        socket.setdefaulttimeout(SOCKET_TIMEOUT)
        searchresults = []
        albumresults = []
        while True:
            print("> ", end="")
            prompt = input()
            prompt = prompt.strip().split()
            if len(prompt) < 1:
                print("Please enter a command and argument")
                continue
            cmd = prompt[0].lower()
            cmdargs = " ".join(prompt[1:])

            try:
                if cmd == 'q':
                    break

                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                    s.connect((SERVER_ADDRESS, SERVER_PORT))

                    if cmd == 's':
                        searchresults = fetch_search_results(s, cmdargs)
                        if not searchresults:
                            print("No search results")
                            continue
                        searchresults = searchresults[:min(len(searchresults)-1, MAX_NUMBER_RESULTS_SHOWN-1)]
                        searchresults = [result[0] for result in searchresults]
                        res = [[(Style.DIM + f"{idx+1}.", True),
                                result[TagIndex.ARTIST],
                                Style.BRIGHT+Fore.GREEN + result[TagIndex.TITLE],
                                Style.DIM+Fore.BLUE + f"({result[TagIndex.ALBUM]})",
                                (Style.BRIGHT + time.strftime("%M:%S", time.gmtime(result[TagIndex.DURATION])), True),
                                (bytes_si(result[TagIndex.SIZE])[0], True),
                                (Style.DIM + bytes_si(result[TagIndex.SIZE])[1], True),
                                Fore.RED + result[TagIndex.TYPE]]
                               for idx, (result, _) in enumerate(searchresults)]
                        print_results(res)
                    elif cmd == 'sa':
                        albumresults = fetch_album_search(s, cmdargs)
                        if not albumresults:
                            print("No album results")
                            continue
                        res = [[(Style.DIM + f"{idx+1}.", True),
                                artist,
                                Style.BRIGHT+Fore.GREEN + album]
                               for idx, (_, artist, album, dist) in enumerate(albumresults)]
                        print_results(res)
                    elif cmd == 'a':
                        if albumresults is None or len(albumresults) == 0:
                            print("Search an album first")
                            continue
                        cmdargs = int(cmdargs)
                        if cmdargs < 1 or cmdargs > len(albumresults):
                            print("Index out of range")
                            continue
                        searchresults = fetch_album_contents(s, albumresults[cmdargs-1][0])
                        if not searchresults:
                            print("Album contents not found")
                            continue
                        res = [[(Style.DIM + str(result[TagIndex.TRACK]), True),
                                result[TagIndex.ARTIST],
                                Style.BRIGHT + Fore.GREEN + result[TagIndex.TITLE],
                                Style.DIM + Fore.BLUE + f"({result[TagIndex.ALBUM]})",
                                (Style.BRIGHT + time.strftime("%M:%S", time.gmtime(result[TagIndex.DURATION])), True),
                                (bytes_si(result[TagIndex.SIZE])[0], True),
                                (Style.DIM + bytes_si(result[TagIndex.SIZE])[1], True),
                                Fore.RED + result[TagIndex.TYPE]]
                               for result in searchresults]
                        print_results(res)
                    elif cmd == 'd':
                        if searchresults is None or len(searchresults) == 0:
                            print("Search something first")
                            continue
                        cmdargs = int(cmdargs)
                        if cmdargs < 1 or cmdargs > len(searchresults):
                            print("Index out of range")
                            continue
                        tags, filedata = fetch_download(s, searchresults[cmdargs-1][TagIndex.ID])
                        filename = save_file(filedata, tags)
                        print(f"Saved as {filename}")
                    elif cmd == 'da':
                        if albumresults is None or len(albumresults) == 0:
                            print("Search an album first")
                            continue
                        cmdargs = int(cmdargs)
                        if cmdargs < 1 or cmdargs > len(albumresults):
                            print("Index out of range")
                            continue
                        tags, filedata = fetch_album_download(s, albumresults[cmdargs-1][TagIndex.TITLE])
                        foldername = save_album(filedata, tags)
                        print(f"Saved as {foldername}")
            except Exception as e:
                print(f"Error: {e}")
                debug(format_exc())
    except KeyboardInterrupt:
        pass