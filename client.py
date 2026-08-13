import socket
import struct
import json
import random

from config import *

def sendrq_header(s: socket.socket, arg: str, rqtype: RequestType):
    tx_id = random.randint(1000, 9999)

    print(f"TX: {tx_id} requesting {rqtype}")
    rq_header = struct.pack("!BHI", rqtype, len(arg), tx_id)
    s.sendall(rq_header)
    s.sendall(arg.encode('utf-8'))

def fetch_search_results(s: socket.socket, arg: str):
    sendrq_header(s, arg, RequestType.SEARCH)

    header = s.recv(4)
    if not header:
        print("Connection closed by server")
        return None

    payload_size = struct.unpack("!I", header)[0]

    raw_payload = b""
    while len(raw_payload) < payload_size:
        chunk = s.recv(min(SERVER_BUFFER_SIZE, payload_size - len(raw_payload)))
        if not chunk:
            raise ConnectionError("Connection closed by server mid-transfer")
        raw_payload += chunk

    decoded_json = json.loads(raw_payload.decode("utf-8"))

    final_list = [tuple(item) for item in decoded_json]
    return final_list

def fetch_download(s: socket.socket, arg: str):
    sendrq_header(s, arg, RequestType.DOWNLOAD)

    header = s.recv(13)
    if not header:
        print("Connection closed by server")
        return None, None

    error, fsize, fn_len = struct.unpack("!BQI", header)
    if not error:
        return None, None
    fname = s.recv(fn_len).decode("utf-8")

    raw_payload = b""
    while len(raw_payload) < fsize:
        chunk = s.recv(min(SERVER_BUFFER_SIZE, fsize - len(raw_payload)))
        if not chunk:
            raise ConnectionError("Connection closed by server mid-transfer")
        raw_payload += chunk

    return fname, raw_payload

if __name__ == '__main__':
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.connect(("192.168.1.234", SERVER_PORT))
            s.settimeout(5)
            print(f"Connected to server, requesting search")

            received = fetch_search_results(s, "A")

            if received:
                print(received)
            else:
                exit(1)

            dwnldid = received[0][4]
            filename, filedata = fetch_download(s, dwnldid)
            print(f"Received {filename}, size {len(filedata)}")
            with open(filename, "wb") as f:
                f.write(filedata)
        except Exception as e:
            print(e)