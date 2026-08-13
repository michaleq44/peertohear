import os.path
import socket
import struct
import threading

from datafetcher import *

class Server:
    def __init__(self):
        self.fetcher = DataFetcher()
        self.semaphore = threading.Semaphore(SERVER_MAX_CONNECTIONS)
        self.logger = logging.getLogger(__name__)

        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.settimeout(None)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind((SERVER_HOST, SERVER_PORT))

    def run(self):
        self.sock.listen()
        self.logger.info(f"Server running. Max clients: {SERVER_MAX_CONNECTIONS}")

        while True:
            conn, addr = self.sock.accept()
            client_thread = threading.Thread(
                target=self.handle_client, args=(conn, addr), daemon=True
            )
            client_thread.start()

    def handle_client(self, conn: socket.socket, addr):
        self.logger.info(f"Client connected: {addr}")

        try:
            while True:
                header = conn.recv(7)
                if not header:
                    break

                req_id, arg_len, tx_id = struct.unpack("!BHI", header)

                arg = ""
                if arg_len > 0:
                    arg = conn.recv(arg_len).decode('utf-8')

                self.logger.info(f"TX:{tx_id} | Request: {RequestType(req_id).name} (ID: {req_id}) | Arg: '{arg}'")
                self.semaphore.acquire()

                if req_id == RequestType.SEARCH:
                    data = [(self.fetcher.id_to_tags[res[0]], res[1]) for res in self.fetcher.search(arg)]
                    json_bytes = json.dumps(data).encode('utf-8')

                    data_size = len(json_bytes)
                    header = struct.pack("!I", data_size)

                    conn.sendall(header)
                    conn.sendall(json_bytes)
                    self.logger.info(f"Sent package ({data_size} bytes) to client {addr}")
                elif req_id == RequestType.DOWNLOAD:
                    relpath = self.fetcher.keeper.id_to_file.get(arg)
                    if not relpath:
                        self.logger.warning(f"TX:{tx_id} requested nonexistent file.")
                        conn.sendall(struct.pack("!BQI", 0, 0, 0))
                        continue

                    filepath = os.path.join(SERVER_MUSIC_DIRECTORY, relpath)
                    if not os.path.exists(filepath) or not os.path.isfile(filepath):
                        self.logger.warning(f"TX:{tx_id} requested nonexistent file.")
                        conn.sendall(struct.pack("!BQI", 0, 0, 0))
                        continue

                    try:
                        file_size = os.path.getsize(filepath)
                        #fn_bytes = os.path.basename(filepath).encode('utf-8')
                        tags_bytes = json.dumps(self.fetcher.id_to_tags[self.fetcher.keeper.file_to_id[relpath]]).encode('utf-8')

                        conn.sendall(struct.pack("!BQI", 1, file_size, len(tags_bytes)))
                        conn.sendall(tags_bytes)

                        with open(filepath, 'rb') as f:
                            while chunk := f.read(SERVER_BUFFER_SIZE):
                                conn.sendall(chunk)
                    except Exception as e:
                        self.logger.error(f"TX:{tx_id} failed sending: {e}")
                    finally:
                        self.logger.info(f"TX:{tx_id} Finished sending.")
                else:
                    self.logger.error(f"TX:{tx_id} unknown request ID.")
        except ConnectionError:
            self.logger.warning(f"Client {addr} connection error.")
        finally:
            self.semaphore.release()
            conn.close()