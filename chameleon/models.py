from .common import *
# ==============================================================================
# DATA CLASSES
# ==============================================================================

@dataclass
class AbilityOverride:
    ability_id: str = ""
    icon: str = ""
    particles: List[str] = field(default_factory=list)
    projectiles: List[str] = field(default_factory=list)
    sounds: List[str] = field(default_factory=list)
    cast_effect: str = ""
    hit_effect: str = ""
    modifier_effect: str = ""
    raw_data: dict = field(default_factory=dict)

@dataclass 
class StyleDefinition:
    style_id: int = 0
    name: str = "Default"
    model_player: str = ""
    asset: str = ""
    particles: List[str] = field(default_factory=list)
    models: List[str] = field(default_factory=list)
    materials: List[str] = field(default_factory=list)
    textures: List[str] = field(default_factory=list)
    icons: List[str] = field(default_factory=list)
    ability_overrides: List[AbilityOverride] = field(default_factory=list)
    raw_data: dict = field(default_factory=dict)

@dataclass
class SkinItem:
    item_id: int
    name: str
    prefab: str = ""
    rarity: str = ""
    used_by_hero: str = ""
    visual_assets: List[str] = field(default_factory=list)
    is_arcana: bool = False
    is_persona: bool = False
    is_immortal: bool = False
    is_bugged: bool = False
    icon_path: str = ""
    particle_effect: str = ""
    item_slot: str = ""
    item_type: str = ""
    quality: str = ""
    category: str = ""
    slots: List[str] = field(default_factory=list)
    model_paths: List[str] = field(default_factory=list)
    material_paths: List[str] = field(default_factory=list)
    particle_paths: List[str] = field(default_factory=list)
    animation_paths: List[str] = field(default_factory=list)
    texture_paths: List[str] = field(default_factory=list)
    sound_paths: List[str] = field(default_factory=list)
    model_player: str = ""
    styles: List[StyleDefinition] = field(default_factory=list)
    ability_overrides: List[AbilityOverride] = field(default_factory=list)
    icons: Dict[str, str] = field(default_factory=dict)
    asset_modifiers: List[dict] = field(default_factory=list)
    is_loading_screen: bool = False
    is_effigy: bool = False
    is_music: bool = False
    is_tower: bool = False
    is_base: bool = False
    is_fountain: bool = False
    is_gem: bool = False
    gem_type: str = ""
    gem_particle: str = ""
    gem_color: str = ""
    socketable_slots: List[str] = field(default_factory=list)
    terrain_type: str = ""
    terrain_resource_path: str = ""
    weather_particle_path: str = ""
    courier_model_path: str = ""
    is_announcer: bool = False
    is_mega_kills: bool = False
    raw_item_data: dict = field(default_factory=dict)
    def_index: str = ""
    class_name: str = ""
    internal_name: str = ""
    localized_name: str = ""

# ==============================================================================
# RESOURCE RESOLVER — VPK extraction with deep dependency parsing
# ==============================================================================

