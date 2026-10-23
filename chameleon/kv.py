from .common import *

# ==============================================================================
# KEYVALUES PARSER / WRITER
#
# Valve KeyValues allow the SAME key many times in one block - and items_game relies on it:
#
#     "visuals"
#     {
#         "asset_modifier" { "type" "particle_create" "modifier" "particles/a.vpcf" }
#         "asset_modifier" { "type" "particle_create" "modifier" "particles/b.vpcf" }
#     }
#
# A plain dict keeps only the LAST of those, which silently dropped every effect but one.
# Repeated keys are therefore stored as  "asset_modifier", "asset_modifier\x01 1", "asset_modifier\x01 2" ...
# (first one keeps its plain name). Iterating .items() still yields every entry in file order, the writer
# emits the original key again, and kv_base() / kv_children() give the original name back.
# ==============================================================================

DUP_SEP = "\x01"


def kv_base(key: str) -> str:
    """Original key name (strips the duplicate suffix)."""
    return key.split(DUP_SEP, 1)[0] if isinstance(key, str) and DUP_SEP in key else key


def kv_children(block, name: str) -> list:
    """All values stored under `name` in `block` (including repeated keys), in file order."""
    if not isinstance(block, dict):
        return []
    return [v for k, v in block.items() if kv_base(k) == name]


def kv_set_unique(block: dict, key: str, value) -> str:
    """Add `value` under `key`, using a duplicate-suffix key if `key` is already present. Returns the real key."""
    if key not in block:
        block[key] = value
        return key
    n = 1
    while f"{key}{DUP_SEP}{n}" in block:
        n += 1
    real = f"{key}{DUP_SEP}{n}"
    block[real] = value
    return real


class KeyValueParser:
    def __init__(self, text: str):
        self.text = text
        self.pos = 0
        self.len = len(text)

    def parse(self) -> dict:
        root: dict = {}
        stack = [root]
        current_key = None
        while self.pos < self.len:
            self._skip_ws()
            if self.pos >= self.len:
                break
            c = self.text[self.pos]
            if c == '{':
                self.pos += 1
                new_dict: dict = {}
                if current_key is not None:
                    kv_set_unique(stack[-1], current_key, new_dict)
                else:
                    kv_set_unique(stack[-1], str(len(stack[-1])), new_dict)
                stack.append(new_dict)
                current_key = None
            elif c == '}':
                self.pos += 1
                if len(stack) > 1:
                    stack.pop()
                current_key = None
            else:
                token = self._read_token()
                if not token:
                    break
                if current_key is None:
                    current_key = token
                else:
                    kv_set_unique(stack[-1], current_key, token)
                    current_key = None
        return root

    def _skip_ws(self):
        t, n = self.text, self.len
        while self.pos < n:
            c = t[self.pos]
            if c in ' \t\r\n\ufeff':
                self.pos += 1
            elif c == '/' and self.pos + 1 < n and t[self.pos + 1] == '/':
                while self.pos < n and t[self.pos] != '\n':
                    self.pos += 1
            elif c == '/' and self.pos + 1 < n and t[self.pos + 1] == '*':
                self.pos += 2
                while self.pos < n - 1:
                    if t[self.pos] == '*' and t[self.pos + 1] == '/':
                        self.pos += 2
                        break
                    self.pos += 1
            else:
                break

    def _read_token(self) -> str:
        if self.pos >= self.len:
            return ""
        t = self.text
        if t[self.pos] == '"':
            self.pos += 1
            start = self.pos
            while self.pos < self.len:
                if t[self.pos] == '\\':
                    self.pos += 2
                    continue
                if t[self.pos] == '"':
                    break
                self.pos += 1
            token = t[start:self.pos]
            self.pos += 1
            return token.replace('\\"', '"').replace('\\\\', '\\')
        start = self.pos
        while self.pos < self.len and t[self.pos] not in ' \t\r\n{}"':
            self.pos += 1
        return t[start:self.pos]


class KeyValueWriter:
    @staticmethod
    def write(data: dict, indent=0) -> str:
        lines = []
        tab = "\t" * indent
        for key, value in data.items():
            key = kv_base(key)
            if isinstance(value, dict):
                lines.append(f'{tab}"{key}"')
                lines.append(f"{tab}{{")
                inner = KeyValueWriter.write(value, indent + 1)
                if inner:
                    lines.append(inner)
                lines.append(f"{tab}}}")
            else:
                v = str(value).replace('\\', '\\\\').replace('"', '\\"')
                lines.append(f'{tab}"{key}"\t\t"{v}"')
        return "\n".join(lines)
