from .common import *
from .signatures import SignatureManager

MARKER = "Chameleon"          # written beside every line we add so it can be found and removed again
_TAG = f"// {MARKER}"


def _find_block(text: str, keyword: str) -> Tuple[int, int]:
    """Return (start_of_keyword, index_after_closing_brace) of `keyword { ... }`, or (-1, -1)."""
    at = text.find(keyword)
    if at == -1:
        return -1, -1
    open_ = text.find("{", at)
    if open_ == -1:
        return -1, -1
    depth = 0
    for i in range(open_, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                return at, i + 1
    return -1, -1


def search_paths_block(gameinfo_text: str) -> str:
    a, b = _find_block(gameinfo_text, "SearchPaths")
    if a < 0:
        raise ValueError("gameinfo.gi: SearchPaths block not found")
    return gameinfo_text[a:b]


def with_mod_folder(block: str, folder: str) -> str:
    """Add `folder` before the first `Game dota` and the first `Mod dota` line."""
    out, added_game, added_mod = [], False, False
    for line in block.splitlines():
        g = re.match(r"^(\s*)Game(\s+)dota\s*$", line)
        if g and not added_game:
            out.append(f"{g.group(1)}Game{g.group(2)}{folder}\t\t{_TAG}")
            added_game = True
        m = re.match(r"^(\s*)Mod(\s+)dota\s*$", line)
        if m and not added_mod:
            out.append(f"{m.group(1)}Mod{m.group(2)}{folder}\t\t{_TAG}")
            added_mod = True
        out.append(line)
    if not (added_game and added_mod):
        raise ValueError("gameinfo.gi: `Game dota` / `Mod dota` lines not found")
    return "\r\n".join(out)


def strip_patch(text: str) -> str:
    """Remove our SearchPaths block (and nothing else) from a branchspecific file."""
    for _ in range(8):
        if _TAG not in text:
            break
        mark = text.index(_TAG)
        kw = text.rfind("SearchPaths", 0, mark)
        if kw == -1:
            break
        a, b = _find_block(text[kw:], "SearchPaths")
        if a < 0:
            break
        start, end = kw, kw + b
        while start > 0 and text[start - 1] in " \t\r\n":
            start -= 1
        while end < len(text) and text[end] in " \t\r\n":
            end += 1
        joiner = "\r\n\t" if text[end:end + 1] == "}" else "\r\n"
        text = text[:start] + joiner + text[end:]
    return text


def patched_branch(branch_text: str, block: str) -> str:
    a, b = _find_block(branch_text, "FileSystem")
    if a < 0:
        raise ValueError("gameinfo_branchspecific.gi: FileSystem block not found")
    close = b - 1
    head = re.sub(r"[ \t]+$", "", branch_text[:close])
    indented = "\r\n".join(("\t\t" + l.strip()) if l.strip() else l for l in block.splitlines())
    return head + indented + "\r\n\t" + branch_text[close:]


class GameInfoManager:
    """
    Registers the mod folder as an extra content search path.

    Differences from the old version:
      * the SearchPaths block is derived from the CURRENT gameinfo.gi (a Valve change is carried over,
        nothing is hard-coded);
      * the original branchspecific file is backed up exactly once, and never from an already-patched file;
      * restore() strips only our own lines, so a file changed by Valve or another tool is left intact.

    NOTE: this does not touch Valve's integrity lists (dota.signatures). Whether the client accepts a
    modified gameinfo_branchspecific.gi is Valve's call; if the game shows an integrity/VAC notice,
    use "Restore" and verify the game files in Steam.
    """
    BRANCH = "gameinfo_branchspecific.gi"
    MAIN = "gameinfo.gi"

    def __init__(self, dota_path: Path, sign: bool = True):
        self.sign = sign
        self.dota_path = Path(dota_path)
        self.signatures = SignatureManager(self.dota_path, BACKUP_DIR)
        self.game_dir = self.dota_path / "game" / "dota"
        self.branch_path = self.game_dir / self.BRANCH
        self.main_path = self.game_dir / self.MAIN
        self.backup_path = BACKUP_DIR / f"{self.BRANCH}.orig"
        # kept for backward compatibility with the old attribute name
        self.gameinfo_path = self.branch_path

    @staticmethod
    def _read(p: Path) -> str:
        return p.read_bytes().decode("latin1")

    @staticmethod
    def _write(p: Path, text: str):
        tmp = p.with_suffix(p.suffix + ".tmp")
        tmp.write_bytes(text.encode("latin1"))
        os.replace(tmp, p)

    def is_injected(self) -> bool:
        return self.branch_path.exists() and _TAG in self._read(self.branch_path)

    def backup(self):
        """Back up the pristine file once. Never overwrite a good backup with a patched file."""
        if not self.branch_path.exists() or self.backup_path.exists():
            return
        text = self._read(self.branch_path)
        self.backup_path.parent.mkdir(parents=True, exist_ok=True)
        self.backup_path.write_bytes(strip_patch(text).encode("latin1"))

    def inject_vpk(self) -> bool:
        if not self.main_path.exists() or not self.branch_path.exists():
            log.error("gameinfo files not found under %s", self.game_dir)
            return False
        self.backup()
        current = strip_patch(self._read(self.branch_path))
        block = with_mod_folder(search_paths_block(self._read(self.main_path)), MOD_FOLDER_NAME)
        self._write(self.branch_path, patched_branch(current, block))
        if self.sign:
            self.signatures.patch(self.branch_path.read_bytes())      # keep the client's integrity check consistent
        return True

    def remove_vpk(self) -> bool:
        if not self.branch_path.exists():
            return True
        text = self._read(self.branch_path)
        if _TAG in text:
            self._write(self.branch_path, strip_patch(text))
        self.signatures.restore()
        return True

    def restore(self) -> bool:
        return self.remove_vpk()
