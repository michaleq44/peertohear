import socket
import struct
import json
import random
import string
import sys
from encodings import cp437

from common import *

# format in filename:
#   {title}: the title
#   {artist}: the artist
#   {album}: the album
FILENAME_FMT = "{artist} - {title}.opus"
BUFFER_SIZE = 4096
SERVER_ADDRESS = "192.168.1.234"
SERVER_PORT = 3571
SOCKET_TIMEOUT = 5

class SafeFormatter(string.Formatter):
    def get_value(self, key, args, kwargs):
        if isinstance(key, str) and key not in kwargs:
            return f"{{{key}}}"
        return super().get_value(key, args, kwargs)

def debug(*args, **kwargs):
    print(*args, file=sys.stderr, **kwargs)

def save_file(data: bytes, tagslist: list) -> str:
    context_tags = {
        "title": tagslist[TagIndex.TITLE],
        "artist": tagslist[TagIndex.ARTIST],
        "album": tagslist[TagIndex.ALBUM]
    }

    formatter = SafeFormatter()
    try:
        fname = formatter.format(FILENAME_FMT, **context_tags)
    except ValueError:
        fname = f"{context_tags['title']}.opus"

    with open(fname, "wb") as f:
        f.write(data)
    return fname

def sendrq_header(sock: socket.socket, arg: str, rqtype: RequestType):
    tx_id = random.randint(1000, 9999)

    debug(f"TX: {tx_id} requesting {rqtype.name}")
    rq_header = struct.pack("!BHI", rqtype, len(arg), tx_id)
    sock.sendall(rq_header)
    sock.sendall(arg.encode('utf-8'))

def fetch_search_results(sock: socket.socket, arg: str):
    sendrq_header(sock, arg, RequestType.SEARCH)

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

    final_list = [tuple(item) for item in decoded_json]
    return final_list

def fetch_download(sock: socket.socket, arg: str):
    sendrq_header(sock, arg, RequestType.DOWNLOAD)

    header = sock.recv(13)
    if not header:
        debug("Connection closed by server")
        return None, None

    error, fsize, tagsize = struct.unpack("!BQI", header)
    if not error:
        return None
    tagslist = json.loads(sock.recv(tagsize).decode("utf-8"))

    raw_payload = b""
    while len(raw_payload) < fsize:
        chunk = sock.recv(min(BUFFER_SIZE, fsize - len(raw_payload)))
        if not chunk:
            raise ConnectionError("Connection closed by server mid-transfer")
        raw_payload += chunk

    return tagslist, raw_payload

if __name__ == '__main__':
    try:
        socket.setdefaulttimeout(SOCKET_TIMEOUT)
        searchresults = []
        while True:
            prompt = input("> ")
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
                        for i in range(len(searchresults)):
                            print(f"{i+1}. {searchresults[i][0][TagIndex.ARTIST]} - {searchresults[i][0][TagIndex.TITLE]} ({searchresults[i][0][TagIndex.ALBUM]}) - {searchresults[i][1]:.2f}%")
                    elif cmd == 'd':
                        if searchresults is None or len(searchresults) == 0:
                            print("Search something first")
                            continue
                        cmdargs = int(cmdargs)
                        if cmdargs < 1 or cmdargs > len(searchresults):
                            print("Index out of range")
                            continue
                        tags, filedata = fetch_download(s, searchresults[cmdargs-1][0][TagIndex.ID])
                        filename = save_file(filedata, tags)
                        print(f"Saved as {filename}")
            except Exception as e:
                print(f"Error: {e}")
    except KeyboardInterrupt:
        pass