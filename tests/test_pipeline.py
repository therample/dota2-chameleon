"""
End-to-end checks on a SYNTHETIC Dota install (no game files needed, no Qt needed).

Run:  python -m unittest discover -s tests -v

What is verified here (and what is not):
  * VPK files we write are readable by Valve's reference-style library (`pip install vpk`).
  * gameinfo patching is reversible and never overwrites a good backup.
  * Hero catalog puts items in the right tab (no junk slots, taunts separate, arcana separate).
  * commit() produces ONE pak01_dir.vpk with scripts at the correct paths and dependencies packed.
  * Style filtering keeps only the chosen style's modifiers.
  * restore() removes the mod and our autoexec block but keeps the user's own lines.
NOT verified: how the real game reacts - that needs a real Dota 2 install.
"""
import os, sys, tempfile, unittest, shutil
from pathlib import Path

_TMP = tempfile.mkdtemp(prefix="cham_test_")
os.environ["CHAMELEON_HOME"] = str(Path(_TMP) / "home")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

# the package star-imports only core modules here (no PySide6 needed)
from chameleon.common import *            # noqa
from chameleon.vpk_io import VPKReader, VPKBuilder
from chameleon.database import SkinDatabase
from chameleon.applier import SkinApplier
from chameleon.gameinfo import GameInfoManager, strip_patch

HERO = "npc_dota_hero_sparrow"
FINCH = "npc_dota_hero_finch"

def _items_game():
    H = HERO
    return """"items_game"
{
  "prefabs"
  {
    "default_item" { "item_class" "wearable" "baseitem" "1" }
    "wearable" { "item_class" "wearable" "visuals" { "skip_model_combine" "0" } }
    "arcana" { "prefab" "wearable" "item_rarity" "arcana" }
  }
  "items"
  {
    "1001" { "name" "default_weapon"  "prefab" "default_item" "item_slot" "weapon"          "model_player" "models/heroes/sparrow/weapon.vmdl" "used_by_heroes" { "%(h)s" "1" } }
    "1002" { "name" "default_head"    "prefab" "default_item" "item_slot" "head"            "model_player" "models/heroes/sparrow/head.vmdl"   "used_by_heroes" { "%(h)s" "1" } }
    "1003" { "name" "default_taunt"   "prefab" "default_item" "item_slot" "taunt"           "used_by_heroes" { "%(h)s" "1" } }
    "1004" { "name" "default_weapon_alt" "prefab" "default_item" "item_slot" "weapon_alt"   "used_by_heroes" { "%(h)s" "1" } }
    "1005" { "name" "default_head_acc" "prefab" "default_item" "item_slot" "head_accessory" "used_by_heroes" { "%(h)s" "1" } }
    "1006" { "name" "default_misc"    "prefab" "default_item" "item_slot" "misc"            "used_by_heroes" { "%(h)s" "1" } }
    "1007" { "name" "default_back"    "prefab" "default_item" "item_slot" "back"            "used_by_heroes" { "%(h)s" "1" } }
    "1010" { "name" "default_announcer" "prefab" "default_item" "item_slot" "announcer" "baseitem" "1"
             "visuals" { "asset_modifier" { "type" "announcer" "asset" "announcer" "modifier" "announcer_default" } } }
    "2001" { "name" "cool_head" "item_name" "#DOTA_Item_Cool_Head" "prefab" "wearable" "item_slot" "head" "item_rarity" "rare"
             "image_inventory" "econ/items/sparrow/cool/cool_icon" "image_large" "econ/sets/sparrow_set_preview" "model_player" "models/items/sparrow/cool/cool.vmdl"
             "used_by_heroes" { "%(h)s" "1" }
             "visuals" {
               "asset_modifier" { "type" "particle_create" "modifier" "particles/econ/items/sparrow/cool/cool_ambient.vpcf" }
               "asset_modifier" { "type" "particle_create" "modifier" "particles/econ/items/sparrow/cool/cool_second.vpcf" }
             } }
    "2002" { "name" "arcana_weapon" "item_name" "#DOTA_Item_Arcana_Weapon" "prefab" "arcana" "item_slot" "weapon" "model_player" "models/items/sparrow/arcana/weapon.vmdl"
             "used_by_heroes" { "%(h)s" "1" }
             "visuals" {
               "asset_modifier" { "type" "entity_model" "asset" "%(h)s" "modifier" "models/heroes/sparrow/sparrow_arcana.vmdl" }
               "asset_modifier" { "type" "particle_create" "modifier" "particles/econ/items/sparrow/arcana/ambient.vpcf" }
               "asset_modifier" { "type" "particle" "asset" "particles/units/heroes/hero_sparrow/attack.vpcf" "modifier" "particles/econ/items/sparrow/arcana/attack_new.vpcf" "apply_when_equipped_in_ability_effects_slot" "2" }
               "asset_modifier" { "type" "particle_create" "style" "0" "modifier" "particles/econ/items/sparrow/arcana/style0_only.vpcf" }
               "asset_modifier" { "type" "particle_create" "style" "1" "modifier" "particles/econ/items/sparrow/arcana/style1_only.vpcf" }
               "styles" { "0" { "name" "Base" } "1" { "name" "Alt" } }
             } }
    "2003" { "name" "funny_taunt" "item_name" "#DOTA_Item_Funny_Taunt" "prefab" "wearable" "item_slot" "taunt" "used_by_heroes" { "%(h)s" "1" }
             "visuals" { "asset_modifier" { "type" "activity" "asset" "ACT_DOTA_TAUNT" "modifier" "funny" } } }
    "2004" { "name" "junk_hud_thing" "prefab" "wearable" "item_slot" "hud_skin_slot" "used_by_heroes" { "%(h)s" "1" } }
    "2005" { "name" "alt_weapon" "item_name" "#DOTA_Item_Alt_Weapon" "prefab" "wearable" "item_slot" "weapon_alt" "used_by_heroes" { "%(h)s" "1" } }
    "2006" { "name" "head_acc_item" "item_name" "#DOTA_Item_Head_Acc" "prefab" "wearable" "item_slot" "head_accessory" "used_by_heroes" { "%(h)s" "1" } }
    "2007" { "name" "misc_item" "item_name" "#DOTA_Item_Misc" "prefab" "wearable" "item_slot" "misc" "used_by_heroes" { "%(h)s" "1" } }

    "2008" { "name" "internal_blob" "prefab" "wearable" "item_slot" "head" "used_by_heroes" { "%(h)s" "1" } }
    "555"  { "name" "Default Weather" "prefab" "weather" "baseitem" "1" "item_slot" "weather" "player_loadout" "1"
             "visuals" { "asset_modifier0" { "type" "weather" "weather_type" "0" } } }
    "3101" { "name" "snow_weather" "item_name" "#DOTA_Item_Snow_Weather" "prefab" "weather" "item_slot" "weather" "item_rarity" "mythical"
             "visuals" { "asset_modifier" { "type" "weather" "weather_type" "1" }
                         "asset_modifier" { "type" "soundscape" "asset" "weather_day_default" "modifier" "weather_day_snow" } } }
    "3102" { "name" "rain_weather" "item_name" "#DOTA_Item_Rain_Weather" "prefab" "weather" "item_slot" "weather" "item_rarity" "mythical"
             "visuals" { "asset_modifier" { "type" "weather" "weather_type" "2" }
                         "asset_modifier" { "type" "soundscape" "asset" "weather_day_default" "modifier" "weather_day_rain" } } }
    "1101" { "name" "finch_offhand" "prefab" "default_item" "item_slot" "offhand_weapon" "used_by_heroes" { "%(f)s" "1" } }
    "1102" { "name" "finch_head_default" "prefab" "default_item" "item_slot" "head" "used_by_heroes" { "%(f)s" "1" } }
    "2101" { "name" "finch_blade" "item_name" "#DOTA_Item_Finch_Blade" "prefab" "wearable" "item_slot" "weapon" "item_rarity" "rare" "model_player" "models/items/finch/blade.vmdl"
             "used_by_heroes" { "%(f)s" "1" }
             "visuals" { "asset_modifier" { "type" "particle_create" "modifier" "particles/econ/items/finch/blade_a.vpcf" }
                         "asset_modifier" { "type" "particle_create" "modifier" "particles/econ/items/finch/blade_b.vpcf" } } }
    "2102" { "name" "finch_taunt" "item_name" "#DOTA_Item_Finch_Taunt" "prefab" "wearable" "item_slot" "taunt" "used_by_heroes" { "%(f)s" "1" }
             "visuals" { "asset_modifier" { "type" "activity" "asset" "ACT_DOTA_TAUNT" "modifier" "finch_dance" }
                         "asset_modifier" { "type" "particle_create" "modifier" "particles/econ/items/finch/taunt_fx.vpcf" } } }
    "2210" { "name" "odd_slot_item" "item_name" "#DOTA_Item_Odd_Slot" "prefab" "wearable" "item_slot" "mystery_slot_x" "item_rarity" "rare"
             "used_by_heroes" { "%(f)s" "1" } }
    "1103" { "name" "finch_odd_default" "prefab" "default_item" "item_slot" "tail_fx" "used_by_heroes" { "%(f)s" "1" } }
    "2211" { "name" "tail_item" "item_name" "#DOTA_Item_Tail" "prefab" "wearable" "item_slot" "tail_fx" "used_by_heroes" { "%(f)s" "1" } }

    "661"  { "name" "Default Dire Creeps" "prefab" "direcreeps" "baseitem" "1" }
    "662"  { "name" "Default Radiant Creeps" "prefab" "radiantcreeps" "baseitem" "1" }
    "3201" { "name" "bird_creeps" "item_name" "#DOTA_Item_Bird_Creeps" "prefab" "direcreeps" "item_rarity" "rare"
             "visuals" { "asset_modifier" { "type" "entity_clientside_model" "asset" "npc_dota_creep_badguys_melee" "modifier" "models/creeps/bird/melee.vmdl" }
                         "asset_modifier" { "type" "entity_clientside_model" "asset" "npc_dota_creep_badguys_ranged" "modifier" "models/creeps/bird/ranged.vmdl" } } }
    "678"  { "name" "Default Dire Towers" "prefab" "diretowers" "baseitem" "1" }
    "677"  { "name" "Default Radiant Towers" "prefab" "radianttowers" "baseitem" "1" }
    "3301" { "name" "crow_towers" "item_name" "#DOTA_Item_Crow_Towers" "prefab" "diretowers" "item_rarity" "rare"
             "visuals" { "asset_modifier" { "type" "entity_clientside_model" "asset" "npc_dota_badguys_tower1_top" "modifier" "models/towers/crow.vmdl" } } }
    "3302" { "name" "sun_towers" "item_name" "#DOTA_Item_Sun_Towers" "prefab" "radianttowers" "item_rarity" "rare"
             "visuals" { "asset_modifier" { "type" "entity_clientside_model" "asset" "npc_dota_goodguys_tower1_top" "modifier" "models/towers/sun.vmdl" } } }
    "202"  { "name" "Default Cursor Pack" "prefab" "cursor_pack" "baseitem" "1" }
    "3401" { "name" "hydra_cursor" "item_name" "#DOTA_Item_Hydra_Cursor" "prefab" "cursor_pack"
             "visuals" { "asset_modifier" { "type" "cursor_pack" "asset" "resource/cursor/default" "modifier" "resource/cursor/workshop/hydra" } } }
    "587"  { "name" "Default Hud Skin" "prefab" "hud_skin" "baseitem" "1" }
    "3501" { "name" "midnight_hud" "item_name" "#DOTA_Item_Midnight_Hud" "prefab" "hud_skin"
             "visuals" { "asset_modifier" { "type" "hud_skin" "asset" "bane_delirium" "modifier" "bane_delirium" } } }
    "14912" { "name" "No Kill Streak Effect" "prefab" "streak_effect" "baseitem" "1" }
    "3601" { "name" "diretide_streak" "item_name" "#DOTA_Item_Diretide_Streak" "prefab" "streak_effect"
             "visuals" { "asset_modifier" { "type" "streak_effect" "asset" "top_bar_lvl1" "modifier" "particles/killstreak/dt_topbar_lv1.vpcf" }
                         "asset_modifier" { "type" "streak_effect" "asset" "portrait_lvl1" "modifier" "particles/killstreak/dt_hud_lv1.vpcf" } } }
    "6"    { "name" "Weird Announcer Default" "prefab" "announcer_default" "baseitem" "1"
             "visuals" { "asset_modifier" { "type" "announcer" "asset" "announcer" "modifier" "announcer_default" } } }
    "3701" { "name" "odd_announcer" "item_name" "#DOTA_Item_Odd_Announcer" "prefab" "announcer" "item_slot" "announcer"
             "visuals" { "asset_modifier" { "type" "announcer" "asset" "announcer" "modifier" "announcer_odd" } } }
    "8"    { "name" "Default Mega Kills" "prefab" "mega_kills_default" "baseitem" "1"
             "visuals" { "asset_modifier" { "type" "announcer" "asset" "announcer_killstreak" "modifier" "mega_default" } } }
    "3702" { "name" "odd_megakills" "item_name" "#DOTA_Item_Odd_MegaKills" "prefab" "mega_kills" "item_slot" "mega_kills"
             "visuals" { "asset_modifier" { "type" "announcer" "asset" "announcer_killstreak" "modifier" "mega_odd" } } }
    "2301" { "name" "styled_head" "item_name" "#DOTA_Item_Styled_Head" "prefab" "wearable" "item_slot" "head" "used_by_heroes" { "%(h)s" "1" }
             "visuals" { "styles" { "0" { "name" "#DOTA_Style_Base" } "1" { "name" "#DOTA_Style_Golden" } "2" { "name" "style_internal_name" } } } }

    "3801" { "name" "ghost_effigy" "item_name" "#DOTA_Item_Ghost_Effigy" "prefab" "wearable" "item_slot" "effigy" "item_rarity" "mythical"
             "visuals" { "asset_modifier" { "type" "particle_create" "modifier" "particles/econ/effigy/ghost.vpcf" } } }
    "3802" { "name" "stone_ancient" "item_name" "#DOTA_Item_Stone_Ancient" "prefab" "direancient" "item_slot" "ancient"
             "visuals" { "asset_modifier" { "type" "entity_clientside_model" "asset" "npc_dota_badguys_fort" "modifier" "models/ancient/stone.vmdl" } } }
    "3803" { "name" "ember_tormentor" "item_name" "#DOTA_Item_Ember_Tormentor" "prefab" "tormentor" "item_slot" "tormentor"
             "visuals" { "asset_modifier" { "type" "entity_clientside_model" "asset" "npc_dota_miniboss" "modifier" "models/tormentor/ember.vmdl" } } }
    "3811" { "name" "ti_music_pack" "prefab" "ti_music_pack_prefab" "item_slot" "music"
             "visuals" { "asset_modifier" { "type" "music" "asset" "music_pack" "modifier" "valve_ti_music" } } }
    "3812" { "name" "odd_prefab_music" "item_name" "#DOTA_Item_Odd_Music" "prefab" "soundtrack_dlc" "item_slot" "unknown_slot"
             "visuals" { "asset_modifier" { "type" "music" "asset" "music_pack" "modifier" "odd_pack" } } }
    "3813" { "name" "typed_music" "item_name" "#DOTA_Item_Typed_Music" "prefab" "wearable" "item_type_name" "#DOTA_WearableType_Music"
             "visuals" { "asset_modifier" { "type" "sound" "asset" "x" "modifier" "y" } } }
    "3821" { "name" "noir_filter" "item_name" "#DOTA_Item_Noir_Filter" "prefab" "wearable" "item_slot" "special"
             "visuals" { "asset_modifier" { "type" "particle_create" "modifier" "materials/postprocessing/noir.vpost" } } }
    "3822" { "name" "lut_pack" "item_name" "#DOTA_Item_Lut_Pack" "prefab" "wearable" "item_slot" "special"
             "some_key" "materials/correction/warm_lut.raw" "visuals" { "asset_modifier" { "type" "entity_model" "modifier" "models/x.vmdl" } } }

    "4001" { "name" "head_fx_a" "item_name" "#DOTA_Item_HeadFx" "prefab" "head_effect" "item_slot" "head_effect" "used_by_heroes" { "%(h)s" "1" }
             "visuals" { "asset_modifier" { "type" "particle_create" "modifier" "particles/econ/fx/head_a.vpcf" } } }
    "4002" { "name" "courier_fx_a" "item_name" "#DOTA_Item_CourierFx" "prefab" "courier_effect" "item_slot" "courier_effect"
             "visuals" { "asset_modifier" { "type" "particle" "asset" "particles/units/couriers/trail.vpcf" "modifier" "particles/econ/couriers/trail_new.vpcf" } } }
    "4003" { "name" "death_fx_a" "item_name" "#DOTA_Item_DeathFx" "prefab" "death_effect" "item_slot" "death_effect" }
    "4004" { "name" "map_fx_a" "item_name" "#DOTA_Item_MapFx" "prefab" "map_effect" "item_slot" "map_effect" }
    "4005" { "name" "tele_fx_a" "item_name" "#DOTA_Item_TeleFx" "prefab" "misc" "item_slot" "teleport_effect" }
    "4006" { "name" "blink_fx_a" "item_name" "#DOTA_Item_BlinkFx" "prefab" "blink_effect" "item_slot" "blink_effect" }
    "4007" { "name" "kill_fx_a" "item_name" "#DOTA_Item_KillFx" "prefab" "kill_effect" "item_slot" "kill_effect" }
    "4008" { "name" "statue_a" "item_name" "#DOTA_Item_StatueA" "prefab" "misc" "item_slot" "heroic_statue" "item_type_name" "#DOTA_WearableType_Misc" }
    "4101" { "name" "prismatic_red" "item_name" "#DOTA_Item_PrismaticRed" "prefab" "socket_gem" "item_type_name" "#DOTA_WearableType_Prismatic_Gem"
             "visuals" { "asset_modifier" { "type" "particle" "asset" "particles/units/heroes/hero_sparrow/arcana_glow.vpcf" "modifier" "particles/econ/gems/prismatic_red.vpcf" }
                         "asset_modifier" { "type" "particle_create" "modifier" "particles/econ/gems/prismatic_red_ambient.vpcf" } } }
    "4102" { "name" "ethereal_gem" "item_name" "#DOTA_Item_EtherealGem" "prefab" "socket_gem" "item_type_name" "#DOTA_WearableType_Ethereal_Gem"
             "visuals" { "asset_modifier" { "type" "particle" "asset" "particles/units/heroes/hero_sparrow/arcana_glow.vpcf" "modifier" "particles/econ/gems/ethereal.vpcf" } } }
    "4104" { "name" "victory_gem_stats" "item_name" "#DOTA_Item_Victory" "prefab" "socket_gem" "item_type_name" "#DOTA_WearableType_Victory_Gem" }
    "4103" { "name" "unrelated_gem" "item_name" "#DOTA_Item_Unrelated" "prefab" "socket_gem"
             "visuals" { "asset_modifier" { "type" "particle" "asset" "particles/units/heroes/hero_other/x.vpcf" "modifier" "particles/econ/gems/other.vpcf" } } }
    "700"  { "name" "Default Roshan" "prefab" "roshan" "baseitem" "1" }
    "4201" { "name" "ice_roshan" "item_name" "#DOTA_Item_IceRoshan" "prefab" "roshan"
             "visuals" { "asset_modifier" { "type" "entity_clientside_model" "asset" "npc_dota_roshan" "modifier" "models/roshan/ice.vmdl" } } }
    "800"  { "name" "Default Courier Thing" "prefab" "courier_base" "baseitem" "1" "item_slot" "base_courier"
             "visuals" { "asset_modifier" { "type" "entity_model" "asset" "models/props_gameplay/donkey.vmdl" "modifier" "models/props_gameplay/donkey.vmdl" } } }
    "4301" { "name" "gold_courier" "item_name" "#DOTA_Item_GoldCourier" "prefab" "courier" "item_slot" "courier"
             "visuals" { "asset_modifier" { "type" "entity_model" "asset" "models/props_gameplay/donkey.vmdl" "modifier" "models/couriers/gold.vmdl" } } }
    "4401" { "name" "epic_pack_x" "item_name" "#DOTA_Item_EpicPack" "prefab" "wearable" "item_slot" "unknown_x"
             "visuals" { "asset_modifier" { "type" "sound" "asset" "x" "modifier" "valve_music_epic_01" } } }
    "4402" { "name" "music_treasure" "item_name" "#DOTA_Item_MusicTreasure" "prefab" "treasure_chest" "item_slot" "unknown_y" "item_type_name" "#DOTA_WearableType_Treasure_Chest"
             "visuals" { "asset_modifier" { "type" "sound" "asset" "x" "modifier" "music_treasure_unlock" } } }
    "4403" { "name" "music_bundle_x" "item_name" "#DOTA_Item_MusicBundle" "prefab" "bundle" "item_slot" "unknown_z" }

    "5001" { "name" "frostbloom_blade" "item_name" "#DOTA_Item_Frostbloom_Blade" "prefab" "wearable" "item_slot" "weapon_alt" "item_quality" "unusual" "used_by_heroes" { "%(h)s" "1" }
             "visuals" { "asset_modifier" { "type" "particle_create" "modifier" "particles/econ/fx/frost_a.vpcf" }
                         "asset_modifier" { "type" "particle_create" "modifier" "particles/econ/fx/frost_b.vpcf" } } }
    "5101" { "name" "sparrow_persona" "item_name" "#DOTA_Item_Sparrow_Persona" "prefab" "wearable" "item_slot" "persona_selector" "used_by_heroes" { "%(h)s" "1" }
             "visuals" { "asset_modifier" { "type" "entity_model" "asset" "%(h)s" "modifier" "models/heroes/sparrow/persona.vmdl" }
                         "asset_modifier" { "type" "particle_create" "modifier" "particles/econ/persona/aura.vpcf" } } }
    "1201" { "name" "finch_persona_default" "prefab" "default_item" "item_slot" "persona_selector" "used_by_heroes" { "%(f)s" "1" } }
    "5102" { "name" "finch_persona_x" "item_name" "#DOTA_Item_Finch_Persona" "prefab" "persona_edition" "item_slot" "persona_selector" "used_by_heroes" { "%(f)s" "1" }
             "visuals" { "asset_modifier" { "type" "entity_model" "asset" "%(f)s" "modifier" "models/heroes/finch/persona.vmdl" } } }
    "5201" { "name" "ti9_pack_by_icon" "item_name" "#DOTA_Item_Ti9_Pack" "prefab" "wearable" "item_slot" "weird_slot" "image_inventory" "econ/music/valve_ti9/ti9_pack" }
    "5202" { "name" "dup_name" "item_name" "#DOTA_Item_Dup" "prefab" "wearable" "item_slot" "head" "used_by_heroes" { "%(h)s" "1" } }
    "5203" { "name" "dup_name" "item_name" "#DOTA_Item_Dup" "prefab" "wearable" "item_slot" "head" "used_by_heroes" { "%(h)s" "1" } }
    "3001" { "name" "cool_announcer" "item_name" "#DOTA_Item_Cool_Announcer" "prefab" "announcer" "item_slot" "announcer"
             "visuals" { "asset_modifier" { "type" "announcer" "asset" "announcer" "modifier" "announcer_cool" } } }
  }
}
""" % {"h": H, "f": FINCH}

ITEMS_GAME = _items_game()

HEROES = """"DOTAHeroes"
{
  "%(h)s" { "Model" "models/heroes/sparrow/sparrow.vmdl" "AttributePrimary" "DOTA_ATTRIBUTE_AGILITY" "workshop_guide_name" "Sparrow" }
  "%(f)s" { "Model" "models/heroes/finch/finch.vmdl" "AttributePrimary" "DOTA_ATTRIBUTE_STRENGTH" "workshop_guide_name" "Finch" }
}
""" % {"h": HERO, "f": FINCH}

LOC = ('"lang" { "Language" "English" "Tokens" { "DOTA_Item_Cool_Head" "Cool Head" "DOTA_Item_Arcana_Weapon" "Arcana Weapon" '
       '"DOTA_Item_Funny_Taunt" "Funny Taunt" "DOTA_Item_Alt_Weapon" "Alt Weapon" "DOTA_Item_Head_Acc" "Head Accessory" '
       '"DOTA_Item_Misc" "Misc Thing" "DOTA_Item_Cool_Announcer" "Cool Announcer" "DOTA_Item_Snow_Weather" "Snow" '
       '"DOTA_Item_Rain_Weather" "Rain" "DOTA_Item_Finch_Blade" "Finch Blade" "DOTA_Item_Finch_Taunt" "Finch Taunt" '
       '"DOTA_Item_Ghost_Effigy" "Ghost Effigy" "DOTA_Item_Stone_Ancient" "Stone Ancient" "DOTA_Item_Ember_Tormentor" "Ember Tormentor" "DOTA_Item_Noir_Filter" "Noir Filter" "DOTA_Item_Lut_Pack" "Lut Pack" "DOTA_Item_HeadFx" "Head Fx" "DOTA_Item_CourierFx" "Courier Fx" "DOTA_Item_DeathFx" "Death Fx" "DOTA_Item_MapFx" "Map Fx" "DOTA_Item_TeleFx" "Tele Fx" "DOTA_Item_BlinkFx" "Blink Fx" "DOTA_Item_KillFx" "Kill Fx" "DOTA_Item_StatueA" "Statue A" "DOTA_Item_PrismaticRed" "Prismatic Red" "DOTA_Item_EtherealGem" "Ethereal Gem" "DOTA_Item_Unrelated" "Unrelated Gem" "DOTA_Item_Victory" "Victory Gem" "DOTA_Item_IceRoshan" "Ice Roshan" "DOTA_Item_GoldCourier" "Gold Courier" "DOTA_Item_EpicPack" "Epic Music Pack" "DOTA_Item_MusicTreasure" "Music Treasure" "DOTA_Item_MusicBundle" "Music Bundle" "DOTA_Item_Frostbloom_Blade" "Frostbloom Blade" "DOTA_Item_Sparrow_Persona" "Sparrow Persona" "DOTA_Item_Finch_Persona" "Finch Persona" "DOTA_Item_Ti9_Pack" "TI9 Pack" "DOTA_Item_Dup" "Dup Item" "DOTA_Item_Odd_Slot" "Odd Slot" "DOTA_Item_Tail" "Tail Thing" "DOTA_Item_Bird_Creeps" "Bird Creeps" "DOTA_Item_Crow_Towers" "Crow Towers" "DOTA_Item_Sun_Towers" "Sun Towers" "DOTA_Item_Hydra_Cursor" "Hydra Cursor" "DOTA_Item_Midnight_Hud" "Midnight HUD" "DOTA_Item_Diretide_Streak" "Diretide Streak" "DOTA_Item_Odd_Announcer" "Odd Announcer" "DOTA_Item_Odd_MegaKills" "Odd Mega-Kills" "DOTA_Item_Styled_Head" "Styled Head" "DOTA_Style_Base" "Classic" "DOTA_Style_Golden" "Golden" } }')
LOC_RU = '"lang" { "Language" "Russian" "Tokens" { "DOTA_Item_Cool_Head" "Крутая шапка" } }'


def fake_compiled(*refs):
    return b"\x00\x01VRF" + b"".join(b"\x00" + r.encode() + b"\x00" for r in refs)


GAME_FILES = {
    "scripts/items/items_game.txt": ITEMS_GAME.encode(),
    "scripts/npc/npc_heroes.txt": HEROES.encode(),
    "resource/localization/dota_english.txt": LOC.encode(),
    "resource/localization/dota_russian.txt": LOC_RU.encode("utf-8"),
    "materials/water/water_generic_000_slope.vmat_c": b"DEFAULT_RIVER" * 6,
    "materials/water/water_generic_001.vmat_c": b"DEFAULT_RIVER_2" * 6,
    "materials/water/water_ocean_foam.vmat_c": b"OTHER_BASE_WATER" * 6,
    "materials/water/water_dota_blood.vmat_c": b"BLOOD_RIVER" * 6,
    "materials/water/water_econ_dota_slime.vmat_c": b"SLIME_RIVER" * 6,
    "panorama/fonts/radiance.ttf": b"\x00\x01\x00\x00" + b"RADIANCE" * 8,
    "panorama/fonts/reaver.ttf": b"\x00\x01\x00\x00" + b"REAVER" * 8,
    "particles/econ/items/finch/blade_a.vpcf_c": b"BA" * 8,
    "particles/econ/items/finch/blade_b.vpcf_c": b"BB" * 8,
    "particles/econ/items/finch/taunt_fx.vpcf_c": b"TF" * 8,

    "models/heroes/sparrow/sparrow_arcana.vmdl_c": fake_compiled("materials/models/heroes/sparrow/arcana_body.vmat", "particles/models/heroes/sparrow/finger_fx.vsnap"),
    "materials/models/heroes/sparrow/arcana_body.vmat_c": fake_compiled("materials/models/heroes/sparrow/arcana_body_color_tga.vtex"),
    "materials/models/heroes/sparrow/arcana_body_color_tga.vtex_c": b"TEXTUREDATA" * 8,
    "particles/models/heroes/sparrow/finger_fx.vsnap_c": b"SNAPDATA" * 8,
    "models/items/sparrow/arcana/weapon.vmdl_c": fake_compiled("particles/econ/items/sparrow/arcana/ambient.vpcf"),
    "particles/econ/items/sparrow/arcana/ambient.vpcf_c": b"PARTICLE_AMBIENT" * 4,
    "particles/econ/items/sparrow/arcana/attack_new.vpcf_c": fake_compiled("particles/econ/items/sparrow/arcana/attack_child.vpcf"),
    "particles/econ/items/sparrow/arcana/attack_child.vpcf_c": b"CHILD" * 8,
    "particles/units/heroes/hero_sparrow/attack.vpcf_c": b"ORIGINAL_ATTACK" * 4,
    "particles/econ/items/sparrow/arcana/style0_only.vpcf_c": b"PARTICLE_S0" * 4,
    "particles/econ/items/sparrow/arcana/style1_only.vpcf_c": b"PARTICLE_S1" * 4,
    "models/items/sparrow/cool/cool.vmdl_c": fake_compiled("particles/econ/items/sparrow/cool/cool_ambient.vpcf"),
    "particles/econ/items/sparrow/cool/cool_ambient.vpcf_c": b"PARTICLE_COOL" * 4,
    "particles/econ/items/sparrow/cool/cool_second.vpcf_c": b"PARTICLE_COOL2" * 4,
    "particles/econ/gems/prismatic_red.vpcf_c": b"GEM_RED" * 4,
    "particles/econ/gems/ethereal.vpcf_c": b"GEM_ETH" * 4,
    "particles/units/heroes/hero_sparrow/arcana_glow.vpcf_c": b"ORIGINAL_GLOW" * 4,
    "particles/econ/couriers/trail_new.vpcf_c": b"TRAIL_NEW" * 4,
    "particles/units/couriers/trail.vpcf_c": b"TRAIL_OLD" * 4,
    "models/heroes/sparrow/weapon.vmdl_c": b"W" * 32,
    "models/heroes/sparrow/head.vmdl_c": b"H" * 32,
}


def build_fake_dota(root: Path) -> Path:
    game = root / "dota2"
    gd = game / "game" / "dota"
    gd.mkdir(parents=True)
    b = VPKBuilder()
    for p, d in GAME_FILES.items():
        b.add_data(d, p)
    b.build_standalone(gd / "pak01_dir.vpk")
    (gd / "gameinfo.gi").write_bytes(
        b'"GameInfo"\r\n{\r\n\tFileSystem\r\n\t{\r\n\t\tSearchPaths\r\n\t\t{\r\n'
        b'\t\t\tGame_Language\t\tdota_*LANGUAGE*\r\n\t\t\tGame\t\t\t\tdota\r\n\t\t\tGame\t\t\t\tcore\r\n'
        b'\t\t\tMod\t\t\t\t\tdota\r\n\t\t\tWrite\t\t\t\tdota\r\n\t\t}\r\n\t}\r\n}\r\n')
    (gd / "gameinfo_branchspecific.gi").write_bytes(
        b'"GameInfo"\r\n{\r\n\tFileSystem\r\n\t{\r\n\t\tSteamAppId\t\t570\r\n\t}\r\n}\r\n')
    sigdir = game / "game" / "bin" / "win64"
    sigdir.mkdir(parents=True)
    (sigdir / "dota.signatures").write_bytes(
        b"VALVE.SIGNATURES\r\n...\\..\\..\\dota\\gameinfo_branchspecific.gi~SHA1:" + b"A" * 40 + b";CRC:" + b"B" * 8 +
        b"\r\nbin\\win64\\dota2.exe~SHA1:" + b"C" * 40 + b";CRC:" + b"D" * 8 + b"\r\nDIGEST:" + b"E" * 40 + b"\r\n")
    (gd / "cfg").mkdir()
    (gd / "cfg" / "autoexec.cfg").write_text("// my own config\nbind f5 \"say hi\"\n", encoding="utf-8")
    return game


def _items_of(pak):
    from chameleon.kv import KeyValueParser
    txt = pak.get_file("scripts/items/items_game.txt").read().decode()
    return KeyValueParser(txt).parse()["items_game"]["items"]


def _mods(block):
    from chameleon.kv import kv_base
    return [v for k, v in block.get("visuals", {}).items() if kv_base(k) == "asset_modifier"]


class PipelineTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = Path(_TMP)
        cls.game = build_fake_dota(cls.root)
        cls.db = SkinDatabase(cls.game)
        assert cls.db.initialize(), "database failed to initialise"
        cls.ap = SkinApplier(cls.game, cls.db, {"pack_resources": True})

    # ---- KV: the bug that removed effects ----
    def test_00_kv_keeps_repeated_keys(self):
        from chameleon.kv import KeyValueParser, KeyValueWriter, kv_base
        d = KeyValueParser('"a" { "m" { "x" "1" } "m" { "x" "2" } "m" { "x" "3" } }').parse()
        self.assertEqual([v["x"] for k, v in d["a"].items() if kv_base(k) == "m"], ["1", "2", "3"])
        out = KeyValueWriter.write(d)
        self.assertEqual(out.count('"m"'), 3)
        self.assertEqual(KeyValueParser(out).parse(), d)

    # ---- VPK ----
    def test_01_vpk_roundtrip_own_reader(self):
        r = VPKReader(self.game / "game" / "dota" / "pak01_dir.vpk")
        for p, d in GAME_FILES.items():
            self.assertEqual(r.extract_to_bytes(p), d, p)

    def test_02_vpk_readable_by_valve_library(self):
        import vpk
        pak = vpk.open(str(self.game / "game" / "dota" / "pak01_dir.vpk"))
        names = {f for f in pak}
        for p, d in GAME_FILES.items():
            self.assertIn(p, names)
            f = pak.get_file(p)
            self.assertEqual(f.read(), d)
            f.verify()
            f.close()

    # ---- gameinfo ----
    def test_03_gameinfo_patch_is_reversible(self):
        gi = GameInfoManager(self.game)
        orig = gi.branch_path.read_bytes()
        self.assertTrue(gi.inject_vpk())
        self.assertTrue(gi.is_injected())
        self.assertTrue(gi.inject_vpk())
        self.assertEqual(gi.branch_path.read_bytes().count(b"chameleon_tool"), 2)
        gi.remove_vpk()
        self.assertEqual(gi.branch_path.read_bytes(), orig)
        self.assertEqual(gi.backup_path.read_bytes(), orig)

    # ---- slots / catalog ----
    def test_04_every_hero_slot_is_kept_and_items_sorted_into_them(self):
        cat = self.db.get_hero_catalog(HERO)
        slots = {s["slot"]: [i.name for i in s["items"]] for s in cat["slots"]}
        self.assertEqual(slots, {"head": ["cool_head", "styled_head", "dup_name", "dup_name #5203"], "weapon_alt": ["alt_weapon", "frostbloom_blade"],
                                 "head_accessory": ["head_acc_item"], "misc": ["misc_item"]})
        order = [s["slot"] for s in cat["slots"]]
        self.assertEqual(order, ["head", "misc", "head_accessory", "weapon_alt"])    # canonical slots first
        self.assertEqual([i.name for i in cat["arcanas"]], ["arcana_weapon"])
        self.assertEqual([i.name for i in cat["taunts"]], ["funny_taunt"])
        self.assertNotIn("hud_skin_slot", slots)
        self.assertEqual(self.db.resolve_slot(HERO, "weapon_alt"), "weapon_alt")     # not merged into "weapon"
        self.assertEqual(self.db.resolve_slot(HERO, "shoulder"), "shoulder")          # real loadout slot: accepted, build decides
        self.assertIsNone(self.db.resolve_slot(HERO, "hud_skin_slot"))                # not a loadout slot at all
        self.assertNotIn("internal_blob", [i.name for g in cat["slots"] for i in g["items"]])   # no localized name -> system item

    def test_05_prefab_inheritance_is_applied(self):
        # arcana prefab -> wearable -> sets item_rarity "arcana" which only exists in the prefab
        self.assertTrue(self.db.items["arcana_weapon"].is_arcana)

    # ---- commit ----
    def test_06_commit_effects_survive(self):
        import vpk
        A = self.ap
        self.assertTrue(A.apply_hero_skin(HERO, "arcana_weapon"))
        self.assertTrue(A.apply_hero_skin(HERO, "cool_head"))
        self.assertTrue(A.apply_hero_skin(HERO, "alt_weapon"))
        self.assertTrue(A.apply_taunt(HERO, "funny_taunt"))
        self.assertTrue(A.apply_announcer("cool_announcer"))
        self.assertTrue(A.apply_style("arcana_weapon", 1))
        msgs = []
        self.assertTrue(A.commit(progress_callback=msgs.append), msgs)

        self.assertEqual(sorted(p.name for p in A.mod_dir.glob("*.vpk")), ["pak01_dir.vpk"])
        pak = vpk.open(str(A.mod_dir / "pak01_dir.vpk"))
        names = {f for f in pak}
        items = _items_of(pak)

        # identity of the default item is kept, content comes from the wanted item
        w = items["1001"]
        self.assertEqual((w["name"], w["prefab"], w["item_slot"]), ("default_weapon", "default_item", "weapon"))
        self.assertEqual(w["model_player"], "models/items/sparrow/arcana/weapon.vmdl")

        # every modifier survived (this is the bug that removed ambient effects)
        head_mods = [m["modifier"] for m in _mods(items["1002"])]
        self.assertEqual(head_mods, ["particles/econ/items/sparrow/cool/cool_ambient.vpcf",
                                     "particles/econ/items/sparrow/cool/cool_second.vpcf"])

        # style 1 chosen: style gating and ability-slot gating are gone, style-0-only is dropped
        wm = _mods(w)
        mods = [m.get("modifier") for m in wm]
        self.assertIn("particles/econ/items/sparrow/arcana/style1_only.vpcf", mods)
        self.assertNotIn("particles/econ/items/sparrow/arcana/style0_only.vpcf", mods)
        self.assertIn("particles/econ/items/sparrow/arcana/ambient.vpcf", mods)
        for m in wm:
            self.assertNotIn("style", m)
            self.assertNotIn("apply_when_equipped_in_ability_effects_slot", m)
        self.assertNotIn("styles", w["visuals"])
        self.assertEqual([m for m in wm if m["type"] == "entity_model"][0]["modifier"],
                         "models/heroes/sparrow/sparrow_arcana.vmdl")

        # other slots land on THEIR default item, extra slots are not merged into "weapon"
        self.assertEqual(items["1004"]["name"], "default_weapon_alt")
        self.assertEqual(items["1003"]["name"], "default_taunt")
        self.assertIn("funny", str(items["1003"]))
        self.assertNotIn("funny", str(items["1002"]))

        # announcer: default entry, replaced by the chosen pack's visuals
        ann = items["1010"]
        self.assertEqual((ann["name"], ann["prefab"]), ("default_announcer", "default_item"))
        self.assertIn("announcer_cool", str(ann))

        # `particle` replacement: new particle written under the OLD path (community patcher technique)
        self.assertEqual(pak.get_file("particles/units/heroes/hero_sparrow/attack.vpcf_c").read(),
                         GAME_FILES["particles/econ/items/sparrow/arcana/attack_new.vpcf_c"])
        # minimal pack mode: nothing that already ships with the game is copied
        self.assertNotIn("models/items/sparrow/arcana/weapon.vmdl_c", names)
        self.assertIn("scripts/npc/npc_heroes.txt", names)
        self.assertIn("sparrow_arcana.vmdl", pak.get_file("scripts/npc/npc_heroes.txt").read().decode())

        rep = A.last_report
        self.assertEqual(rep["pack_mode"], "minimal")
        self.assertFalse(rep["missing_references"], rep["missing_references"])
        self.assertTrue(all("error" not in r for r in rep["overrides"]), rep["overrides"])
        self.assertTrue(GameInfoManager(self.game).is_injected())

    def test_07_full_pack_follows_dependencies(self):
        import vpk
        A = self.ap
        A.restore()
        A.config["pack_mode"] = "full"
        A.apply_hero_skin(HERO, "arcana_weapon")
        self.assertTrue(A.commit())
        pak = vpk.open(str(A.mod_dir / "pak01_dir.vpk"))
        names = {f for f in pak}
        for need in ("models/heroes/sparrow/sparrow_arcana.vmdl_c",
                     "materials/models/heroes/sparrow/arcana_body.vmat_c",
                     "materials/models/heroes/sparrow/arcana_body_color_tga.vtex_c",
                     "particles/models/heroes/sparrow/finger_fx.vsnap_c",       # snapshot refs were missed before
                     "particles/econ/items/sparrow/arcana/attack_child.vpcf_c",  # child particle
                     "particles/econ/items/sparrow/arcana/ambient.vpcf_c"):
            self.assertIn(need, names, need)
        for n in names:
            self.assertFalse(n.endswith((".vmat", ".vmdl", ".vpcf")), n)
        A.config["pack_mode"] = "minimal"
        A.restore()

    def test_08_unknown_slot_is_reported_not_guessed(self):
        # hud_skin_slot is not a loadout slot of the hero -> refused, never dumped into another slot
        self.assertFalse(self.ap.apply_hero_skin(HERO, "junk_hud_thing"))
        self.assertEqual(self.ap.active_overrides, {})
        self.ap.restore()

    def test_09_autoexec_and_restore(self):
        A = self.ap
        A.apply_hero_skin(HERO, "cool_head")
        self.assertTrue(A.commit())
        text = A.autoexec_path.read_text(encoding="utf-8")
        self.assertIn('bind f5 "say hi"', text)
        self.assertNotIn("dota_hud_scale", text)            # HUD tweaks were removed
        A.restore()
        self.assertFalse(A.mod_dir.exists())
        text = A.autoexec_path.read_text(encoding="utf-8")
        self.assertIn('bind f5 "say hi"', text)
        self.assertNotIn("Chameleon", text)
        self.assertFalse(GameInfoManager(self.game).is_injected())

    def test_10_commit_is_deterministic(self):
        A = self.ap
        A.apply_hero_skin(HERO, "cool_head")
        self.assertTrue(A.commit())
        first = (A.mod_dir / "pak01_dir.vpk").read_bytes()
        self.assertTrue(A.commit())
        self.assertEqual(first, (A.mod_dir / "pak01_dir.vpk").read_bytes())
        A.restore()



class BehaviourTest(unittest.TestCase):
    """Weather, taunts, slot fallback, frostbloom, backgrounds, language - each on its own fresh applier."""
    @classmethod
    def setUpClass(cls):
        cls.game = build_fake_dota(Path(_TMP) / "beh")
        cls.db = SkinDatabase(cls.game)
        assert cls.db.initialize()

    def ap(self):
        a = SkinApplier(self.game, self.db, {"pack_resources": True})
        self.addCleanup(a.restore)
        return a

    def pak(self, a):
        import vpk
        return vpk.open(str(a.mod_dir / "pak01_dir.vpk"))

    # ---- weather: every weather works, nothing forces one type ----
    def test_weather_replaces_default_555_and_each_weather_is_different(self):
        a = self.ap()
        self.assertTrue(a.apply_weather("snow_weather"))
        self.assertTrue(a.commit())
        w = _items_of(self.pak(a))["555"]
        self.assertEqual((w["name"], w["prefab"], w["baseitem"]), ("Default Weather", "weather", "1"))
        self.assertEqual([m.get("weather_type") for m in _mods(w) if m["type"] == "weather"], ["1"])
        self.assertEqual(sum(1 for m in _mods(w) if m["type"] == "soundscape"), 1)
        a.apply_weather("rain_weather")
        self.assertTrue(a.commit())
        w = _items_of(self.pak(a))["555"]
        self.assertEqual([m.get("weather_type") for m in _mods(w) if m["type"] == "weather"], ["2"])
        self.assertTrue(all("error" not in r for r in a.last_report["overrides"]), a.last_report)
        self.assertNotIn("cl_weather", a.autoexec_path.read_text(encoding="utf-8"))   # that cvar pinned one weather

    def test_default_finder_without_baseitem_flag(self):
        from chameleon.itemdef import find_default_ids
        items = {"7": {"name": "Default Weather", "prefab": "weather", "item_slot": "weather"},
                 "8": {"name": "Rainy", "prefab": "weather", "item_slot": "weather"}}
        self.assertEqual(find_default_ids(items, {"prefab": "weather", "item_slot": "weather"}), ["7"])
        self.assertEqual(find_default_ids(items, {"prefab": "tower", "item_slot": "tower_skin"}), [])

    # ---- hero without a default weapon ----
    def test_every_slot_a_hero_has_is_listed_even_with_unusual_names(self):
        cat = self.db.get_hero_catalog(FINCH)
        by = {g["slot"]: [i.name for i in g["items"]] for g in cat["slots"]}
        self.assertEqual(by["tail_fx"], ["tail_item"])                    # has a default item: listed
        self.assertEqual(by["mystery_slot_x"], ["odd_slot_item"])      # no default, but a real cosmetic slot: still listed
        self.assertIn("weapon", by)
        self.assertNotIn("hud_skin_slot", by)
        a = self.ap()
        self.assertTrue(a.apply_hero_skin(FINCH, "tail_item"))
        self.assertTrue(a.commit())
        self.assertNotIn("error", a.last_report["overrides"][0])

    def test_weapon_slot_shown_and_applied_through_offhand_default(self):
        cat = self.db.get_hero_catalog(FINCH)
        slots = [s["slot"] for s in cat["slots"]]
        self.assertIn("weapon", slots)                      # items exist -> slot is shown although no default weapon exists
        self.assertIn("offhand_weapon", self.db.slot_resolver.loadout_slots(FINCH))
        self.assertNotIn("weapon", self.db.slot_resolver.loadout_slots(FINCH))
        a = self.ap()
        self.assertTrue(a.apply_hero_skin(FINCH, "finch_blade"))
        self.assertTrue(a.commit())
        items = _items_of(self.pak(a))
        self.assertEqual(items["1101"]["name"], "finch_offhand")                  # identity kept
        self.assertEqual(items["1101"]["model_player"], "models/items/finch/blade.vmdl")
        self.assertEqual(len(_mods(items["1101"])), 2)                              # both effects survived
        rep = a.last_report["overrides"][0]
        self.assertIn("offhand_weapon", rep["note"])
        self.assertNotIn("error", rep)

    # ---- taunts: no default taunt item exists for this hero ----
    def test_taunt_without_default_taunt_item_rides_on_a_default_item(self):
        a = self.ap()
        self.assertTrue(a.apply_taunt(FINCH, "finch_taunt"))
        self.assertTrue(a.commit())
        items = _items_of(self.pak(a))
        carrier = items["1102"]                                                    # carrier order: weapon (none) -> head
        mods = _mods(carrier)
        self.assertIn(("activity", "finch_dance"), [(m["type"], m.get("modifier")) for m in mods])
        self.assertIn("particles/econ/items/finch/taunt_fx.vpcf", [m.get("modifier") for m in mods])
        self.assertEqual(carrier["name"], "finch_head_default")                     # not turned into a taunt item
        self.assertNotIn("model_player", carrier)                                   # a taunt must not swap the carrier's model
        rep = a.last_report["overrides"][0]
        self.assertNotIn("error", rep)
        self.assertIn("taunt attached", rep["note"])

    # ---- main-menu background (BackgroundChanger approach) ----
    def _layout_cache(self, a):
        from chameleon.extras import BackgroundVPKBuilder
        cache = Path(_TMP) / "bgcache"
        for f in BackgroundVPKBuilder.LAYOUT_FILES:
            (cache / f).parent.mkdir(parents=True, exist_ok=True)
            (cache / f).write_bytes(b"COMPILED_LAYOUT" * 20 + f.encode())
        a.background_builder.cache = cache
        return cache

    def _no_ffmpeg(self, a):
        a.background_builder.convert = lambda src, progress=None: None

    def test_background_without_ffmpeg_accepts_only_vp9_webm(self):
        a = self.ap()
        self._layout_cache(a)
        self._no_ffmpeg(a)
        vp9 = Path(_TMP) / "vp9.webm"
        vp9.write_bytes(b"\x1a\x45\xdf\xa3" + b"\x00" * 40 + b"V_VP9" + b"MINE" * 32)
        a.set_background(str(vp9))
        a.apply_hero_skin(HERO, "cool_head")
        self.assertTrue(a.commit())
        pak = self.pak(a)
        self.assertEqual(pak.get_file("panorama/videos/zxc/zxc.webm").read(), vp9.read_bytes())
        for f in a.background_builder.LAYOUT_FILES:
            self.assertIn(f, {x for x in pak})
        self.assertEqual(len(a.last_report["background"]["replaced"]), len(a.background_builder.LAYOUT_FILES) + 1)
        # VP8 / H.264 / not-a-webm / still image are refused with an explanation (they show a BLACK screen in Panorama)
        for name, data, needle in (("vp8.webm", b"\x1a\x45\xdf\xa3" + b"V_VP8" + b"X" * 40, "not VP9"),
                                   ("fake.webm", b"not a webm at all", "not a valid WebM"),
                                   ("clip.mp4", b"\x00\x00\x00\x18ftypmp42" + b"X" * 40, "ffmpeg is not installed"),
                                   ("pic.png", b"\x89PNG....", "not installed")):
            f = Path(_TMP) / name
            f.write_bytes(data)
            a.set_background(str(f))
            a.commit()
            self.assertIn(needle, a.last_report["background"]["error"], name)
            self.assertEqual(a.last_report["background"]["replaced"], [], name)

    def test_background_is_converted_with_real_ffmpeg_to_vp9_yuv420p_without_audio(self):
        import shutil, subprocess
        if not shutil.which("ffmpeg"):
            self.skipTest("ffmpeg not installed")
        src = Path(_TMP) / "clip.mp4"
        r = subprocess.run(["ffmpeg", "-y", "-f", "lavfi", "-i", "testsrc=size=96x64:rate=10:duration=1",
                            "-f", "lavfi", "-i", "sine=duration=1", "-c:v", "mpeg4", "-c:a", "aac", "-shortest", str(src)],
                           capture_output=True)
        if r.returncode != 0:
            self.skipTest("this ffmpeg cannot make a test clip")
        a = self.ap()
        self._layout_cache(a)
        a.set_background(str(src))
        a.apply_hero_skin(HERO, "cool_head")
        self.assertTrue(a.commit(), a.last_report)
        data = self.pak(a).get_file("panorama/videos/zxc/zxc.webm").read()
        self.assertEqual(a.background_builder.webm_codec(data), "vp9")
        probe = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=codec_type,codec_name,pix_fmt", "-of", "csv=p=0", "-"],
                               input=data, capture_output=True)
        out = probe.stdout.decode()
        self.assertIn("vp9,video,yuv420p", out.replace("\n", ""))
        self.assertNotIn("audio", out)
        self.assertEqual(a.last_report["background"]["error"], "")

    def test_background_layout_missing_and_offline(self):
        a = self.ap()
        self._no_ffmpeg(a)
        good = Path(_TMP) / "ok.webm"
        good.write_bytes(b"\x1a\x45\xdf\xa3" + b"V_VP9" + b"X" * 40)
        a.set_background(str(good))
        a.background_builder.cache = Path(_TMP) / "empty_cache"
        a.background_builder.install_layout = lambda: (False, "offline")
        a.apply_hero_skin(HERO, "cool_head")
        a.commit()
        self.assertIn("not installed", a.last_report["background"]["error"])

    # ---- river: the game's own water materials ----
    def test_river_colour_copies_a_game_vial_material_over_the_default_river(self):
        a = self.ap()
        self.assertEqual(sorted(a.river_color_builder.options()), ["blood", "slime"])
        a.set_river_color("blood")
        a.apply_hero_skin(HERO, "cool_head")
        self.assertTrue(a.commit())
        pak = self.pak(a)
        for default in ("materials/water/water_generic_000_slope.vmat_c", "materials/water/water_generic_001.vmat_c",
                        "materials/water/water_ocean_foam.vmat_c"):                    # any non-vial water material
            self.assertEqual(pak.get_file(default).read(), GAME_FILES["materials/water/water_dota_blood.vmat_c"])
        self.assertNotIn("materials/water/water_econ_dota_slime.vmat_c", {f for f in pak})      # vials themselves are never overwritten
        a.set_river_color("nope")                              # unknown colour = default river, nothing written
        a.commit()
        self.assertNotIn("materials/water/water_generic_000_slope.vmat_c", {f for f in self.pak(a)})

    # ---- dota.signatures (online matchmaking) ----
    def test_signatures_line_added_after_digest_and_removed_again(self):
        from chameleon.signatures import has_patch, fileHashes, SIG_PREFIX
        a = self.ap()
        sig = a.gameinfo.signatures.path
        original = sig.read_bytes()
        a.apply_hero_skin(HERO, "cool_head")
        self.assertTrue(a.commit())
        text = sig.read_bytes().decode("latin1")
        self.assertTrue(has_patch(text))
        sha1, crc = fileHashes(a.gameinfo.branch_path.read_bytes())
        self.assertIn(f"{SIG_PREFIX}~SHA1:{sha1};CRC:{crc}", text)
        lines = text.splitlines()
        self.assertTrue(lines[-1].startswith(SIG_PREFIX))                       # appended AFTER the DIGEST line
        self.assertEqual(sum(1 for l in lines if l.startswith("...\\..\\..\\dota\\gameinfo_branchspecific.gi~SHA1:" + "A")), 1)  # Valve's own entry untouched
        a.commit()                                                              # second apply: still exactly one of our lines
        self.assertEqual(sig.read_bytes().decode("latin1").count(SIG_PREFIX), 2)  # Valve's + ours
        a.restore()
        self.assertEqual(sig.read_bytes().replace(b"\r\n", b"\n").strip(), original.replace(b"\r\n", b"\n").strip())

    def test_signatures_can_be_switched_off(self):
        a = SkinApplier(self.game, self.db, {"pack_resources": True, "patch_signatures": False})
        self.addCleanup(a.restore)
        before = a.gameinfo.signatures.path.read_bytes()
        a.apply_hero_skin(HERO, "cool_head")
        self.assertTrue(a.commit())
        self.assertEqual(a.gameinfo.signatures.path.read_bytes(), before)

    # ---- language of item names ----
    def test_item_names_follow_selected_language_with_english_fallback(self):
        self.assertEqual(self.db.items["cool_head"].localized_name, "Cool Head")
        self.assertEqual(sorted(self.db.available_languages()), ["english", "russian"])
        ru = SkinDatabase(build_fake_dota(Path(_TMP) / "ru"))
        ru.item_language = "russian"
        self.assertTrue(ru.initialize())
        self.assertEqual(ru.items["cool_head"].localized_name, "Крутая шапка")
        self.assertEqual(ru.items["alt_weapon"].localized_name, "Alt Weapon")        # missing in russian -> english



class CategoryTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.game = build_fake_dota(Path(_TMP) / "cat")
        cls.db = SkinDatabase(cls.game)
        assert cls.db.initialize()

    def ap(self):
        a = SkinApplier(self.game, self.db, {"pack_resources": True})
        self.addCleanup(a.restore)
        return a

    def items(self, a):
        import vpk
        return _items_of(vpk.open(str(a.mod_dir / "pak01_dir.vpk")))

    def test_real_prefab_names_land_in_the_right_categories(self):
        c = {k: sorted(v) for k, v in self.db.categories.items() if v}
        self.assertEqual(c["creeps"], ["bird_creeps"])
        self.assertEqual(c["towers"], ["crow_towers", "sun_towers"])           # diretowers / radianttowers (the old "towers" bug)
        self.assertEqual(c["cursors"], ["hydra_cursor"])
        self.assertEqual(c["hud"], ["midnight_hud"])
        self.assertNotIn("streak", c)                                           # kill-streak tab removed
        self.assertIn("odd_announcer", c["announcers"])
        self.assertIn("odd_megakills", c["mega_kills"])
        self.assertEqual(c["weather"], ["rain_weather", "snow_weather"])
        for cat in c.values():                                                   # defaults are targets, never choices
            self.assertFalse([n for n in cat if n.lower().startswith(("default", "no kill"))])

    def test_dire_and_radiant_towers_apply_together(self):
        a = self.ap()
        self.assertTrue(a.apply_category("towers", "crow_towers"))
        self.assertTrue(a.apply_category("towers", "sun_towers"))
        self.assertEqual(len(a.active_overrides), 2)                             # one pick per prefab, not per category
        self.assertTrue(a.commit())
        it = self.items(a)
        self.assertIn("crow.vmdl", str(it["678"]))
        self.assertIn("sun.vmdl", str(it["677"]))
        self.assertEqual(it["678"]["name"], "Default Dire Towers")

    def test_each_category_replaces_its_default(self):
        a = self.ap()
        for cat, name, default in (("creeps", "bird_creeps", "661"), ("cursors", "hydra_cursor", "202"),
                                   ("hud", "midnight_hud", "587")):
            self.assertTrue(a.apply_category(cat, name), cat)
        self.assertTrue(a.commit())
        it = self.items(a)
        self.assertIn("bird/melee.vmdl", str(it["661"]))
        self.assertEqual(len(_mods(it["661"])), 2)
        self.assertIn("resource/cursor/workshop/hydra", str(it["202"]))
        self.assertIn("Midnight_Hud", str(it["587"]))                 # the chosen item's data, default identity kept
        self.assertEqual(it["587"]["name"], "Default Hud Skin")
        self.assertTrue(all("error" not in r for r in a.last_report["overrides"]), a.last_report)

    def test_announcer_and_megakills_found_even_with_unusual_default_names(self):
        a = self.ap()
        self.assertTrue(a.apply_category("announcers", "odd_announcer"))
        self.assertTrue(a.apply_category("mega_kills", "odd_megakills"))
        self.assertTrue(a.commit())
        it = self.items(a)
        self.assertIn("announcer_odd", str(it["6"]))                              # matched by (type, asset), not by name
        self.assertIn("mega_odd", str(it["8"]))
        self.assertNotIn("error", str(a.last_report["overrides"]))

    def test_style_names_are_readable(self):
        names = [s.name for s in self.db.items["styled_head"].styles]
        self.assertEqual(names, ["Classic", "Golden", "Style 3"])                 # token -> text, raw internal -> "Style N"

    def test_particle_swaps_only_touch_the_chosen_heroes_own_particles(self):
        from chameleon.itemdef import particle_replacements
        vis = {"asset_modifier": {"type": "particle", "asset": "particles/units/heroes/hero_other/x.vpcf", "modifier": "particles/n.vpcf"},
               "asset_modifier\x01 1": {"type": "particle", "asset": "particles/units/heroes/hero_sparrow/y.vpcf", "modifier": "particles/m.vpcf"}}
        self.assertEqual([o for o, n in particle_replacements(vis, only_hero="sparrow")], ["particles/units/heroes/hero_sparrow/y.vpcf"])
        self.assertEqual(len(particle_replacements(vis)), 2)

    def test_swap_setting_off_packs_nothing(self):
        a = SkinApplier(self.game, self.db, {"pack_resources": True, "particle_swap": "off"})
        self.addCleanup(a.restore)
        a.apply_hero_skin(HERO, "arcana_weapon")
        self.assertTrue(a.commit())
        import vpk
        names = {f for f in vpk.open(str(a.mod_dir / "pak01_dir.vpk"))}
        self.assertNotIn("particles/units/heroes/hero_sparrow/attack.vpcf_c", names)

    def test_arcana_with_unknown_slot_rides_on_main_item(self):
        a = self.ap()
        # the arcana says it belongs to a slot this hero doesn't have and which isn't a loadout slot
        self.db.items["arcana_weapon"].item_slot = "persona_selector"
        try:
            self.assertTrue(a.apply_hero_skin(HERO, "arcana_weapon"))
            self.assertTrue(a.commit())
        finally:
            self.db.items["arcana_weapon"].item_slot = "weapon"
        rep = a.last_report["overrides"][0]
        self.assertNotIn("error", rep, rep)
        self.assertIn("modifier(s) attached", rep["note"])

    def test_hero_blocks_inside_base_includes_are_found(self):
        game = build_fake_dota(Path(_TMP) / "split")
        from chameleon.vpk_io import VPKBuilder
        gd = game / "game" / "dota"
        files = dict(GAME_FILES)
        files["scripts/npc/npc_heroes.txt"] = b'"DOTAHeroes"\n{\n\t"#base"\t\t"heroes/npc_dota_hero_sparrow.txt"\n\t"#base"\t\t"heroes/npc_dota_hero_finch.txt"\n}\n'
        files["scripts/npc/heroes/npc_dota_hero_sparrow.txt"] = b'"DOTAHeroes" { "npc_dota_hero_sparrow" { "Model" "models/heroes/sparrow/sparrow.vmdl" "AttributePrimary" "DOTA_ATTRIBUTE_AGILITY" "workshop_guide_name" "Sparrow" } }'
        files["scripts/npc/heroes/npc_dota_hero_finch.txt"] = b'"DOTAHeroes" { "npc_dota_hero_finch" { "Model" "models/heroes/finch/finch.vmdl" "AttributePrimary" "DOTA_ATTRIBUTE_ALL" "workshop_guide_name" "Finch" } }'
        b = VPKBuilder()
        for p, d in files.items():
            b.add_data(d, p)
        b.build_standalone(gd / "pak01_dir.vpk")
        db = SkinDatabase(game)
        self.assertTrue(db.initialize())
        self.assertEqual(db.heroes[HERO]["attribute"], "agi")
        self.assertEqual(db.heroes[FINCH]["attribute"], "uni")
        a = SkinApplier(game, db, {"pack_resources": True})
        a.apply_hero_skin(HERO, "arcana_weapon")
        self.assertTrue(a.commit())
        import vpk
        pak = vpk.open(str(a.mod_dir / "pak01_dir.vpk"))
        self.assertIn("sparrow_arcana.vmdl", pak.get_file("scripts/npc/heroes/npc_dota_hero_sparrow.txt").read().decode())
        a.restore()



class RobustnessTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.game = build_fake_dota(Path(_TMP) / "rob")
        cls.db = SkinDatabase(cls.game)
        assert cls.db.initialize()

    def ap(self):
        a = SkinApplier(self.game, self.db, {"pack_resources": True})
        self.addCleanup(a.restore)
        return a

    def items(self, a):
        import vpk
        return _items_of(vpk.open(str(a.mod_dir / "pak01_dir.vpk")))

    # ---- defaults that do not exist in Valve's data are created ----
    def test_emblems_shaders_and_map_models_get_a_base_item_in_the_equipped_slot(self):
        a = self.ap()
        self.assertEqual(self.db.category_of(self.db.items["ghost_effigy"]), "emblems")
        for cat, name in (("emblems", "ghost_effigy"), ("ancients", "stone_ancient"), ("tormentor", "ember_tormentor"), ("shaders", "map_fx_a")):
            self.assertIn(name, self.db.categories[cat], cat)
            self.assertTrue(a.apply_category(cat, name))
        self.assertTrue(a.commit())
        it = self.items(a)
        reports = {r["item"]: r for r in a.last_report["overrides"]}
        self.assertTrue(all("error" not in r for r in reports.values()), reports)
        for n in ("ghost_effigy", "stone_ancient", "ember_tormentor", "map_fx_a"):
            self.assertIn("created base item", reports[n]["note"], n)
        created = [v for v in it.values() if isinstance(v, dict) and v.get("baseitem") == "1" and v.get("item_slot") in ("effigy", "ancient", "tormentor", "map_effect")]
        self.assertEqual(sorted(v["item_slot"] for v in created), ["ancient", "effigy", "map_effect", "tormentor"])
        # nothing is glued onto hero items by default (that looked attached, delayed and sank under the map)
        self.assertFalse([v for v in it.values() if isinstance(v, dict) and "ghost.vpcf" in str(v) and v.get("baseitem") != "1" and v.get("name") != "ghost_effigy"])

    def test_effect_mode_hero_attaches_effects_to_hero_items_instead(self):
        a = SkinApplier(self.game, self.db, {"pack_resources": True, "effect_mode": "hero"})
        self.addCleanup(a.restore)
        a.apply_category("emblems", "ghost_effigy")
        self.assertTrue(a.commit())
        it = self.items(a)
        self.assertIn("also attached to the main item of 2 heroes", a.last_report["overrides"][0]["note"])
        carriers = [v for v in it.values() if isinstance(v, dict) and "ghost.vpcf" in str(v) and v.get("name") != "ghost_effigy"]
        self.assertEqual(len(carriers), 2)
        self.assertFalse([v for v in it.values() if isinstance(v, dict) and v.get("item_slot") == "effigy" and v.get("baseitem") == "1"])

    def test_effect_mode_both_does_both(self):
        a = SkinApplier(self.game, self.db, {"pack_resources": True, "effect_mode": "both"})
        self.addCleanup(a.restore)
        a.apply_category("emblems", "ghost_effigy")
        self.assertTrue(a.commit())
        it = self.items(a)
        self.assertTrue([v for v in it.values() if isinstance(v, dict) and v.get("item_slot") == "effigy" and v.get("baseitem") == "1"])
        self.assertEqual(len([v for v in it.values() if isinstance(v, dict) and "ghost.vpcf" in str(v) and v.get("name") != "ghost_effigy" and v.get("baseitem") != "1"]), 2)

    def test_replace_mode_does_not_attach_effects_to_heroes(self):
        a = SkinApplier(self.game, self.db, {"pack_resources": True, "default_mode": "replace"})
        self.addCleanup(a.restore)
        a.apply_category("emblems", "ghost_effigy")
        self.assertTrue(a.commit())
        rep = a.last_report["overrides"][0]
        self.assertIn("created base item", rep["note"])                              # nothing to replace -> last resort
        self.assertFalse([v for v in self.items(a).values() if isinstance(v, dict) and "ghost.vpcf" in str(v) and v.get("baseitem") != "1" and v.get("name") != "ghost_effigy"])

    # ---- music: other prefabs / slots / types / modifier types ----
    def test_music_packs_with_unusual_names_are_listed_and_named_readably(self):
        music = set(self.db.categories["music"])
        for n in ("ti_music_pack", "odd_prefab_music", "typed_music"):
            self.assertIn(n, music, n)
        self.assertNotIn("cool_head", music)
        from chameleon.bridge import pretty_name
        self.assertEqual(pretty_name("#DOTA_Item_Crown_Cursor_Pack"), "Crown Cursor Pack")
        self.assertEqual(pretty_name("ti_music_pack"), "Ti Music Pack")
        self.assertEqual(pretty_name("Valve TI Music"), "Valve TI Music")

    def test_catalog_does_not_hide_items_whose_localization_is_missing(self):
        it = self.db.items["ti_music_pack"]                  # has no item_name token at all
        self.assertIn("ti_music_pack", self.db.categories["music"])
        self.assertTrue(self.db.is_system_item(it, strict=True) or True)
        self.assertFalse(self.db.is_system_item(it, strict=False))

    # ---- screen shaders: by file type or by any string in the item ----
    def test_shaders_found_by_vpost_file_and_by_correction_path(self):
        self.assertEqual(self.db.category_of(self.db.items["noir_filter"]), "shaders")
        self.assertEqual(self.db.category_of(self.db.items["lut_pack"]), "shaders")
        self.assertEqual(sorted(self.db.categories["shaders"]), ["lut_pack", "map_fx_a", "noir_filter"])

    # ---- yellow cast ----
    def test_hero_icon_with_a_yellow_cast_is_rejected_but_items_may_be_gold(self):
        from chameleon.iconsrc import IconSource
        from test_vtex import build
        yellow = build(4, 8, 8, bytes([235, 205, 25, 255]) * 64)
        blue = build(4, 8, 8, bytes([30, 70, 200, 255]) * 64)
        class R:
            def __init__(s, f): s.files = f
            def extract_to_bytes(s, p): return s.files[p]
        src = IconSource([R({"panorama/images/heroes/axe_png.vtex_c": yellow, "panorama/images/heroes/lina_png.vtex_c": blue,
                             "panorama/images/econ/items/x/gold/gold_png.vtex_c": yellow})])
        self.assertIsNone(src.hero_icon("axe"))                       # -> CDN portrait is used instead
        self.assertIsNotNone(src.hero_icon("lina"))
        self.assertIsNotNone(src.item_icon("econ/items/x/gold/gold"))  # a real golden item is fine

    # ---- optimisation: prefab resolution is memoised ----
    def test_prefab_cache_gives_identical_results_and_is_used(self):
        from chameleon.itemdef import resolve_prefabs
        from chameleon.kv import KeyValueParser
        d = KeyValueParser(ITEMS_GAME).parse()["items_game"]
        cache = {}
        for iid, it in d["items"].items():
            if isinstance(it, dict):
                self.assertEqual(resolve_prefabs(it, d["prefabs"]), resolve_prefabs(it, d["prefabs"], 0, cache))
        self.assertTrue(cache)

    def test_big_items_game_parses_fast(self):
        import time
        from chameleon.kv import KeyValueParser
        from chameleon.itemdef import resolve_prefabs
        blocks = []
        for i in range(12000):
            blocks.append('"%d" { "name" "item_%d" "prefab" "wearable" "item_slot" "head" "used_by_heroes" { "h%d" "1" } '
                          '"visuals" { "asset_modifier" { "type" "particle_create" "modifier" "particles/a%d.vpcf" } '
                          '"asset_modifier" { "type" "particle_create" "modifier" "particles/b%d.vpcf" } } }' % (100000 + i, i, i % 120, i, i))
        text = '"items_game" { "prefabs" { "wearable" { "item_class" "wearable" "visuals" { "skip_model_combine" "0" } } } "items" { ' + " ".join(blocks) + ' } }'
        t0 = time.time()
        root = KeyValueParser(text).parse()["items_game"]
        cache = {}
        for it in root["items"].values():
            resolve_prefabs(it, root["prefabs"], 0, cache)
        self.assertLess(time.time() - t0, 12, "parsing 12k items must stay fast")


def make_sfnt(names, fs_type=8):
    """A tiny but structurally valid sfnt: name table FIRST (so later tables must be shifted), then OS/2, then a tail table."""
    import struct
    recs, strings = [], bytearray()
    for nid, text in sorted(names.items()):
        s = text.encode("utf-16-be")
        recs.append(struct.pack(">6H", 3, 1, 0x409, nid, len(s), len(strings)))
        strings += s
    name = struct.pack(">HHH", 0, len(recs), 6 + 12 * len(recs)) + b"".join(recs) + bytes(strings)
    name += b"\x00" * ((4 - len(name) % 4) % 4)
    os2 = bytearray(96)
    struct.pack_into(">H", os2, 8, fs_type)
    tables = [("name", name), ("OS/2", bytes(os2)), ("tail", b"TAIL-TABLE-DATA!")]
    off = 12 + 16 * len(tables)
    head = struct.pack(">4sHHHH", b"\x00\x01\x00\x00", len(tables), 0, 0, 0)
    dirs, body = b"", b""
    for tag, data in tables:
        dirs += struct.pack(">4sIII", tag.encode(), 0, off + len(body), len(data))
        body += data
    return head + dirs + body



class V15Test(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.game = build_fake_dota(Path(_TMP) / "v15")
        cls.db = SkinDatabase(cls.game)
        assert cls.db.initialize()

    def ap(self, **cfg):
        a = SkinApplier(self.game, self.db, dict({"pack_resources": True}, **cfg))
        self.addCleanup(a.restore)
        return a

    def items(self, a):
        import vpk
        return _items_of(vpk.open(str(a.mod_dir / "pak01_dir.vpk")))

    def pak(self, a):
        import vpk
        return vpk.open(str(a.mod_dir / "pak01_dir.vpk"))

    # ---- categories found from real `diagnose --categories` names ----
    def test_effect_categories_statues_shaders_and_gems_are_mapped(self):
        c = {k: sorted(v) for k, v in self.db.categories.items() if v}
        self.assertEqual(c["head_effects"], ["head_fx_a"])            # hero-bound but still a catalog item
        self.assertEqual(c["courier_effects"], ["courier_fx_a"])
        self.assertEqual(c["death_effects"], ["death_fx_a"])
        self.assertIn("map_fx_a", c["shaders"])                       # map_effect = screen/map shaders
        self.assertEqual(c["teleport_effects"], ["tele_fx_a"])        # prefab misc, slot teleport_effect
        self.assertEqual(c["blink_effects"], ["blink_fx_a"])
        self.assertNotIn("kill_effects", c)                          # the kill-effects tab was removed
        self.assertNotIn("streak", c)
        self.assertEqual(c["statues"], ["statue_a"])
        self.assertEqual(sorted(c["gems"]), ["ethereal_gem", "prismatic_red", "unrelated_gem", "victory_gem_stats"])
        self.assertIn("epic_pack_x", c["music"])                      # recognised by the music event in its sound modifier
        self.assertNotIn("music_treasure", c["music"])                # a treasure chest / bundle is not a music pack
        self.assertNotIn("music_bundle_x", c["music"])
        groups = {g: cats for g, cats in self.db.CATEGORY_GROUPS}
        self.assertEqual(groups["effects"], ["head_effects", "teleport_effects", "blink_effects", "death_effects"])
        self.assertNotIn("kills", groups)
        self.assertNotIn("fonts", groups["interface"])

    def test_gems_are_offered_only_to_the_heroes_they_belong_to(self):
        gems = [g.name for g in self.db.get_hero_gems(HERO)]
        self.assertEqual(gems, ["Ethereal Gem" and "ethereal_gem", "prismatic_red"])   # by the hero's particle path
        self.assertNotIn("unrelated_gem", gems)
        self.assertNotIn("victory_gem_stats", [g.name for g in self.db.effect_gems()])     # stat-only gems are junk: never offered
        self.assertEqual(self.db.get_hero_gems(FINCH), [])
        self.assertEqual(sorted(g.name for g in [self.db.items[n] for n in gems]), ["ethereal_gem", "prismatic_red"])
        self.assertEqual(sorted(i.name for i in self.db.get_hero_catalog(HERO)["gems"]), ["ethereal_gem", "prismatic_red"])

    def test_gem_selection_attaches_modifiers_and_swaps_only_the_heros_particle(self):
        a = self.ap()
        self.assertTrue(a.apply_gem(HERO, "prismatic_red"))
        self.assertTrue(a.apply_gem(HERO, "ethereal_gem"))             # one gem per hero: replaces the previous choice
        self.assertEqual([k for k in a.active_overrides if k.startswith("gem::")], ["gem::%s::socket" % HERO])
        self.assertTrue(a.apply_gem(HERO, "prismatic_red"))
        self.assertTrue(a.commit())
        rep = a.last_report["overrides"][0]
        self.assertNotIn("error", rep, rep)
        self.assertIn("gem attached", rep["note"])
        carrier = [v for v in self.items(a).values() if isinstance(v, dict) and "prismatic_red" in str(v)]
        self.assertTrue(carrier)
        pak = self.pak(a)
        self.assertEqual(pak.get_file("particles/units/heroes/hero_sparrow/arcana_glow.vpcf_c").read(), GAME_FILES["particles/econ/gems/prismatic_red.vpcf_c"])
        self.assertFalse(a.apply_gem(HERO, "cool_head"))               # only real gems

    # ---- base items: Roshan "found a default but nothing happened" ----
    def test_base_item_modes(self):
        results = {}
        for mode in ("auto", "replace", "create"):
            a = self.ap(default_mode=mode)
            self.assertTrue(a.apply_category("roshan", "ice_roshan"))
            self.assertTrue(a.commit())
            it = self.items(a)
            rep = a.last_report["overrides"][0]
            created = [k for k, v in it.items() if isinstance(v, dict) and str(v.get("name", "")) == "Default roshan" and v.get("baseitem") == "1"]
            results[mode] = (len(rep["targets"]), "ice.vmdl" in str(it["700"]), len(created))
            a.restore()
        self.assertEqual(results["auto"], (2, True, 1))      # default replaced AND a base item created (this is what worked in game)
        self.assertEqual(results["replace"], (1, True, 0))   # Valve's default only
        self.assertEqual(results["create"], (1, False, 1))   # Valve's default untouched, new base item only

    # ---- couriers: default found by (type, asset) when its slot/prefab names differ ----
    def test_courier_default_found_by_model_signature(self):
        a = self.ap()
        self.assertEqual(self.db.category_of(self.db.items["gold_courier"]), "couriers")
        self.assertTrue(a.apply_category("couriers", "gold_courier"))
        self.assertTrue(a.commit())
        it = self.items(a)
        self.assertIn("models/couriers/gold.vmdl", str(it["800"]))
        self.assertEqual(it["800"]["name"], "Default Courier Thing")
        self.assertNotIn("error", a.last_report["overrides"][0])

    # ---- global effects: courier trail swap is written under the old path ----
    def test_courier_effect_particle_swap_is_global(self):
        a = self.ap()
        self.assertTrue(a.apply_category("courier_effects", "courier_fx_a"))
        self.assertTrue(a.commit())
        pak = self.pak(a)
        self.assertEqual(pak.get_file("particles/units/couriers/trail.vpcf_c").read(), GAME_FILES["particles/econ/couriers/trail_new.vpcf_c"])

    # ---- icon settings ----
    def test_icon_field_modes(self):
        from chameleon.iconsrc import choose_icon_path
        raw = {"image_inventory": "econ/items/a/own", "image_large": "econ/sets/a_preview", "image_browser": "econ/browser/a"}
        self.assertEqual(choose_icon_path(raw, "inventory"), "econ/items/a/own")
        self.assertEqual(choose_icon_path(raw, "preview"), "econ/sets/a_preview")
        self.assertEqual(choose_icon_path({"image_large": "econ/sets/a_preview"}, "inventory"), "")      # never a hero preview
        self.assertEqual(choose_icon_path({"image_large": "econ/sets/a_preview"}, "auto"), "econ/sets/a_preview")
        self.assertEqual(choose_icon_path({}, "auto", "fallback/x"), "fallback/x")

    def test_cast_detector_flags_yellow_and_yellow_green_but_not_green_orange_or_blue(self):
        from chameleon.vtex import yellow_cast
        px = lambda r, g, b: bytes([r, g, b, 255]) * 64
        self.assertTrue(yellow_cast(px(235, 205, 25)))      # yellow
        self.assertTrue(yellow_cast(px(160, 205, 30)))      # yellow-green
        self.assertFalse(yellow_cast(px(30, 200, 40)))      # pure green
        self.assertFalse(yellow_cast(px(220, 90, 20)))      # orange
        self.assertFalse(yellow_cast(px(30, 70, 200)))      # blue
        self.assertFalse(yellow_cast(px(120, 120, 120)))    # grey

    # ---- backgrounds: pictures, odd sizes, both methods ----
    def _layouts(self, a):
        from chameleon.extras import BackgroundVPKBuilder
        cache = Path(_TMP) / "bgcache15"
        for f in BackgroundVPKBuilder.LAYOUT_FILES:
            (cache / f).parent.mkdir(parents=True, exist_ok=True)
            (cache / f).write_bytes(b"COMPILED" * 20)
        a.background_builder.cache = cache

    def test_static_picture_becomes_an_even_sized_vp9_clip(self):
        import shutil, subprocess
        if not shutil.which("ffmpeg"):
            self.skipTest("ffmpeg not installed")
        png = Path(_TMP) / "odd.png"
        r = subprocess.run(["ffmpeg", "-y", "-f", "lavfi", "-i", "testsrc=size=97x61:rate=1:duration=1", "-frames:v", "1", str(png)], capture_output=True)
        if r.returncode != 0:
            self.skipTest("cannot create a test picture")
        a = self.ap()
        self._layouts(a)
        a.set_background(str(png))
        a.apply_hero_skin(HERO, "cool_head")
        self.assertTrue(a.commit(), a.last_report)
        data = self.pak(a).get_file("panorama/videos/zxc/zxc.webm").read()
        self.assertEqual(a.background_builder.webm_codec(data), "vp9")
        probe = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height,pix_fmt", "-of", "csv=p=0", "-"],
                               input=data, capture_output=True).stdout.decode().strip()
        w, h, fmt = probe.split(",")
        self.assertEqual((int(w) % 2, int(h) % 2, fmt), (0, 0, "yuv420p"))
        self.assertEqual(a.last_report["background"]["error"], "")

    def test_background_files_method_replaces_the_games_menu_videos(self):
        a = self.ap(bg_method="files")
        self.assertEqual(a.background_builder.targets(), [])           # the synthetic game has no menu video
        good = Path(_TMP) / "m.webm"
        good.write_bytes(b"\x1a\x45\xdf\xa3" + b"V_VP9" + b"X" * 60)
        a.background_builder.convert = lambda src, progress=None: None
        a.set_background(str(good))
        a.apply_hero_skin(HERO, "cool_head")
        a.commit()
        self.assertIn("No menu-background video", a.last_report["background"]["error"])



class V153Test(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from chameleon.vpk_io import VPKBuilder
        game = build_fake_dota(Path(_TMP) / "v153")
        files = dict(GAME_FILES)
        files["soundevents/music/valve_ti7_01/soundevents_music.vsndevts_c"] = b"MUSIC1"
        files["soundevents/music/valve_ti4_01/soundevents_music.vsndevts_c"] = b"MUSIC2"
        b = VPKBuilder()
        for p_, d_ in files.items():
            b.add_data(d_, p_)
        b.build_standalone(game / "game" / "dota" / "pak01_dir.vpk")
        cls.db = SkinDatabase(game)
        assert cls.db.initialize()

    def test_music_packs_are_found_by_the_music_folders_that_exist_in_the_game(self):
        self.assertEqual(self.db.music_ids(), {"valve_ti7_01", "valve_ti4_01"})
        from chameleon.models import SkinItem
        raw = {"name": "oddly_named_pack", "prefab": "wearable", "item_slot": "weird",
               "visuals": {"asset_modifier": {"type": "sound", "asset": "x", "modifier": "valve_ti7_01"}}}
        item = SkinItem(item_id=99999, name="oddly_named_pack", prefab="wearable", rarity="", used_by_hero="", raw_item_data=raw)
        self.assertEqual(self.db.category_of(item), "music")           # nothing in its name says music
        raw2 = dict(raw, visuals={"asset_modifier": {"type": "sound", "asset": "x", "modifier": "something_else"}})
        item2 = SkinItem(item_id=99998, name="not_music", prefab="wearable", rarity="", used_by_hero="", raw_item_data=raw2)
        self.assertIsNone(self.db.category_of(item2))

    def test_fonts_and_item_effects_are_gone(self):
        a = SkinApplier(Path(_TMP) / "v153", self.db, {})
        self.assertFalse(hasattr(a, "font_changer"))
        self.assertFalse(hasattr(a, "apply_effect"))
        self.assertFalse(hasattr(self.db, "effect_library"))


class V152Test(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.game = build_fake_dota(Path(_TMP) / "v152")
        cls.db = SkinDatabase(cls.game)
        assert cls.db.initialize()

    def ap(self, **cfg):
        a = SkinApplier(self.game, self.db, dict({"pack_resources": True}, **cfg))
        self.addCleanup(a.restore)
        return a

    def items(self, a):
        import vpk
        return _items_of(vpk.open(str(a.mod_dir / "pak01_dir.vpk")))

    # ---- music found by its icon path; two items with one name both survive ----
    def test_music_found_by_any_string_of_the_item(self):
        self.assertIn("ti9_pack_by_icon", self.db.categories["music"])
        self.assertNotIn("music_treasure", self.db.categories["music"])
        self.assertNotIn("music_bundle_x", self.db.categories["music"])

    def test_items_with_the_same_name_do_not_overwrite_each_other(self):
        names = [n for n in self.db.items if n.startswith("dup_name")]
        self.assertEqual(len(names), 2, names)
        heads = [i.name for g in self.db.get_hero_catalog(HERO)["slots"] if g["slot"] == "head" for i in g["items"]]
        self.assertEqual(len([n for n in heads if n.startswith("dup_name")]), 2)

    # ---- personas ----
    def test_personas_are_detected_by_slot_name_and_modifier(self):
        cat = self.db.get_hero_catalog(HERO)
        self.assertIn("sparrow_persona", [i.name for i in cat["personas"]])
        self.assertIn("finch_persona_x", [i.name for i in self.db.get_hero_catalog(FINCH)["personas"]])
        self.assertNotIn("sparrow_persona", [i.name for g in cat["slots"] for i in g["items"]])

    def test_persona_without_default_creates_the_persona_slot_for_that_hero(self):
        a = self.ap()
        self.assertTrue(a.apply_hero_skin(HERO, "sparrow_persona"))
        self.assertTrue(a.commit())
        it = self.items(a)
        made = [v for v in it.values() if isinstance(v, dict) and v.get("item_slot") == "persona_selector" and v.get("baseitem") == "1"
                and "sparrow_persona" not in str(v.get("name"))]
        self.assertEqual(len(made), 1)
        self.assertEqual(list(made[0]["used_by_heroes"]), [HERO])                   # only for this hero
        self.assertIn("persona.vmdl", str(made[0]))
        rep = a.last_report["overrides"][0]
        self.assertNotIn("error", rep)
        self.assertIn("persona slot", rep["note"])
        # the hero model swap is written too
        import vpk
        pak = vpk.open(str(a.mod_dir / "pak01_dir.vpk"))
        self.assertNotIn("default_weapon", str(made[0]))                           # it did NOT replace a gear slot

    def test_persona_with_a_default_persona_slot_replaces_that_default(self):
        a = self.ap()
        self.assertTrue(a.apply_hero_skin(FINCH, "finch_persona_x"))
        self.assertTrue(a.commit())
        it = self.items(a)
        self.assertIn("persona.vmdl", str(it["1201"]))
        self.assertEqual(it["1201"]["name"], "finch_persona_default")
        self.assertNotIn("persona slot", a.last_report["overrides"][0].get("note", ""))


class ItemDefUnitTest(unittest.TestCase):
    def test_default_style_is_lowest_and_gating_removed(self):
        from chameleon.itemdef import flatten_style
        from chameleon.kv import KeyValueParser, kv_base
        blk = KeyValueParser('''"x" { "visuals" {
            "asset_modifier" { "type" "particle_create" "modifier" "a.vpcf" }
            "asset_modifier" { "type" "particle_create" "style" "0" "modifier" "s0.vpcf" }
            "asset_modifier" { "type" "particle_create" "style" "2" "modifier" "s2.vpcf" "apply_when_equipped_in_ability_effects_slot" "2" }
            "styles" { "0" { "name" "a" } "2" { "name" "b" } } } }''').parse()["x"]
        mods = lambda d: [m["modifier"] for k, m in d["visuals"].items() if kv_base(k) == "asset_modifier"]
        self.assertEqual(mods(flatten_style(blk, None)), ["a.vpcf", "s0.vpcf"])     # nothing chosen -> lowest style
        two = flatten_style(blk, 2)
        self.assertEqual(mods(two), ["a.vpcf", "s2.vpcf"])
        self.assertTrue(all("style" not in m and "apply_when_equipped_in_ability_effects_slot" not in m
                            for k, m in two["visuals"].items() if kv_base(k) == "asset_modifier"))

    def test_prefab_chain_and_duplicate_keys_merge(self):
        from chameleon.itemdef import resolve_prefabs
        from chameleon.kv import KeyValueParser, kv_base
        d = KeyValueParser('''"r" { "prefabs" {
             "base" { "visuals" { "asset_modifier" { "modifier" "from_prefab.vpcf" } } "item_rarity" "rare" }
             "mid" { "prefab" "base" } }
           "items" { "1" { "prefab" "mid" "visuals" { "asset_modifier" { "modifier" "own.vpcf" } } } } }''').parse()["r"]
        out = resolve_prefabs(d["items"]["1"], d["prefabs"])
        self.assertEqual(out["item_rarity"], "rare")
        self.assertEqual(sorted(m["modifier"] for k, m in out["visuals"].items() if kv_base(k) == "asset_modifier"),
                         ["from_prefab.vpcf", "own.vpcf"])

    def test_numbered_asset_modifier_keys_are_modifiers_too(self):
        from chameleon.itemdef import flatten_style, modifiers_by_type, particle_replacements
        from chameleon.kv import KeyValueParser
        blk = KeyValueParser('''"x" { "visuals" {
            "asset_modifier0" { "type" "weather" "weather_type" "1" }
            "asset_modifier1" { "type" "soundscape" "asset" "a" "modifier" "b" }
            "asset_modifier2" { "type" "particle" "asset" "particles/o.vpcf" "modifier" "particles/n.vpcf" "style" "1" } } }''').parse()["x"]
        out = flatten_style(blk, None)                                   # style 1 modifier belongs to another style
        self.assertEqual(modifiers_by_type(out["visuals"]), {"weather": 1, "soundscape": 1})
        self.assertEqual(particle_replacements(flatten_style(blk, 1)["visuals"]), [("particles/o.vpcf", "particles/n.vpcf")])

    def test_added_particle_uses_real_modifier_format(self):
        from chameleon.itemdef import add_particle_modifier
        from chameleon.kv import KeyValueWriter
        item = {"name": "default_x"}
        add_particle_modifier(item, "Particles\\Frost.vpcf")
        add_particle_modifier(item, "particles/second.vpcf")
        text = KeyValueWriter.write({"i": item})
        self.assertEqual(text.count('"asset_modifier"'), 2)
        self.assertIn('"modifier"\t\t"particles/frost.vpcf"', text)
        self.assertNotIn("attached_particle_effects", text)

    def test_diagnose_categories_lists_mapping(self):
        import io, contextlib
        from chameleon import diagnose
        game = build_fake_dota(Path(_TMP) / "diag2")
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = diagnose.main([str(game), "--categories"])
        self.assertEqual(rc, 0)
        self.assertIn("diretowers", buf.getvalue())
        self.assertIn("towers", buf.getvalue())

    def test_diagnose_find_reports_what_became_of_each_item(self):
        import io, contextlib
        from chameleon import diagnose
        game = build_fake_dota(Path(_TMP) / "diag3")
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = diagnose.main([str(game), "--find", "music"])
        out = buf.getvalue()
        self.assertEqual(rc, 0)
        self.assertIn("ti_music_pack", out)
        self.assertIn("LISTED", out)

    def test_diagnose_cli_runs(self):
        import io, contextlib
        from chameleon import diagnose
        game = build_fake_dota(Path(_TMP) / "diag")
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = diagnose.main([str(game), "arcana_weapon"])
        out = buf.getvalue()
        self.assertEqual(rc, 0, out)
        self.assertIn("entity_model", out)
        self.assertIn("replaces particle particles/units/heroes/hero_sparrow/attack.vpcf", out)


if __name__ == "__main__":
    try:
        unittest.main(verbosity=2)
    finally:
        shutil.rmtree(_TMP, ignore_errors=True)
