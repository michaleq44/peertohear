import os.path
import socket
import struct
import threading
import zipfile
import io

from pip._internal.utils import compatibility_tags

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
                    data = [(self.fetcher.id_to_tags[res[0]], res[1]) for res in self.fetcher.search_track(arg)]
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
                elif req_id == RequestType.DOWNLOAD_ALBUM:
                    album_data = self.fetcher.albums.get(arg)
                    if album_data is None:
                        self.logger.warning(f"TX:{tx_id} requested nonexistent album.")
                        conn.sendall(struct.pack("!BQI", 0, 0, 0))
                        continue
                    print(album_data)
                    zip_buffer = io.BytesIO()
                    tagsdata = {}

                    try:
                        with zipfile.ZipFile(zip_buffer, mode='w', compression=zipfile.ZIP_DEFLATED) as zf:
                            for track in album_data:
                                tagsdata[track] = self.fetcher.id_to_tags.get(track)
                                relpath = self.fetcher.keeper.id_to_file.get(track)
                                if relpath is None:
                                    self.logger.error("TX:{tx_id} song cache is malformed.")
                                    conn.sendall(struct.pack("!BQI", 0, 0, 0))
                                    continue
                                filepath = os.path.join(SERVER_MUSIC_DIRECTORY, relpath)
                                if not os.path.exists(filepath) or not os.path.isfile(filepath):
                                    self.logger.warning(f"TX:{tx_id} song cache is malformed.")
                                    conn.sendall(struct.pack("!BQI", 0, 0, 0))
                                    continue
                                with open(filepath, 'rb') as f:
                                    zf.writestr(track, f.read())
                    except Exception as e:
                        self.logger.error(f"TX:{tx_id} failed zipping: {e}")
                        continue

                    try:
                        zip_buffer.seek(0)
                        zip_size = zip_buffer.getbuffer().nbytes
                        tagsdata = json.dumps(tagsdata).encode('utf-8')
                        tags_size = len(tagsdata)

                        conn.sendall(struct.pack("!BQI", 1, zip_size, tags_size))
                        conn.sendall(tagsdata)

                        while chunk := zip_buffer.read(SERVER_BUFFER_SIZE):
                            conn.sendall(chunk)
                    except Exception as e:
                        self.logger.error(f"TX:{tx_id} failed sending: {e}")
                    finally:
                        self.logger.info(f"TX:{tx_id} Finished sending.")
                elif req_id == RequestType.SEARCH_ALBUM:
                    data = self.fetcher.search_album(arg)
                    json_bytes = json.dumps(data).encode('utf-8')

                    data_size = len(json_bytes)
                    header = struct.pack("!I", data_size)

                    conn.sendall(header)
                    conn.sendall(json_bytes)
                    self.logger.info(f"Sent package ({data_size} bytes) to client {addr}")
                elif req_id == RequestType.SHOW_ALBUM:
                    tracks = self.fetcher.albums.get(arg)
                    if not tracks:
                        self.logger.warning(f"TX:{tx_id} requested nonexistent album.")
                        header = struct.pack("!I", 0)
                        conn.sendall(header)
                        continue

                    data = [self.fetcher.id_to_tags[track] for track in tracks]
                    json_bytes = json.dumps(data).encode('utf-8')

                    data_size = len(json_bytes)
                    header = struct.pack("!I", data_size)

                    conn.sendall(header)
                    conn.sendall(json_bytes)
                    self.logger.info(f"Sent package ({data_size} bytes) to client {addr}")
                else:
                    self.logger.error(f"TX:{tx_id} unknown request ID.")
        except ConnectionError:
            self.logger.warning(f"Client {addr} connection error.")
        finally:
            self.semaphore.release()
            conn.close()