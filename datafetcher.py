import os.path
import json
import logging
import string
import secrets
from collections import defaultdict
from traceback import format_exc

from mutagen import File
import filetype
from rapidfuzz.utils import default_process
from rapidfuzz import process, fuzz

from config import *
from common import *


class IndexingException(Exception):
    pass

class TagReader:
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.audio = None

    # tag format artist, title, album, id, duration (s), track_number, size, filetype
    def fetch_filetags(self, fname: str, fid: str) -> tuple[str, str, str, str, int, int, int, str] | None:
        if not os.path.exists(fname):
            self.logger.error(f"File {fname} does not exist. Skipping.")
            return None

        try:
            self.audio = File(fname, easy=True)
        except Exception as e:
            self.logger.error(f"Skipping file {fname} because its tags cannot be read: {e}")
            return None

        if self.audio.tags is None:
            self.logger.error(f"File {fname} has no tags. Skipping.")
            return None

        title = self.audio.get("title", [None])[0]
        artist = self.audio.get("artist", [None])[0]
        album = self.audio.get("album", [None])[0]
        track_number = int(str(self.audio.get("tracknumber", [0])[0]).strip().split('/')[0])

        if title and artist and album:
            return (title.strip(), artist.strip(), album.strip(),
                    fid, int(self.audio.info.length), track_number,
                    os.path.getsize(fname), filetype.guess(fname).extension)
        self.logger.error(f"File {fname} is not properly tagged or unsupported. Skipping.")
        return None


class DatabaseKeeper:
    def __init__(self):
        self.dbdir = SERVER_MUSIC_DIRECTORY
        self.indexdb = SERVER_INDEX_PATH
        self.logger = logging.getLogger(__name__)
        self.reader = TagReader()
        self.id_to_file: dict[str, str] = {}
        self.file_to_id: dict[str, str] = {}
        self.id_to_info = {}

        filetype.add_type(Opus())

    def _gen_file_id(self):
        alphabet = string.ascii_letters + string.digits
        while True:
            token = "".join(secrets.choice(alphabet) for _ in range(SERVER_FILE_ID_LENGTH))
            if token not in self.id_to_file:
                return token

    def load_registry(self) -> bool:
        if not os.path.isdir(self.dbdir):
            raise IndexingException("Song database directory does not exist")
        if os.path.isfile(self.indexdb):
            try:
                with open(self.indexdb, 'r', encoding='utf-8') as f:
                    self.id_to_info = json.load(f)
                    self.id_to_file = {fid: finfo['name'] for fid, finfo in self.id_to_info.items()}
                    self.file_to_id = {finfo['name']: fid for fid, finfo in self.id_to_info.items()}
                self.logger.info("Loaded file index from file.")
                return True
            except json.JSONDecodeError:
                self.logger.critical("Registry file corrupt. Remove it and restart server to rebuild.")
                raise IndexingException("Registry file corrupt.")
            except Exception as e:
                self.logger.critical(f"Registry file loading failure: {e}")
                self.logger.info(format_exc())
                raise IndexingException("Registry file loading failure.")
        return False

    def index_files(self):
        current_files: list[str] = []
        for root, dirs, files in os.walk(self.dbdir):
            for fname in files:
                fpath = os.path.join(str(root), str(fname))
                rel_path = os.path.relpath(fpath, self.dbdir)
                rel_path = rel_path.replace(os.sep, "/")
                current_files.append(rel_path)

        changed = False
        for rel_path in current_files:
            if rel_path not in self.file_to_id:
                new_id = self._gen_file_id()
                new_tags = self.reader.fetch_filetags(os.path.join(self.dbdir, rel_path), new_id)
                self.id_to_file[new_id] = rel_path
                self.file_to_id[rel_path] = new_id
                self.id_to_info[new_id] = {
                    'name': rel_path,
                    'tags': new_tags
                }
                changed = True

        for rel_path in list(self.file_to_id.keys()):
            if rel_path not in current_files:
                dead_id = self.file_to_id[rel_path]
                del self.id_to_file[dead_id]
                del self.file_to_id[rel_path]
                del self.id_to_info[dead_id]
                changed = True

        if changed or not os.path.exists(self.indexdb):
            try:
                with open(self.indexdb, 'w', encoding='utf-8') as f:
                    json.dump(self.id_to_info, f, indent=4)
                self.logger.info("Synced changes to file database.")
            except Exception as e:
                self.logger.error(f"Failed to sync file database: {e}. Program will still function.")
        else:
            self.logger.info("No changes to file database.")


class DataFetcher:
    def __init__(self):
        self.keeper = DatabaseKeeper()
        self.logger = logging.getLogger(__name__)
        # title, artist, album, id, length, track, size, type
        self.id_to_tags: dict[str, tuple] = {}
        self.albums: dict[str, list] = {}
        self.reader = TagReader()
        self.dbdir = SERVER_MUSIC_DIRECTORY

        self.keeper.load_registry()
        self.keeper.index_files()

        for fid, finfo in self.keeper.id_to_info.items():
            self.id_to_tags[fid] = finfo['tags']

        self.logger.info("Building album cache.")
        albums = defaultdict(list)
        for fid, tags in self.id_to_tags.items():
            albumstring = ",".join([tags[TagIndex.ARTIST], tags[TagIndex.ALBUM]])
            albums[albumstring].append((tags[TagIndex.TRACK], fid))

        for album, tracks in albums.items():
            tracks.sort(key=lambda x: x[0])
            self.albums[album] = [fid for _, fid in tracks]

        self.logger.info(f"Built album cache: {len(self.albums)} items, {len(self.id_to_tags)} tracks indexed.")

    def search_track(self, q: str, tags: list[int] | None = None) -> list[tuple[str, float]]:
        if tags is None:
            tags = [TagIndex.TITLE, TagIndex.ARTIST]
        for tag in tags:
            if tag < 0 or tag > TagIndex.ID:
                return []
        searchspace: list[str] = []
        ids: list[str] = []
        for item in self.id_to_tags.values():
            searchable = [str(item[t]) for t in tags]
            combined = ",".join(searchable)
            searchspace.append(combined)
            ids.append(item[TagIndex.ID])

        results = process.extract(
            q,
            searchspace,
            scorer=fuzz.WRatio,
            processor=default_process,
            limit=SERVER_SEARCH_RESULT_LIMIT,
            score_cutoff=40.0
        )

        matches = []
        for _, dist, idx in results:
            songid = ids[idx]
            matches.append((songid, dist))

        return matches

    def search_album(self, q: str) -> list[tuple[str, str, str, str]]:
        searchspace: list[str] = list(self.albums.keys())

        results = process.extract(
            q,
            searchspace,
            scorer=fuzz.WRatio,
            processor=default_process,
            limit=SERVER_SEARCH_RESULT_LIMIT,
            score_cutoff=40.0
        )

        matches = []
        for match, dist, _ in results:
            matches.append((match, self.id_to_tags[self.albums[match][0]][TagIndex.ARTIST], self.id_to_tags[self.albums[match][0]][TagIndex.ALBUM], dist))

        return matches