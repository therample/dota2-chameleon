from .common import *
from .vpk_io import *
from .kv import *
from .models import *
class ResourceResolver:
    ALL_FILE_EXTS = ['.vmdl', '.vmat', '.vtex', '.vpcf', '.vanim', '.vsnd', '.png', '.vtf', 
                     '.wav', '.mp3', '.mdl', '.vmt', '.pcf',
                     '.vmdl_c', '.vmat_c', '.vtex_c', '.vpcf_c', '.vanim_c', '.vsnd_c', 
                     '.vsndevts', '.vsndevts_c', '.vsvg', '.vxml', '.fxc', '.fxh', '.cg', 
                     '.cso', '.dxbc', '.tga', '.jpg', '.jpeg', '.vfont', '.ttf']
    PATH_PREFIXES = ["models/", "materials/", "particles/", "sounds/", "scripts/", 
                     "textures/", "panorama/", "resource/", "maps/", "shaders/", 
                     "ui/", "localization/", "cfg/", "events/"]
    RESOURCE_EXTS = {'.vmdl', '.vmdl_c', '.vmat', '.vmat_c', '.vtex', '.vtex_c', '.vpcf', '.vpcf_c',
                     '.vanim', '.vanim_c', '.mdl', '.vmt', '.pcf', '.vtf', '.png', '.tga',
                     '.vsnd', '.vsnd_c', '.vsndevts', '.vsndevts_c', '.wav', '.mp3', '.vsvg', '.vfont'}
    
    # Patterns for junk paths to filter out
    JUNK_PATTERNS = [
        "/test/", "/_test/", "/debug/", "/_debug/", "/temp/", "/_temp/",
        "/dev/", "/_dev/", "/wip/", "/_wip/", "/old/", "/_old/",
        "/unused/", "/_unused/", "/backup/", "/_backup/",
    ]
    _KNOWN_EXTS_BYTES = (b'.vmdl', b'.vmat', b'.vtex', b'.vpcf', b'.vanim',
                         b'.vsnd', b'.vsndevts', b'.vagrp', b'.vseq', b'.vmorf')

    def _scan_raw_refs(self, data: bytes) -> Set[str]:
        """
        Единый бинарный сканер ссылок внутри compiled resource (_c) и
        текстовых KV3-блоков. Source 2 хранит часть путей БЕЗ слэшей
        (m_keyValueText, particle_cfg_list, RERL-таблицы) — старый
        код требовал '/' в строке и терял эти ссылки, из-за чего
        пропадали эмбиенты, ауры и анимационные зависимости арканы.
        """
        refs: Set[str] = set()
        for ext in self._KNOWN_EXTS_BYTES:
            idx = 0
            while True:
                idx = data.find(ext, idx)
                if idx == -1:
                    break
                start = idx
                while start > 0:
                    b = data[start - 1]
                    if b < 0x20 or b > 0x7e:
                        break
                    ch = chr(b)
                    if ch not in ('abcdefghijklmnopqrstuvwxyz'
                                  'ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_/.-'):
                        break
                    start -= 1
                try:
                    raw_str = data[start: idx + len(ext)].decode('ascii')
                except UnicodeDecodeError:
                    idx += len(ext)
                    continue
                if len(raw_str) > 5:
                    candidate = raw_str if '/' in raw_str else self._reconstruct_path(raw_str)
                    refs.add(candidate.lower())
                idx += len(ext)
        return refs

    def _resolve_and_extract_refs(self, refs: Set[str], resources: Dict[str, bytes],
                                   processed: Set[str], depth: int, max_depth: int):
        for ref in refs:
            clean = self._clean_path(ref)
            if not clean or clean in processed or self._is_junk_path(clean):
                continue
            file_path = self._find_in_vpks(clean)
            if not file_path and not clean.endswith('_c'):
                file_path = self._find_in_vpks(clean + '_c')
            if file_path:
                self._extract_recursive(clean, resources, processed, depth, max_depth)

    def __init__(self, vpk_readers: List['VPKReader']):
        self.vpk_readers = vpk_readers
        self._resolved_cache: Dict[str, Dict[str, bytes]] = {}
        self._flat_index: Dict[str, str] = {}
        self._all_files_set: Set[str] = set()
        self._build_flat_index()

    def _build_flat_index(self):
        """
        Build only deterministic aliases.

        The previous implementation flattened every path by deleting all '/'
        characters. That creates collisions such as:
            models/foo/bar.vmdl_c
            models/foob/ar.vmdl_c

        More importantly, a flat basename lookup is unsafe for cosmetics:
        different heroes/sets frequently have the same resource basename.

        We keep exact paths as the primary index and only create conservative
        aliases for Resource-prefixed paths.
        """
        exact: Dict[str, str] = {}
        aliases: Dict[str, Set[str]] = {}
        all_files: Set[str] = set()

        for reader in self.vpk_readers:
            for raw_path in reader.files:
                fp = raw_path.replace("\\", "/").strip("/").lower()
                if not fp:
                    continue

                all_files.add(fp)
                exact.setdefault(fp, fp)

                # Resource roots can appear as "resource/..." in one archive
                # and without the prefix in another.
                if fp.startswith("resource/"):
                    stripped = fp[len("resource/"):]
                    aliases.setdefault(stripped, set()).add(fp)

        self._flat_index = exact
        self._alias_index = aliases
        self._all_files_set = all_files

        log.info(
            "ResourceResolver: exact index (%d files, %d resource aliases)",
            len(exact),
            len(aliases),
        )

    def _get_flat_index(self) -> Dict[str, str]:
        return self._flat_index

    def _is_junk_path(self, path: str) -> bool:
        path_lower = path.lower()
        for pattern in self.JUNK_PATTERNS:
            if pattern in path_lower:
                return True
        return False
    
    @staticmethod
    def _is_precise_match(fp_lower: str, item_short: str, hero_short: str = "") -> bool:
        filename = fp_lower.rsplit('/', 1)[-1]
        stem = filename.split('.', 1)[0]
        tokens = set(stem.split('_'))
        item_tokens = set(item_short.split('_'))
        token_match = (item_short in stem and (stem == item_short or f"_{item_short}" in stem or f"{item_short}_" in stem)) \
                      or (len(item_tokens) > 1 and item_tokens.issubset(tokens))
        if not token_match:
            return False
        if hero_short:
            segments = fp_lower.split('/')
            if not any(hero_short == seg or hero_short in seg.split('_') for seg in segments):
                return False
        return True

    def resolve_item_resources(self, item: SkinItem, progress_cb=None, style_id: Optional[int] = None) -> Dict[str, bytes]:
        # Item name is not always globally unique in reconstructed item data.
        # Prefer the stable def_index/internal_name when available.
        identity = (
            getattr(item, "def_index", "")
            or getattr(item, "internal_name", "")
            or getattr(item, "name", "")
        )
        cache_key = (
            f"{identity}::style{style_id}"
            if style_id is not None
            else str(identity)
        )
        if cache_key in self._resolved_cache:
            return self._resolved_cache[cache_key]

        resources: Dict[str, bytes] = {}
        processed: Set[str] = set()
        all_paths: Set[str] = set()
        declared_particles: Set[str] = set()

        for p in item.model_paths: all_paths.add(p)
        for p in item.particle_paths: 
            all_paths.add(p)
            declared_particles.add(p)
        for p in item.material_paths: all_paths.add(p)
        for p in item.animation_paths: all_paths.add(p)
        for p in item.texture_paths: all_paths.add(p)
        for p in item.sound_paths: all_paths.add(p)
        for p in item.visual_assets: all_paths.add(p)
        if item.model_player: all_paths.add(item.model_player)
        if item.courier_model_path: all_paths.add(item.courier_model_path)
        if item.weather_particle_path: all_paths.add(item.weather_particle_path)
        if item.terrain_resource_path and not item.terrain_resource_path.startswith("terrain:"):
            all_paths.add(item.terrain_resource_path)
        if item.particle_effect: 
            all_paths.add(item.particle_effect)
            declared_particles.add(item.particle_effect)
        if item.gem_particle: all_paths.add(item.gem_particle)
        if item.icon_path: all_paths.add(item.icon_path)

        for icon_type, icon_path in item.icons.items():
            if icon_path: all_paths.add(icon_path)

        if item.raw_item_data:
            attached = item.raw_item_data.get("attached_particle_effects", {})
            if isinstance(attached, dict):
                for _, pe in attached.items():
                    if isinstance(pe, dict):
                        p = pe.get("particle", "")
                        if p:
                            all_paths.add(p)
                            declared_particles.add(p)

        item_short = item.name.replace("item_", "").lower() if item.name else ""
        hero_short = item.used_by_hero.replace("npc_dota_hero_", "").lower() if item.used_by_hero else ""

        if item.is_arcana or item.is_persona:
            arcana_extra_paths: Set[str] = set()
            arcana_body_candidates: Set[str] = set()
            arcana_particle_candidates: Set[str] = set()

            if item.model_player:
                arcana_body_candidates.add(item.model_player)

            if item.raw_item_data:
                am_data = item.raw_item_data.get("asset_modifiers", {})
                if isinstance(am_data, dict):
                    for _, mod in am_data.items():
                        if not isinstance(mod, dict): continue
                        mod_asset = mod.get("asset", "") or mod.get("model_player", "") or mod.get("model", "")
                        if mod_asset:
                            arcana_body_candidates.add(mod_asset)
                        mod_particle = mod.get("particle", "")
                        if mod_particle:
                            arcana_extra_paths.add(mod_particle)
                            arcana_particle_candidates.add(mod_particle)

                visuals_data = item.raw_item_data.get("visuals", {})
                if isinstance(visuals_data, dict):
                    for _, ve in visuals_data.items():
                        if not isinstance(ve, dict): continue
                        ve_asset = ve.get("asset", "") or ve.get("model_player", "") or ve.get("model", "")
                        if ve_asset:
                            arcana_body_candidates.add(ve_asset)
                        ve_particle = ve.get("particle", "")
                        if ve_particle:
                            arcana_extra_paths.add(ve_particle)
                            arcana_particle_candidates.add(ve_particle)

                deep_scan_paths: Set[str] = set()
                self._scan_known_fields(item.raw_item_data, deep_scan_paths, 0, 20)
                for p in deep_scan_paths:
                    if not p or p.startswith("terrain:"): continue
                    p_lower = p.lower()
                    if p_lower.endswith(('.vmdl', '.vmdl_c', '.mdl')):
                        arcana_body_candidates.add(p)
                    elif p_lower.endswith(('.vpcf', '.vpcf_c', '.pcf')):
                        arcana_extra_paths.add(p)
                        arcana_particle_candidates.add(p)
                    else:
                        all_paths.add(p)

            for style in item.styles:
                if style.model_player: arcana_body_candidates.add(style.model_player)
                if style.asset: arcana_body_candidates.add(style.asset)
                for m in style.models: 
                    arcana_body_candidates.add(m)
                for p in style.particles: 
                    arcana_extra_paths.add(p)
                    arcana_particle_candidates.add(p)
                for m in style.materials: arcana_extra_paths.add(m)
                for t in style.textures: arcana_extra_paths.add(t)
                for i in style.icons: arcana_extra_paths.add(i)
                
                if style.raw_data:
                    style_am = style.raw_data.get("asset_modifiers", {})
                    if isinstance(style_am, dict):
                        for _, mod in style_am.items():
                            if not isinstance(mod, dict): continue
                            mod_asset = mod.get("asset", "") or mod.get("model_player", "") or mod.get("model", "")
                            if mod_asset:
                                arcana_body_candidates.add(mod_asset)
                            mod_particle = mod.get("particle", "")
                            if mod_particle:
                                arcana_extra_paths.add(mod_particle)
                                arcana_particle_candidates.add(mod_particle)
                    
                    style_scan_paths: Set[str] = set()
                    self._scan_known_fields(style.raw_data, style_scan_paths, 0, 15)
                    for p in style_scan_paths:
                        if not p or p.startswith("terrain:"): continue
                        p_lower = p.lower()
                        if p_lower.endswith(('.vmdl', '.vmdl_c', '.mdl')):
                            arcana_body_candidates.add(p)
                        elif p_lower.endswith(('.vpcf', '.vpcf_c', '.pcf')):
                            arcana_extra_paths.add(p)
                            arcana_particle_candidates.add(p)

            for path in arcana_extra_paths:
                all_paths.add(path)

            for body_path in arcana_body_candidates:
                clean = self._clean_path(body_path)
                if clean and clean not in resources:
                    body_processed: Set[str] = set()
                    self._extract_recursive(clean, resources, body_processed, 0, 40)

            for particle_path in arcana_particle_candidates:
                clean = self._clean_path(particle_path)
                if clean and clean not in resources:
                    particle_processed: Set[str] = set()
                    self._extract_recursive(clean, resources, particle_processed, 0, 35)

        if style_id is not None:
            for style in item.styles:
                if style.style_id != style_id: continue
                if style.model_player: all_paths.add(style.model_player)
                if style.asset: all_paths.add(style.asset)
                for p in style.particles: 
                    all_paths.add(p)
                    declared_particles.add(p)
                for p in style.models: all_paths.add(p)
                for p in style.materials: all_paths.add(p)
                for p in style.textures: all_paths.add(p)
                for p in style.icons: all_paths.add(p)
                if style.raw_data:
                    style_attached = style.raw_data.get("attached_particle_effects", {})
                    if isinstance(style_attached, dict):
                        for _, pe in style_attached.items():
                            if isinstance(pe, dict):
                                p = pe.get("particle", "")
                                if p: 
                                    all_paths.add(p)
                                    declared_particles.add(p)
                    self._scan_known_fields(style.raw_data, all_paths)
                break

        for ao in item.ability_overrides:
            if ao.icon: 
                all_paths.add(ao.icon)
                if not ao.icon.endswith('.vtex_c') and not ao.icon.endswith('.png'):
                    all_paths.add(ao.icon + '.vtex_c')
                    all_paths.add(ao.icon + '_png.vtex_c')
            for p in ao.particles: 
                all_paths.add(p)
                declared_particles.add(p)
            for p in ao.projectiles: 
                all_paths.add(p)
                declared_particles.add(p)
            for p in ao.sounds: all_paths.add(p)
            if ao.cast_effect: all_paths.add(ao.cast_effect)
            if ao.hit_effect: all_paths.add(ao.hit_effect)
            if ao.modifier_effect: all_paths.add(ao.modifier_effect)
            if ao.raw_data:
                self._scan_known_fields(ao.raw_data, all_paths)

        for mod in item.asset_modifiers:
            mod_asset = mod.get("asset", "") or mod.get("model_player", "") or mod.get("model", "")
            if mod_asset: all_paths.add(mod_asset)
            mod_particle = mod.get("particle", "")
            if mod_particle: 
                all_paths.add(mod_particle)
                declared_particles.add(mod_particle)
            mod_icon = mod.get("icon", "")
            if mod_icon: 
                all_paths.add(mod_icon)
                if not mod_icon.endswith('.vtex_c') and not mod_icon.endswith('.png'):
                    all_paths.add(mod_icon + '.vtex_c')
                    all_paths.add(mod_icon + '_png.vtex_c')
            mod_animation = mod.get("animation", "")
            if mod_animation: all_paths.add(mod_animation)
            mod_material = mod.get("material", "")
            if mod_material: all_paths.add(mod_material)
            mod_texture = mod.get("texture", "")
            if mod_texture: all_paths.add(mod_texture)

        if item.raw_item_data:
            self._scan_known_fields(item.raw_item_data, all_paths)

        for path in all_paths:
            if not path or path.startswith("terrain:"): continue
            if self._is_junk_path(path): continue
            clean = self._clean_path(path)
            if clean: 
                self._extract_recursive(clean, resources, processed, 0, 30)

        self._resolved_cache[cache_key] = resources
        if progress_cb:
            if resources: progress_cb(f"  Found {len(resources)} files for {item.name}")
            else: progress_cb(f"  No resources found for {item.name}")
        return resources
    
    def _scan_known_fields(self, data, all_paths: Set[str], depth=0, max_depth=15):
        if depth > max_depth: return
        KNOWN_ASSET_KEYS = {
            "model_player", "model", "asset", "modifier", "particle", "material", "texture",
            "animation", "icon", "image_inventory", "image_browser", "image_large",
            "image_inventory_wide", "image_store", "hero_icon", "image_hero",
            "portrait", "image_portrait", "sound", "voice_file", "custom_texture",
            "replaceable_texture", "entity_model", "world_model", "particle_file",
            "particle_modifier", "effect", "visual", "asset_modifier",
            "model_override", "texture_override", "particle_override",
            "projectile", "trail", "aura", "ambient_particle", "spawn_effect",
            "kill_effect", "display_unit", "hud_icon", "inventory_icon",
            "icon_redeem", "icon_inventory", "cape", "hair", "beard",
            "skin", "expression", "physics", "trail_effect",
            "ambient_particles", "face", "facial_animation", "morph",
            "transformation", "abilities", "ability_effects",
            "modifier_particle", "model_modifiers", "particle_modifiers",
            "hero_model_override", "alternate_hero_model", "persona_model",
            "particles", "assets", "voice", "voice_file",
            "child_particle", "sub_particle", "modifier_effect",
            "cast_effect", "hit_effect", "death_effect",
            "spawn_particle", "ambient_effect", "persistent_effect",
            "vsnd", "vsndevts", "sound_effect",
            "m_name", "m_refMeshes", "m_refAnimGroups", "m_refSequenceGroups",
            "m_refAnimIncludeModels", "m_materialGroups", "m_meshGroups",
            "m_refPhysicsData", "m_refPhysicsHitboxData", "m_animGraph2Refs",
            "m_vecNmSkeletonRefs", "m_ExtParts",
        }
        if isinstance(data, dict):
            for key, value in data.items():
                key_lower = key.lower() if isinstance(key, str) else ""
                if isinstance(value, str) and key_lower in KNOWN_ASSET_KEYS:
                    if self._looks_like_path(value): all_paths.add(value)
                elif isinstance(value, dict): self._scan_known_fields(value, all_paths, depth+1, max_depth)
                elif isinstance(value, list):
                    for item in value:
                        if isinstance(item, str) and key_lower in KNOWN_ASSET_KEYS:
                            if self._looks_like_path(item): all_paths.add(item)
                        elif isinstance(item, dict): self._scan_known_fields(item, all_paths, depth+1, max_depth)
        elif isinstance(data, list):
            for item in data:
                if isinstance(item, dict): self._scan_known_fields(item, all_paths, depth+1, max_depth)
    
    def _looks_like_path(self, s: str) -> bool:
        if not s or len(s) < 3: return False
        if s.startswith("terrain:"): return False
        s_lower = s.lower()
        for prefix in self.PATH_PREFIXES:
            if s_lower.startswith(prefix): return True
        if s_lower.startswith("s2r://"): return True
        if s_lower.startswith("panorama://"): return True
        for ext in self.ALL_FILE_EXTS:
            if ext in s_lower: return True
        if '/' in s and '.' in s and not s.startswith('{') and not s.startswith('http'):
            parts = s.split('/')
            if len(parts) >= 2:
                last_part = parts[-1]
                if '.' in last_part: return True
        return False
    
    def _clean_path(self, path: str) -> str:
        clean = path.replace("\\", "/").strip()
        if clean.startswith("s2r://"): clean = clean[5:]
        if clean.startswith("panorama://"): clean = clean[11:]
        clean = clean.replace("{", "").replace("}", "")
        return clean.lower()
    
    def _extract_recursive(self, path: str, resources: Dict[str, bytes], processed: Set[str], depth: int, max_depth: int, item_short: str = "", hero_short: str = ""):
        if depth > max_depth or not path or path in processed: return
        if self._is_junk_path(path): return
        processed.add(path)

        file_path = self._find_in_vpks(path)

        if not file_path:
            base = path
            for ext in ['.vmdl_c', '.vmat_c', '.vtex_c', '.vpcf_c', '.vanim_c', '.vsnd_c',
                        '.vsndevts_c', '.vmdl', '.vmat', '.vtex', '.vpcf', '.vanim', '.vsnd',
                        '.png', '.vtf', '.vmt', '.mdl', '.pcf', '.wav', '.mp3', '.tga']:
                if base.endswith(ext):
                    base = base[:-len(ext)]
                    break

            suffixes = [
                '', '_c',
                '.vtex_c', '.vmdl_c', '.vmat_c', '.vpcf_c', '.vanim_c', '.vsnd_c', '.vsndevts_c',
                '_png.vtex_c', '.png', '_png.png',
                '.vmdl', '.vmat', '.vtex', '.vpcf', '.vanim', '.vsnd',
                '.vtf', '.vmt', '.mdl', '.pcf', '.wav', '.mp3', '.tga',
            ]
            for suffix in suffixes:
                candidate = base + suffix
                if candidate == path: continue
                file_path = self._find_in_vpks(candidate)
                if file_path: break

            if not file_path and not path.endswith('_png'):
                file_path = self._find_in_vpks(path + '_png')
            if not file_path and path.endswith('_png'):
                file_path = self._find_in_vpks(path[:-4])

        # Never pick an arbitrary same-basename file here. If the reference
        # omitted a directory, accept it only when exactly one candidate exists.
        # This is intentionally conservative: a missing cosmetic is preferable
        # to silently borrowing another hero's material/model.
        if not file_path:
            filename = Path(path).name.lower()

            exact_suffix_matches = [
                fp for fp in self._all_files_set
                if fp.endswith("/" + filename)
            ]

            if len(exact_suffix_matches) == 1:
                file_path = exact_suffix_matches[0]
            elif len(exact_suffix_matches) > 1:
                # Try to disambiguate using the already known parent directory.
                requested_parts = [
                    part for part in path.lower().split("/")
                    if part
                ][:-1]

                scored = []
                for fp in exact_suffix_matches:
                    candidate_parts = [
                        part for part in fp.lower().split("/")
                        if part
                    ][:-1]

                    score = 0
                    for a, b in zip(
                        reversed(requested_parts),
                        reversed(candidate_parts),
                    ):
                        if a != b:
                            break
                        score += 1

                    scored.append((score, fp))

                scored.sort(key=lambda x: (-x[0], x[1]))

                if scored:
                    best_score = scored[0][0]
                    best = [
                        fp for score, fp in scored
                        if score == best_score
                    ]

                    if len(best) == 1 and best_score > 0:
                        file_path = best[0]


        if not file_path: return
        if self._is_junk_path(file_path): return

        data = self._extract_file(file_path)
        if not data or len(data) == 0: return

        resources[file_path] = data

        if file_path.endswith(('.vmdl', '.vmdl_c', '.mdl')):
            self._parse_model_deps(data, resources, processed, depth + 1, max_depth)
        elif file_path.endswith(('.vmat', '.vmat_c', '.vmt')):
            self._parse_material_deps(data, resources, processed, depth + 1, max_depth)
        elif file_path.endswith(('.vpcf', '.vpcf_c', '.pcf')):
            self._parse_particle_deps(data, resources, processed, depth + 1, max_depth)
    
    def _find_in_vpks(self, path: str) -> Optional[str]:
        """
        Resolve a resource without guessing across unrelated directories.

        Resolution order:
          1. exact canonical path
          2. resource/<path> alias
          3. panorama/images/<path> compatibility mapping
          4. unique suffix match
          5. otherwise None

        We deliberately do NOT choose an arbitrary same-basename file.
        Ambiguous resources are worse than a missing resource because they
        produce valid-looking but incorrect cosmetics.
        """
        path_lower = self._clean_path(path)

        if not path_lower:
            return None

        # Exact path across all VPKs.
        if path_lower in self._all_files_set:
            return path_lower

        # resource/<path> and <path> are common representations of the same
        # logical asset.
        if path_lower.startswith("resource/"):
            stripped = path_lower[len("resource/"):]
            if stripped in self._all_files_set:
                return stripped
        else:
            resource_path = "resource/" + path_lower
            if resource_path in self._all_files_set:
                return resource_path

        # Panorama assets are often referenced with or without this prefix.
        panorama_candidates = []
        if path_lower.startswith("panorama/images/"):
            panorama_candidates.append(
                path_lower[len("panorama/images/"):]
            )
        else:
            panorama_candidates.append(
                "panorama/images/" + path_lower
            )

        for candidate in panorama_candidates:
            if candidate in self._all_files_set:
                return candidate

        # A suffix match is safe only when it is unique.
        # This handles references that omit a known root while preventing
        # cross-hero collisions.
        suffix = "/" + path_lower
        matches = [
            fp for fp in self._all_files_set
            if fp.endswith(suffix)
        ]

        if len(matches) == 1:
            return matches[0]

        # Extension aliases such as foo.vmdl -> foo.vmdl_c are deterministic.
        if not path_lower.endswith("_c"):
            compiled = path_lower + "_c"
            if compiled in self._all_files_set:
                return compiled

        return None

    def _extract_file(self, path: str) -> Optional[bytes]:
        for reader in self.vpk_readers:
            if path in reader.files:
                data = reader.extract_to_bytes(path)
                if data and len(data) > 0:
                    return data
        for reader in self.vpk_readers:
            found = reader.find_file(path)
            if found:
                data = reader.extract_to_bytes(found)
                if data and len(data) > 0:
                    return data
        return None
    
    def _parse_model_deps(self, data: bytes, resources: Dict[str, bytes], processed: Set[str],
                           depth: int, max_depth: int, item_short: str = "", hero_short: str = ""):
        refs = self._scan_raw_refs(data)
        refs.update(self._parse_vmdl_keyvalue_text(data))
        self._resolve_and_extract_refs(refs, resources, processed, depth, max_depth)

    def _parse_vmdl_keyvalue_text(self, data: bytes) -> Set[str]:
        """Parses m_keyValueText from vmdl_c and extracts particle_cfg_list and model refs."""
        refs: Set[str] = set()
        
        text = data.decode('utf-8', errors='ignore')
        
        # Pattern for particle_cfg_list blocks
        particle_pattern = r'particle_cfg_list\s*=\s*\[([^\]]+)\]'
        for match in re.finditer(particle_pattern, text, re.DOTALL):
            block = match.group(1)
            # Extract all name = path.vpcf entries
            for pm in re.finditer(r'name\s*=\s*([^\s\n]+)', block):
                path = pm.group(1).strip().strip('"').strip("'")
                if path and ('.vpcf' in path or 'particle' in path.lower()):
                    path = self._reconstruct_path(path)
                    refs.add(path.lower())
        
        # Also extract m_name = ... .vmdl references
        vmdl_pattern = r'm_name\s*=\s*([^\s\n]+\.vmdl)'
        for match in re.finditer(vmdl_pattern, text):
            path = match.group(1).strip().strip('"')
            if path:
                path = self._reconstruct_path(path)
                refs.add(path.lower())
        
        # Extract m_refAnimIncludeModels references
        anim_include_pattern = r'm_refAnimIncludeModels\s*=\s*\[([^\]]+)\]'
        for match in re.finditer(anim_include_pattern, text, re.DOTALL):
            block = match.group(1)
            for am in re.finditer(r'([a-zA-Z0-9_/.]+\.vmdl)', block):
                path = am.group(1).strip().strip('"')
                if path:
                    path = self._reconstruct_path(path)
                    refs.add(path.lower())
        
        return refs

    def _reconstruct_path(self, raw: str) -> str:
        """Reconstructs slashed path from slashless string."""
        raw = raw.strip().lower()
        if '/' in raw:
            return raw
        for old_prefix, new_prefix in [('resourceparticles', 'resource/particles/'),
                                       ('resourcematerials', 'resource/materials/'),
                                       ('resourcemodels', 'resource/models/'),
                                       ('resourcesounds', 'resource/sounds/'),
                                       ('resourcetextures', 'resource/textures/'),
                                       ('resourcescripts', 'resource/scripts/')]:
            if raw.startswith(old_prefix):
                return new_prefix + raw[len(old_prefix):]
        for stripped, slashed in [('particles', 'particles/'), ('materials', 'materials/'),
                                   ('models', 'models/'), ('sounds', 'sounds/'),
                                   ('textures', 'textures/'), ('scripts', 'scripts/')]:
            if raw.startswith(stripped):
                return slashed + raw[len(stripped):]
        return raw

    def _reconstruct_slashless_path(self, raw: str) -> str:
        raw = raw.strip().lower()
        if '/' in raw:
            return raw
        result = raw
        for old_prefix, new_prefix in [('resourceparticles', 'resource/particles/'),
                                       ('resourcematerials', 'resource/materials/'),
                                       ('resourcemodels', 'resource/models/'),
                                       ('resourcesounds', 'resource/sounds/'),
                                       ('resourcetextures', 'resource/textures/'),
                                       ('resourcescripts', 'resource/scripts/')]:
            if result.startswith(old_prefix):
                result = new_prefix + result[len(old_prefix):]
                break
        else:
            for stripped, slashed in [('particles', 'particles/'), ('materials', 'materials/'),
                                       ('models', 'models/'), ('sounds', 'sounds/'),
                                       ('textures', 'textures/'), ('scripts', 'scripts/')]:
                if result.startswith(stripped):
                    result = slashed + result[len(stripped):]
                    break
        return result

    def _find_best_vpk_match(self, slashless_path: str) -> Optional[str]:
        ext_match = re.search(r'\.([a-zA-Z0-9_]+)$', slashless_path)
        if not ext_match:
            return None

        flat = slashless_path.lower().replace("/", "")
        flat_index = self._get_flat_index()
        if flat in flat_index:
            return flat_index[flat]
        if flat.startswith("resource") and flat[len("resource"):] in flat_index:
            return flat_index[flat[len("resource"):]]

        filename = slashless_path.split('.')[-2] if '.' in slashless_path else slashless_path
        remaining = slashless_path
        for prefix_slashed in ['resource/particles/', 'resource/materials/', 'resource/models/',
                               'resource/sounds/', 'resource/textures/', 'resource/scripts/',
                               'particles/', 'materials/', 'models/', 'sounds/', 'textures/']:
            if remaining.startswith(prefix_slashed):
                remaining = remaining[len(prefix_slashed):]
                break
        
        ext = ext_match.group(0)
        filename_with_ext = remaining
        if remaining.endswith(ext):
            stem = remaining[:-len(ext)]
            best_filename = stem
            for marker in ['econ', 'heroes', 'items', 'seasonal', 'test', 'default', 'core',
                           'particles', 'materials', 'models', 'sounds', 'textures', 'scripts',
                           'panorama', 'shaders', 'ui', 'maps', 'cfg', 'events', 'resource',
                           'ambient', 'ability', 'attack', 'cast', 'hit', 'modifier', 'projectile',
                           'aura', 'spawn', 'death', 'kill', 'buff', 'debuff', 'trail', 'effect']:
                idx = stem.rfind(marker)
                if idx > 0:
                    candidate = stem[idx + len(marker):]
                    if candidate and len(candidate) > 2:
                        best_filename = candidate
                        break
            filename_with_ext = best_filename + ext
        
        candidates = []
        filename_lower = filename_with_ext.lower()
        
        for reader in self.vpk_readers:
            for fp in reader.files:
                if fp.endswith('/' + filename_lower) or fp == filename_lower:
                    score = 0
                    slashless_parts = slashless_path.replace('/', '').lower()
                    fp_parts = fp.replace('/', '').lower()
                    for i in range(min(len(slashless_parts), len(fp_parts))):
                        if slashless_parts[i] == fp_parts[i]:
                            score += 1
                        else:
                            break
                    candidates.append((score, fp))
        
        if candidates:
            candidates.sort(key=lambda x: -x[0])
            best = candidates[0]
            if best[0] > 3:
                return best[1]
        
        stem_only = filename_with_ext.rsplit('.', 1)[0]
        for reader in self.vpk_readers:
            for fp in reader.files:
                fp_stem = fp.rsplit('/', 1)[-1].rsplit('.', 1)[0]
                if fp_stem.lower() == stem_only.lower():
                    return fp
        return None
    
    def _parse_material_deps(self, data: bytes, resources: Dict[str, bytes], processed: Set[str], depth: int, max_depth: int, item_short: str = "", hero_short: str = ""):
        text = data.decode('utf-8', errors='ignore')
        patterns = [
            r'(textures/[^\x00\n\r\t"\'<>|*?{}]+\.(?:vtex|vtex_c|vtf|png))',
            r'(materials/[^\x00\n\r\t"\'<>|*?{}]+\.(?:vtex|vtex_c|vtf|png))',
            r'([a-z_\-/0-9]+\.(?:vtex_c|vtex|vtf|png))',
        ]
        for pattern in patterns:
            for match in re.finditer(pattern, text, re.IGNORECASE):
                ref_path = match.group(1).lower()
                if ref_path not in processed and not self._is_junk_path(ref_path):
                    self._extract_recursive(ref_path, resources, processed, depth, max_depth)
        
        raw = data
        for ext in [b'.vtex', b'.vtex_c', b'.vtf', b'.png', b'.vmat', b'.vmat_c']:
            idx = 0
            while True:
                idx = raw.find(ext, idx)
                if idx == -1: break
                start = idx
                while start > 0:
                    c = raw[start-1:start]
                    bv = c[0] if c else 0
                    if bv < 0x20 or bv > 0x7e: break
                    if chr(bv) not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_/.-': break
                    start -= 1
                try:
                    path_str = raw[start:idx + len(ext)].decode('ascii')
                    if '/' in path_str and len(path_str) > 5: 
                        if not self._is_junk_path(path_str.lower()):
                            self._extract_recursive(path_str.lower(), resources, processed, depth, max_depth)
                    elif len(path_str) > 10:
                        reconstructed = self._reconstruct_slashless_path(path_str.lower())
                        if reconstructed not in processed and not self._is_junk_path(reconstructed):
                            self._extract_recursive(reconstructed, resources, processed, depth, max_depth)
                except: pass
                idx += len(ext)
    
    def _parse_particle_deps(self, data: bytes, resources: Dict[str, bytes], processed: Set[str],
                              depth: int, max_depth: int, item_short: str = "", hero_short: str = ""):
        refs = self._scan_raw_refs(data)
        self._resolve_and_extract_refs(refs, resources, processed, depth, max_depth)
    
    def find_frost_particles(self) -> Dict[str, str]:
        results = {}
        search_terms = ["frost", "frostivus", "frostbloom", "ice_frost", "winter_frost", "snow", "frozen", "ice", "winter", "glacial", "blizzard", "freeze"]
        slot_keywords = ["weapon", "head", "back", "shoulder", "armor", "ambient", "aura", "global", "belt", "neck", "arms", "legs"]
        for reader in self.vpk_readers:
            for filepath in reader.files:
                if not filepath.endswith((".vpcf", ".vpcf_c")) or "particles" not in filepath: continue
                fp_lower = filepath.lower()
                if not any(term in fp_lower for term in search_terms): continue
                for kw in slot_keywords:
                    if kw in fp_lower:
                        key = kw if kw != "ambient" else "global"
                        if key not in results: results[key] = filepath
                        break
                else:
                    if "global" not in results: results["global"] = filepath
        log.info(f"Dynamic frost particles found: {len(results)}")
        return results
    
    def find_all_weather_particles(self) -> List[str]:
        results = set()
        for reader in self.vpk_readers:
            for filepath in reader.files:
                if "weather" in filepath and filepath.endswith((".vpcf", ".vpcf_c")) and "particles" in filepath:
                    results.add(filepath)
        return list(results)
    
    def find_water_materials(self) -> List[str]:
        water_files = set()
        for reader in self.vpk_readers:
            for filepath in reader.files:
                fp_lower = filepath.lower()
                if not fp_lower.endswith((".vmat_c", ".vmat", ".vmt_c", ".vmt")): continue
                stem = Path(fp_lower).stem.lower()
                if "water" in stem or "river" in stem:
                    if "materials/" in fp_lower: water_files.add(filepath)
                    if "maps/" in fp_lower and "water" in fp_lower: water_files.add(filepath)
                if "materials/terrain" in fp_lower and ("water" in fp_lower or "river" in fp_lower):
                    water_files.add(filepath)
                if "materials/water" in fp_lower: water_files.add(filepath)
                if "dota_water" in fp_lower or "hero_water" in fp_lower: water_files.add(filepath)
        return sorted(water_files)
    
    def find_background_files(self) -> List[str]:
        results = set()
        for reader in self.vpk_readers:
            for filepath in reader.files:
                fp_lower = filepath.lower()
                if "panorama" in fp_lower and "background" in fp_lower:
                    if fp_lower.endswith((".vtex_c", ".vtex", ".png", ".vtf", ".jpg", ".jpeg", ".webm", ".usm")):
                        results.add(filepath)
                if "panorama" in fp_lower and "dashboard" in fp_lower and "background" in fp_lower:
                    results.add(filepath)
                if "panorama" in fp_lower and "videos/" in fp_lower:
                    if fp_lower.endswith((".webm", ".usm")):
                        if "background" in fp_lower or "menu" in fp_lower or "dashboard" in fp_lower:
                            results.add(filepath)
                if "panorama" in fp_lower and "hero" in fp_lower and "background" in fp_lower:
                    if fp_lower.endswith((".vtex_c", ".vtex", ".png", ".vtf")):
                        results.add(filepath)
                if "panorama" in fp_lower and ("seasonal" in fp_lower or "event" in fp_lower):
                    if "background" in fp_lower and fp_lower.endswith((".vtex_c", ".png", ".webm")):
                        results.add(filepath)
        return sorted(results)

