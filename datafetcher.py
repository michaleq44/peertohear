import os.path
import json
import logging
import string
import secrets

from mutagen import File
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

    # tag format artist, title, album, duration (s)
    def fetch_filetags(self, fname: str) -> tuple[str, str, str, int] | None:
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

        """
        title, artist, album = None, None, None

        if isinstance(tags, DictMixin):
            title = tags.get("TITLE") or tags.get("Title") or tags.get("WM/Title")
            artist = tags.get("ARTIST") or tags.get("Artist") or tags.get("Author")
            album = tags.get("ALBUM") or tags.get("Album") or tags.get("WM/AlbumTitle")

            title = str(title[0]) if title else None
            artist = str(artist[0]) if artist else None
            album = str(album[0]) if album else None

        if isinstance(tags, ID3Tags):
            artist = tags.get("TPE1", [None])[0]
            title = tags.get("TIT2", [None])[0]
            album = tags.get("TALB", [None])[0]

        if isinstance(tags, MP4Tags):
            artist = tags.get("\xa9ART", [None])[0]
            title = tags.get("\xa9nam", [None])[0]
            album = tags.get("\xa9alb", [None])[0]
        """

        if title and artist and album:
            return title, artist, album, int(self.audio.info.length)
        self.logger.error(f"File {fname} is not properly tagged or unsupported. Skipping.")
        return None

class DatabaseKeeper:
    def __init__(self):
        self.dbdir = SERVER_MUSIC_DIRECTORY
        self.indexdb = SERVER_INDEX_PATH
        self.logger = logging.getLogger(__name__)
        self.id_to_file: dict[str, str] = {}
        self.file_to_id: dict[str, str] = {}

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
                    self.id_to_file = json.load(f)
                    self.file_to_id = {fname: fid for fid, fname in self.id_to_file.items()}
                self.logger.info("Loaded file index from file.")
                return True
            except json.JSONDecodeError:
                self.logger.critical("Registry file corrupt. Remove it and restart server to rebuild.")
                raise IndexingException("Registry file corrupt.")
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
                self.id_to_file[new_id] = rel_path
                self.file_to_id[rel_path] = new_id
                changed = True

        for rel_path in list(self.file_to_id.keys()):
            if rel_path not in current_files:
                dead_id = self.file_to_id[rel_path]
                del self.id_to_file[dead_id]
                del self.file_to_id[rel_path]
                changed = True

        if changed or not os.path.exists(self.indexdb):
            with open(self.indexdb, 'w', encoding='utf-8') as f:
                json.dump(self.id_to_file, f, indent=4)
            self.logger.info("Synced changes to file database.")
        else:
            self.logger.info("No changes to file database.")

class DataFetcher:
    def __init__(self):
        self.keeper = DatabaseKeeper()
        self.logger = logging.getLogger(__name__)
        # title, artist, album, length, id
        self.id_to_tags: dict[str, tuple] = {}
        self.reader = TagReader()
        self.dbdir = SERVER_MUSIC_DIRECTORY

        self.keeper.load_registry()
        self.keeper.index_files()

        for fname, fid in self.keeper.file_to_id.items():
            fullpath = os.path.join(SERVER_MUSIC_DIRECTORY, fname)
            self.logger.info(f"Fetching tags for {fullpath}")
            tags = self.reader.fetch_filetags(fullpath)
            if tags:
                tags = list(tags)
                tags.append(fid)
                self.id_to_tags[fid] = tuple(tags)

    def search(self, q: str, tags: list[int] | None = None) -> list[tuple[str, float]]:
        if tags is None:
            tags = [TagIndex.TITLE, TagIndex.ARTIST]
        for tag in tags:
            if tag < 0 or tag > 4:
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