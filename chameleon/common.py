#!/usr/bin/env python3
"""
Chameleon — Dota 2 Skin Changer & Customizer
Version 14.0 — modular rewrite.
"""

import os, sys, json, re, struct, zlib, shutil, time, copy, random, math, threading, subprocess, ctypes, fnmatch, base64, webbrowser
from pathlib import Path
from datetime import datetime
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Any, Set
from urllib.parse import quote
from concurrent.futures import ThreadPoolExecutor
import logging

try:
    import requests
except ImportError:  # only needed for CDN icon download
    requests = None


if sys.platform == "win32":
    import winreg, ctypes.wintypes
import sys
import io

if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

APP_NAME = "Chameleon"
APP_VERSION = "15.4"

CONFIG_DIR = Path(os.environ.get("CHAMELEON_HOME") or (Path.home() / ".chameleon"))
CONFIG_FILE = CONFIG_DIR / "config.json"
PRESETS_DIR = CONFIG_DIR / "presets"
BACKUP_DIR = CONFIG_DIR / "backups"
CACHE_DIR = CONFIG_DIR / "cache"
LOG_FILE = CONFIG_DIR / "chameleon.log"
DATA_DIR = CONFIG_DIR / "data"
ICONS_DIR = DATA_DIR / "icons"
DATA_FILE = DATA_DIR / "chameleon_data.json"
MOD_FOLDER_NAME = "chameleon_tool"

for d in [CONFIG_DIR, PRESETS_DIR, BACKUP_DIR, CACHE_DIR, DATA_DIR, ICONS_DIR]:
    d.mkdir(parents=True, exist_ok=True)

DEFAULT_CONFIG = {
    "dota_path": "", "steam_path": "", "language": "en",
    "auto_restore_on_exit": True, "pack_resources": True, "pack_mode": "minimal",
    "patch_hero_model": True, "patch_signatures": True, "stock_models": True,
    "particle_swap": "hero", "default_mode": "auto", "effect_mode": "slot",
    "icon_field": "inventory", "icon_source": "auto", "icon_fix_cast": True,
    "bg_method": "menu", "install_method": "language", "lang_folder": "russian", "custom_folder": "dota_chameleon", "files_only": False, "ui_density": "m", "discord_rpc": True,
    "launch_parameters": "-novid", "launch_preset": "Default", "launch_presets": [], "favorites": [],
}
# keys that are written at run time and must survive a save
RUNTIME_KEYS = {"applied_sig", "river_color", "background_path"}


def clean_config(cfg: dict) -> dict:
    """Drop settings of removed features (fonts, HUD scale, item language ...) so old config files stay tidy."""
    allowed = set(DEFAULT_CONFIG) | RUNTIME_KEYS
    return {k: v for k, v in (cfg or {}).items() if k in allowed}

RIVER_COLORS = {
    "default": "", "blue": "0.2 0.4 0.8", "red": "0.8 0.2 0.2", "green": "0.2 0.8 0.3",
    "purple": "0.6 0.2 0.8", "orange": "0.9 0.5 0.1", "white": "0.9 0.9 0.9",
    "black": "0.05 0.05 0.05", "gold": "0.8 0.7 0.2", "cyan": "0.1 0.8 0.9",
    "pink": "0.9 0.4 0.7", "crimson": "0.7 0.1 0.2", "teal": "0.1 0.6 0.5",
    "magenta": "0.8 0.1 0.8", "toxic_green": "0.3 0.9 0.1", "blood_red": "0.6 0.05 0.05",
    "ice_blue": "0.5 0.8 0.9", "lava_orange": "0.9 0.3 0.0"
}

CDN_BASE = "https://cdn.cloudflare.steamstatic.com/apps/dota2/images/"

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", handlers=[logging.FileHandler(str(LOG_FILE)), logging.StreamHandler()])
log = logging.getLogger(APP_NAME)

