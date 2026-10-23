from .common import *
import hashlib
# ==============================================================================
# VPK READER
# ==============================================================================
# Source 2 VPK v1/v2 reader.
#
# Important VPK v2 entry layout:
#   uint32 crc
#   uint16 preload_bytes
#   uint16 archive_index
#   uint32 offset
#   uint32 length
#   uint16 terminator (0xFFFF)
#   uint8  preload[preload_bytes]
#
# The previous implementation read only 16 bytes and consumed the terminator
# afterwards. That is unsafe because the preload length belongs to the same
# 18-byte record. The reader below follows the same record layout as the
# reference implementation used by dota2-mod-manager.
# ==============================================================================

class VPKReader:
    VPK_SIGNATURE = 0x55AA1234
    VPK_VERSION = 2
    INLINE_ARCHIVE = 0x7FFF

    def __init__(self, vpk_path: Path):
        self.path = Path(vpk_path)
        self.files: Dict[str, dict] = {}
        self.version = 0
        self.tree_size = 0
        self.header_size = 12
        self.file_data_size = 0
        self.data_section_offset = 0
        self._parse()

    @staticmethod
    def _read_string(f) -> str:
        result = bytearray()
        while True:
            c = f.read(1)
            if not c or c == b"\x00":
                break
            result.extend(c)
        return result.decode("utf-8", errors="replace")

    @staticmethod
    def _normalize_path(path: str) -> str:
        path = str(path).replace("\\", "/").strip("/")
        while "//" in path:
            path = path.replace("//", "/")
        return path.lower()

    def _parse(self):
        if not self.path.exists():
            return

        try:
            with open(self.path, "rb") as f:
                header = f.read(12)
                if len(header) != 12:
                    return

                sig, version, tree_size = struct.unpack("<III", header)

                if sig != self.VPK_SIGNATURE:
                    log.error("Invalid VPK signature: %s", self.path)
                    return

                if version not in (1, 2):
                    log.error("Unsupported VPK version %s: %s", version, self.path)
                    return

                self.version = version
                self.tree_size = tree_size

                if version == 2:
                    extra = f.read(16)
                    if len(extra) != 16:
                        return

                    (
                        self.file_data_size,
                        _archive_md5_size,
                        _other_md5_size,
                        _signature_size,
                    ) = struct.unpack("<IIII", extra)

                    self.header_size = 28
                else:
                    self.header_size = 12

                self.data_section_offset = self.header_size + self.tree_size
                tree_end = self.data_section_offset

                while f.tell() < tree_end:
                    ext = self._read_string(f)
                    if not ext:
                        break

                    while f.tell() < tree_end:
                        directory = self._read_string(f)
                        if not directory:
                            break

                        while f.tell() < tree_end:
                            filename = self._read_string(f)
                            if not filename:
                                break

                            # Full VPK entry record = 18 bytes.
                            entry_data = f.read(18)
                            if len(entry_data) != 18:
                                raise ValueError(
                                    f"Truncated VPK entry in {self.path}"
                                )

                            (
                                crc,
                                preload_size,
                                archive_index,
                                offset,
                                length,
                                terminator,
                            ) = struct.unpack("<IHHIIH", entry_data)

                            if terminator != 0xFFFF:
                                raise ValueError(
                                    f"Invalid VPK entry terminator "
                                    f"{terminator:#06x} in {self.path}"
                                )

                            preload = f.read(preload_size)
                            if len(preload) != preload_size:
                                raise ValueError(
                                    f"Truncated VPK preload in {self.path}"
                                )

                            # Valve uses a single space to represent an empty
                            # extension/folder in a VPK tree.
                            dir_part = "" if directory == " " else directory
                            ext_part = "" if ext == " " else ext

                            if dir_part:
                                full_path = f"{dir_part}/{filename}"
                            else:
                                full_path = filename

                            if ext_part:
                                full_path = f"{full_path}.{ext_part}"

                            full_path = self._normalize_path(full_path)

                            self.files[full_path] = {
                                "crc": crc,
                                "archive_index": archive_index,
                                "offset": offset,
                                "length": length,
                                "preload": preload,
                            }

                log.info(
                    "VPK %s: %d files",
                    self.path.name,
                    len(self.files),
                )

        except Exception as e:
            log.error("VPK parse error %s: %s", self.path, e)

    def _resolve_archive(self, archive_index: int) -> Optional[Path]:
        if archive_index == self.INLINE_ARCHIVE:
            return self.path

        name = self.path.name

        if name.lower().endswith("_dir.vpk"):
            stem = name[:-8]
        else:
            stem = self.path.stem

        candidates = (
            self.path.parent / f"{stem}_{archive_index:03d}.vpk",
            self.path.parent / f"{stem}_{archive_index}.vpk",
        )

        for candidate in candidates:
            if candidate.exists():
                return candidate

        return None

    def _read_entry_data(self, entry: dict) -> Optional[bytes]:
        try:
            preload = entry.get("preload", b"")
            archive_index = entry["archive_index"]
            offset = entry["offset"]
            length = entry["length"]

            if archive_index == self.INLINE_ARCHIVE:
                source = self.path
                base = self.data_section_offset
            else:
                source = self._resolve_archive(archive_index)
                if source is None:
                    return None
                base = 0

            with open(source, "rb") as f:
                f.seek(base + offset)
                body = f.read(length)

            if len(body) != length:
                return None

            return preload + body

        except (OSError, ValueError, KeyError):
            return None

    def extract_file(self, filepath: str, output: Path) -> bool:
        filepath = self._normalize_path(filepath)

        data = self.extract_to_bytes(filepath)
        if data is None:
            return False

        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(data)
        return True

    def extract_to_bytes(self, filepath: str) -> Optional[bytes]:
        filepath = self._normalize_path(filepath)
        entry = self.files.get(filepath)

        if entry is None:
            return None

        return self._read_entry_data(entry)

    def find_file(self, name_part: str) -> Optional[str]:
        name_lower = self._normalize_path(name_part)

        # Exact path is always preferred.
        if name_lower in self.files:
            return name_lower

        # Suffix matching is deliberately conservative. It is only used by
        # callers that explicitly request a fallback.
        matches = [
            path for path in self.files
            if path.endswith("/" + name_lower) or path == name_lower
        ]

        if len(matches) == 1:
            return matches[0]

        return None

    def has_file(self, filepath: str) -> bool:
        return self._normalize_path(filepath) in self.files


# ==============================================================================
# VPK BUILDER
# ==============================================================================

class VPKBuilder:
    VPK_SIGNATURE = 0x55AA1234
    VPK_VERSION = 2
    INLINE_ARCHIVE = 0x7FFF
    CHAMELEON_MARKER = b"CHAMELEON_VPK_V13"

    def __init__(self):
        # Keep the public list for compatibility with existing Chameleon code.
        self.entries: List[dict] = []

        # Path, not CRC, is the identity of a VPK entry.
        # Two different paths may legitimately contain identical bytes.
        self._path_index: Dict[str, dict] = {}

        # Kept for compatibility with old diagnostics/callers. It is NOT used
        # for deduplication.
        self._crc_index: Dict[int, List[str]] = {}

    @staticmethod
    def _normalize_path(path: str) -> str:
        path = str(path).replace("\\", "/").strip("/")
        while "//" in path:
            path = path.replace("//", "/")
        return path.lower()

    def add_file(
        self,
        source: Path,
        vpk_path: str,
        *,
        preload: bytes = b"",
    ):
        data = Path(source).read_bytes()
        self.add_data(data, vpk_path, preload=preload)

    def add_data(
        self,
        data: bytes,
        vpk_path: str,
        *,
        preload: bytes = b"",
    ):
        if data is None:
            return

        if not isinstance(data, bytes):
            data = bytes(data)

        if not data:
            log.warning("Skipping empty data for VPK: %s", vpk_path)
            return

        if not isinstance(preload, bytes):
            preload = bytes(preload)

        path = self._normalize_path(vpk_path)
        if not path:
            return

        if len(preload) > 0xFFFF:
            raise ValueError("VPK preload is larger than uint16")

        # If the same path is added again, replace it. This makes the builder
        # deterministic and lets a later style/resource override an earlier
        # candidate without creating duplicate tree entries.
        old = self._path_index.get(path)

        entry = {
            "path": path,
            "data": data,
            "preload": preload,
            "crc": zlib.crc32(preload + data) & 0xFFFFFFFF,
        }

        if old is not None:
            for i, current in enumerate(self.entries):
                if current is old:
                    self.entries[i] = entry
                    break
        else:
            self.entries.append(entry)

        self._path_index[path] = entry
        self._crc_index.setdefault(entry["crc"], []).append(path)

    def build_standalone(self, output_path: Path):
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        sorted_entries = sorted(
            self._path_index.values(),
            key=lambda e: e["path"],
        )

        # We intentionally keep data in the main data section. It avoids the
        # previous "every small file becomes preload" behavior and means the
        # offsets are unambiguous. The VPK reader still fully supports preload
        # for Valve archives and external tools.
        all_data = bytearray()
        offset_map: Dict[str, Tuple[int, int]] = {}

        for entry in sorted_entries:
            data = entry["data"]

            offset = len(all_data)
            all_data.extend(data)

            offset_map[entry["path"]] = (
                offset,
                len(data),
            )

        by_ext: Dict[str, Dict[str, List[dict]]] = {}

        for entry in sorted_entries:
            path = entry["path"]
            filename = path.rsplit("/", 1)[-1]

            if "." in filename:
                ext = filename.rsplit(".", 1)[1]
            else:
                ext = " "

            directory = path.rsplit("/", 1)[0] if "/" in path else " "

            by_ext.setdefault(ext, {}).setdefault(directory, []).append(entry)

        tree_data = bytearray()

        def write_cstring(value: str):
            tree_data.extend(value.encode("utf-8"))
            tree_data.append(0)

        for ext in sorted(by_ext):
            write_cstring(ext)

            for directory in sorted(by_ext[ext]):
                write_cstring(directory)

                for entry in sorted(
                    by_ext[ext][directory],
                    key=lambda e: e["path"],
                ):
                    path = entry["path"]
                    filename = path.rsplit("/", 1)[-1]

                    if ext != " " and "." in filename:
                        filename = filename.rsplit(".", 1)[0]

                    write_cstring(filename)

                    offset, length = offset_map[path]
                    preload = entry["preload"]

                    # Exact 18-byte VPK entry metadata.
                    tree_data.extend(
                        struct.pack(
                            "<IHHIIH",
                            entry["crc"],
                            len(preload),
                            self.INLINE_ARCHIVE,
                            offset,
                            length,
                            0xFFFF,
                        )
                    )

                    if preload:
                        tree_data.extend(preload)

                # End of filenames in this directory.
                tree_data.append(0)

            # End of directories for this extension.
            tree_data.append(0)

        # End of extensions.
        tree_data.append(0)

        tree_size = len(tree_data)
        file_data_size = len(all_data)

        # VPK v2 layout:
        #   header(28) | tree | file data | archive-MD5 entries (none: single embedded archive)
        #   | other-MD5 section (48 bytes: tree MD5, archive-MD5-section MD5, whole-file MD5) | signature (none)
        tree_md5 = hashlib.md5(bytes(tree_data)).digest()
        archive_md5_section = b""
        archive_section_md5 = hashlib.md5(archive_md5_section).digest()
        header = struct.pack(
            "<IIIIIII",
            self.VPK_SIGNATURE, self.VPK_VERSION,
            len(tree_data), len(all_data),
            len(archive_md5_section), 48, 0,
        )
        body = header + bytes(tree_data) + bytes(all_data) + archive_md5_section + tree_md5 + archive_section_md5
        whole_md5 = hashlib.md5(body).digest()

        tmp_path = output_path.with_suffix(output_path.suffix + ".tmp")
        with open(tmp_path, "wb") as f:
            f.write(body)
            f.write(whole_md5)
        os.replace(tmp_path, output_path)
        file_data_size = len(all_data)

        log.info(
            "VPK built: %s (%d files, %d bytes data)",
            output_path.name,
            len(sorted_entries),
            file_data_size,
        )

        return output_path


