import os
import aiohttp
from aiohttp import web
import asyncio
import time
import glob
import re
import json
import logging
import traceback
import uuid
import random
from datetime import datetime, timedelta
from pyrogram import Client, filters, enums, raw
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, ChatPrivileges
from pyrogram.errors import SessionPasswordNeeded, PhoneCodeInvalid, PhoneCodeExpired, UserAlreadyParticipant
from pytgcalls import PyTgCalls
from pytgcalls.types import MediaStream, AudioQuality, VideoQuality, Update, StreamEnded, ChatUpdate, UpdatedGroupCallParticipant, GroupCallParticipant
from pytgcalls.types.raw.audio_parameters import AudioParameters
from yt_dlp import YoutubeDL
import psutil
import threading
from concurrent.futures import ThreadPoolExecutor

BOT_START_TIME = time.time()
download_executor = ThreadPoolExecutor(max_workers=3, thread_name_prefix="DLWorker")
_health_runner = None

# --- LOGGING ---
logging.basicConfig(level=logging.INFO)
logging.getLogger("pyrogram.session.session").setLevel(logging.WARNING)
logging.getLogger("pyrogram.connection.connection").setLevel(logging.WARNING)

# --- CONFIGURATION ---
API_ID = 35450953
API_HASH = "763f72b8b828a1907a9291ef02a25dfb"
BOT_TOKEN = "8030013116:AAE_RU3RQznhSBgH2-NrFQvyypCAN3OlGRs"
print(f"DEBUG: Script starting from {os.path.abspath(__file__)}")

# Monkey-patch InlineKeyboardButton to support 'style' property (Bot API 9.4+)
_old_init = InlineKeyboardButton.__init__
def _new_init(self, *args, **kwargs):
    style = kwargs.pop("style", None)
    _old_init(self, *args, **kwargs)
    if style: self.style = style
InlineKeyboardButton.__init__ = _new_init

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DOWNLOAD_DIR = os.path.join(BASE_DIR, "downloads")
DATA_DIR = os.path.join(BASE_DIR, "data")

def find_cookies_file():
    candidates = [
        os.path.join(BASE_DIR, "cookies (1).txt"),
        os.path.join(BASE_DIR, "cookies.txt"),
        "/root/vc/cookies.txt",
        "/cookies.txt",
        "/root/cookies.txt",
        "/app/cookies.txt",
        "/main/cookies.txt",
        "/app/fearless-x-music/cookies.txt",
    ]
    for c in candidates:
        if os.path.exists(c) and os.path.getsize(c) > 0:
            return c
    return os.path.join(BASE_DIR, "cookies.txt")

COOKIES_FILE = find_cookies_file()
SESSION_FILE = os.path.join(DATA_DIR, "assistant_session.json")
ADMINS_FILE = os.path.join(DATA_DIR, "admins.json")
USERS_FILE = os.path.join(DATA_DIR, "users.json")
CHATS_FILE = os.path.join(DATA_DIR, "chats.json")
CLONES_FILE = os.path.join(DATA_DIR, "clones.json")
APPROVED_FILE = os.path.join(DATA_DIR, "approved.json")
CACHE_FILE = os.path.join(DATA_DIR, "cache.json")
SUPER_ADMIN =   7915543522
DEVELOPER_USERNAME = "Prime_Fearless_45"
DEVELOPER_URL = f"tg://openmessage?user_id={SUPER_ADMIN}"

def get_session_string():
    if os.path.exists(SESSION_FILE):
        try:
            with open(SESSION_FILE, "r") as f:
                d = json.load(f)
                if isinstance(d, dict) and d.get("session"):
                    return d["session"]
                elif isinstance(d, str) and d.strip():
                    return d.strip()
        except: pass
    return "BQIc8EkAKuhBvNv1YqqOMcJP673pcLLjOcGbEsaxGZBXzSR6WjaxDd_uY6ENyUOO8-MFvIzl5HFgvrwOFyPEPVFd0MIef6B9qrErltUjh1TX9keJ85TOj5vBO7i2uGqgfeQskSCKYEJkH_BtDzfLnyeDz8kGrRiwmPflKaVk10zWFdz3Jya_4_33J9fF25FQ0DNkX52WUtu0yAbaI2rCt8OtJXpNAFm2aFuhBsO0QOD-_9cgxad1AY6tklv2FJL4dxJNqz-yvk_hCDkfxdxYIEf76cmq3ienRQRxJpgyIpkQmRz0SPh1ij9oD41XsusTZfG_t3wgN98G8oBcBaI3MdzdPF3JnAAAAAH9cc3dAA"

SESSION_STRING = get_session_string()
PHONE_NUMBER = "+918435085793"

# YouTube Login
YT_EMAIL = "fearless45op@gmail.com"
YT_PASS = "Primefearless45!!ff18op"

bot = Client("vc_bot_token", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)
bot.bot_token = BOT_TOKEN
user = Client("vc_user_account", api_id=API_ID, api_hash=API_HASH, session_string=SESSION_STRING)
call_py = PyTgCalls(user)

for d in [DOWNLOAD_DIR, DATA_DIR]:
    if not os.path.exists(d): os.makedirs(d)

# --- DATA MANAGEMENT ---
def load_json(path, default):
    try:
        with open(path, "r") as f:
            content = json.load(f)
            if isinstance(default, set): return set(content)
            return content
    except: return default

def _threaded_save_json(path, data):
    try:
        tmp_path = f"{path}.tmp"
        with open(tmp_path, "w") as f:
            json.dump(data, f)
        os.replace(tmp_path, path)
    except Exception as e:
        logging.error(f"Error saving JSON {path}: {e}")

def save_json(path, data):
    try:
        if isinstance(data, set):
            snapshot = list(data)
        elif isinstance(data, list):
            snapshot = list(data)
        elif isinstance(data, dict):
            snapshot = dict(data)
        else:
            snapshot = data
        threading.Thread(target=_threaded_save_json, args=(path, snapshot), daemon=True).start()
    except Exception as e:
        logging.error(f"save_json thread dispatch error: {e}")

ADMINS = load_json(ADMINS_FILE, {str(SUPER_ADMIN)})
USERS = load_json(USERS_FILE, set())
CHATS = load_json(CHATS_FILE, set())
CLONES = load_json(CLONES_FILE, {})
APPROVED_CHATS = load_json(APPROVED_FILE, {}) # chat_id -> {mode: "admin" or "all"}
BROADCAST_MSGS = set() # Set of message IDs to exclude from auto-delete

# --- GLOBAL STATE ---
bot_states = {}
clone_wizard = {} # uid -> {step, token, phone, hash, client}
active_clones = {} # token -> {bot, user, calls}
DOWNLOAD_CACHE = load_json(CACHE_FILE, {}) # query_is_v -> (fp, title, dur, thumb)

ACTIVE_TARGET = {}

def get_state(bot_id, chat_id):
    if bot_id not in bot_states: bot_states[bot_id] = {}
    if chat_id not in bot_states[bot_id]:
        bot_states[bot_id][chat_id] = {"queue": [], "is_playing": False, "current_data": None, "lock": asyncio.Lock(), "is_transitioning": False, "last_ui_msg": None, "last_ui_chat": None}
    return bot_states[bot_id][chat_id]

def is_file_in_use(file_path):
    if not file_path:
        return False
    for bot_id, chats in bot_states.items():
        for chat_id, st in chats.items():
            if st.get('current_data') and st['current_data'].get('file_path') == file_path:
                return True
            for task in st.get('queue', []):
                if task and len(task) > 0 and task[0] == file_path:
                    return True
    return False

def _sync_remove_file(file_path):
    try:
        if os.path.exists(file_path) and not is_file_in_use(file_path):
            os.remove(file_path)
            logging.info(f"DEBUG: Successfully deleted file from VPS storage: {file_path}")
    except Exception as e:
        logging.error(f"DEBUG: Error deleting file {file_path}: {e}")

async def safe_delete_file(file_path):
    if not file_path:
        return
    await asyncio.sleep(5)  # Wait for file handles to release
    threading.Thread(target=_sync_remove_file, args=(file_path,), daemon=True).start()


# --- UTILS ---
def get_ytdl_opts(file_path, video=False, client=None, is_youtube=True, use_cookies=True):
    """
    Build yt-dlp options.

    client=None means yt-dlp's own default YouTube client selection. This is
    intentionally the first attempt; explicit player clients are fallbacks only.
    """
    opts = {
        "quiet": True,
        "no_warnings": False,
        "noprogress": True,
        "outtmpl": f"{file_path}.%(ext)s",
        "geo_bypass": True,
        "nocheckcertificate": True,
        "noplaylist": True,
        "playlist_items": "1",
        "concurrent_fragment_downloads": 4,
        "retries": 2,
        "extractor_retries": 2,
        "fragment_retries": 2,
        "file_access_retries": 2,
        "socket_timeout": 20,
        "sleep_interval_requests": 1,
        "overwrites": True,
    }

    if is_youtube:
        active_cookie = find_cookies_file() if use_cookies else None
        if active_cookie and os.path.isfile(active_cookie) and os.path.getsize(active_cookie) > 0:
            opts["cookiefile"] = active_cookie
            logging.info("DEBUG: YouTube cookies enabled from configured cookie file")
        else:
            logging.warning("DEBUG: No non-empty YouTube cookies file found")

        # Do not set extractor_args for the first attempt. yt-dlp then uses
        # its current built-in default client strategy.
        if client and client != "default":
            opts["extractor_args"] = {
                "youtube": {"player_client": [client]}
            }

    if video:
        opts["format"] = "bestvideo[height<=480]+bestaudio/best[height<=480]/best"
        opts["merge_output_format"] = "mp4"
    else:
        opts["format"] = "bestaudio/best"

    return opts


def _youtube_search_url(query):
    """Resolve a ytsearch query to a canonical video URL without downloading."""
    search_opts = {
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "extract_flat": "in_playlist",
        "socket_timeout": 15,
    }
    with YoutubeDL(search_opts) as ytdl:
        info = ytdl.extract_info(f"ytsearch1:{query}", download=False)
    entries = (info or {}).get("entries") or []
    if not entries:
        return None
    entry = entries[0] or {}
    return entry.get("webpage_url") or (
        f"https://www.youtube.com/watch?v={entry['id']}" if entry.get("id") else None
    )


async def search_and_download(query, video=False):
    cache_key = f"{query}_{video}"
    cached = DOWNLOAD_CACHE.get(cache_key)
    if cached and len(cached) >= 4 and cached[0] and os.path.isfile(cached[0]):
        logging.info("DEBUG: Found %s in download cache", query)
        return cached

    loop = asyncio.get_running_loop()
    is_url = query.lower().startswith(("http://", "https://"))
    is_youtube = any(host in query.lower() for host in ("youtube.com", "youtu.be", "music.youtube.com"))

    # Required order:
    # 1) yt-dlp's default strategy
    # 2) direct YouTube URL (for search queries, resolve it after default fails)
    # 3) explicit YouTube player clients
    # 4) non-YouTube fallback providers (SoundCloud search)
    youtube_targets = []
    soundcloud_targets = []

    if is_url:
        if is_youtube:
            youtube_targets.append(query)
        else:
            soundcloud_targets.append((query, False, "default"))
    else:
        youtube_targets.append(f"ytsearch1:{query}")
        soundcloud_targets.append((f"scsearch1:{query}", False, "default"))

    attempt_number = 0

    async def run_attempt(target, yt, client_name):
        nonlocal attempt_number
        attempt_number += 1
        attempt_path = os.path.join(
            DOWNLOAD_DIR, f"{int(time.time())}_{uuid.uuid4().hex[:8]}_{attempt_number}"
        )
        opts = get_ytdl_opts(
            attempt_path,
            video=video,
            client=client_name,
            is_youtube=yt,
            use_cookies=yt,
        )
        logging.info(
            "DEBUG: yt-dlp attempt=%s target=%s client=%s video=%s",
            attempt_number, target, client_name or "yt-dlp-default", video,
        )

        def _extract():
            with YoutubeDL(opts) as ytdl:
                return ytdl.extract_info(target, download=True)

        try:
            info = await asyncio.wait_for(
                loop.run_in_executor(download_executor, _extract),
                timeout=55,
            )
            entry = info["entries"][0] if info and info.get("entries") else (info or {})
            downloaded = [
                fp for fp in glob.glob(f"{attempt_path}.*")
                if os.path.isfile(fp) and not fp.endswith((".part", ".ytdl"))
            ]
            if not downloaded:
                logging.warning("DEBUG: yt-dlp returned metadata but produced no output file")
                return None

            downloaded.sort(key=lambda fp: os.path.getsize(fp), reverse=True)
            final_path = downloaded[0]
            title = entry.get("title") or query
            duration = int(entry.get("duration") or 0)
            thumb = entry.get("thumbnail")
            if not thumb and yt and entry.get("id"):
                thumb = f"https://img.youtube.com/vi/{entry['id']}/hqdefault.jpg"

            logging.info(
                "DEBUG: Download successful: %s (%ss) -> %s",
                title, duration, final_path,
            )
            return final_path, title, duration, thumb
        except asyncio.TimeoutError:
            logging.error("DEBUG: Download timed out for %s (%s)", target, client_name)
        except Exception as exc:
            logging.warning(
                "DEBUG: Download failed target=%s client=%s: %s",
                target, client_name or "yt-dlp-default", exc,
            )
        finally:
            # Remove only this attempt's incomplete output; successful file is
            # retained because it no longer has a .part/.ytdl suffix.
            for fp in glob.glob(f"{attempt_path}.*"):
                if fp.endswith((".part", ".ytdl")):
                    try:
                        os.remove(fp)
                    except OSError:
                        pass
        return None

    # First attempt: yt-dlp default client behavior, with no forced player_client.
    for target in youtube_targets:
        result = await run_attempt(target, True, None)
        if result:
            DOWNLOAD_CACHE[cache_key] = result
            save_json(CACHE_FILE, DOWNLOAD_CACHE)
            return result

    # If the original request was a text search, resolve the result and retry
    # using its direct canonical YouTube URL before trying alternate clients.
    direct_url = query if (is_url and is_youtube) else None
    if not is_url and youtube_targets:
        try:
            direct_url = await asyncio.wait_for(
                loop.run_in_executor(download_executor, _youtube_search_url, query),
                timeout=20,
            )
        except Exception as exc:
            logging.warning("DEBUG: Could not resolve direct YouTube URL for %r: %s", query, exc)

    if direct_url:
        result = await run_attempt(direct_url, True, None)
        if result:
            DOWNLOAD_CACHE[cache_key] = result
            save_json(CACHE_FILE, DOWNLOAD_CACHE)
            return result

        # Alternate clients are strictly fallbacks, after default and direct URL.
        for client_name in (
            "android", "ios", "tv", "web_embedded", "mweb", "web_safari", "web"
        ):
            result = await run_attempt(direct_url, True, client_name)
            if result:
                DOWNLOAD_CACHE[cache_key] = result
                save_json(CACHE_FILE, DOWNLOAD_CACHE)
                return result

    # SoundCloud and other providers are attempted only after YouTube paths.
    for target, yt, client_name in soundcloud_targets:
        result = await run_attempt(target, yt, client_name)
        if result:
            DOWNLOAD_CACHE[cache_key] = result
            save_json(CACHE_FILE, DOWNLOAD_CACHE)
            return result

    logging.error("DEBUG: All download providers failed for query=%r", query)
    return None, None, None, None

async def ensure_user_in_chat(chat_id, user_client, bot_client):
    try:
        user_me = await user_client.get_me()
        user_id = user_me.id
        
        # 1. Force Peer Resolution
        try:
            chat_obj = await bot_client.get_chat(chat_id)
        except Exception as e:
            err_str = str(e).lower()
            logging.error(f"DEBUG: Bot could not resolve chat {chat_id}: {err_str}")
            if "peer_id_invalid" in err_str or "peer id invalid" in err_str or "peer" in err_str:
                raise Exception("Bot hasn't 'seen' this channel yet. Please forward any message from the channel to this bot, then try again!")
            raise Exception("Bot cannot access this chat. Make sure Bot is an ADMIN in the channel/group!")

        # 2. Check if already in chat
        try:
            await user_client.get_chat(chat_id)
            return
        except: pass

        # 3. Try Direct Add (Often fails in channels, works in groups)
        try:
            await bot_client.add_chat_members(chat_id, user_id)
            logging.info(f"DEBUG: Successfully added assistant directly to {chat_id}")
            return
        except Exception as e:
            logging.info(f"DEBUG: Direct add failed: {e}")

        # 4. Try joining via Invite Link (Crucial for Channels)
        try:
            # Check if there's a public username first
            if chat_obj.username:
                try:
                    await user_client.join_chat(chat_obj.username)
                    logging.info(f"DEBUG: Assistant joined via public username @{chat_obj.username}")
                    return
                except: pass

            # Generate or get an invite link
            invite = chat_obj.invite_link
            if not invite:
                logging.info(f"DEBUG: No existing invite link, generating a new one...")
                invite = await bot_client.export_chat_invite_link(chat_id)
            
            logging.info(f"DEBUG: Attempting to join via link: {invite}")
            await user_client.join_chat(invite)
            logging.info(f"DEBUG: Assistant successfully joined via link to {chat_id}")
            return
            
        except UserAlreadyParticipant:
            logging.info(f"DEBUG: Assistant is already a participant.")
            return
        except Exception as e:
            logging.error(f"DEBUG: Join via link failed completely: {e}")
            raise Exception(f"Automatic join failed. The Bot must have 'Invite Users' permission. Alternatively, add Assistant (ID: `{user_id}`) manually!")
            
    except Exception as e:
        logging.error(f"CRITICAL: ensure_user_in_chat failed: {e}")
        raise e

INST_CACHE = {}

async def get_or_create_instrumental(title, original_fp):
    if original_fp in INST_CACHE and os.path.exists(INST_CACHE[original_fp]):
        return INST_CACHE[original_fp]

    clean_title = re.sub(r'\(.*?\)|\[.*?\]|official|video|audio|lyric|lyrics|feat\..*|ft\..*|prod\..*', '', title, flags=re.IGNORECASE).strip()
    search_queries = [
        f"{clean_title} instrumental karaoke",
        f"{clean_title} karaoke",
        f"{clean_title} official instrumental"
    ]
    for q in search_queries:
        try:
            fp, dtitle, dur, thumb = await search_and_download(q, video=False)
            if fp and os.path.exists(fp):
                logging.info(f"DEBUG: Found 100% pure studio instrumental track: {dtitle} -> {fp}")
                INST_CACHE[original_fp] = fp
                return fp
        except Exception as e:
            logging.warning(f"DEBUG: Search for '{q}' failed: {e}")

    return original_fp

ALL_EFFECTS = [
    ("Normal", "normal"),
    ("No Vocals", "novocals"),
    ("Slowed", "slowedpure"),
    ("Deep Slowed", "deepslow"),
    ("Slowed + Reverb", "slowed"),
    ("Daycore", "daycore"),
    ("Speed Up", "speedup"),
    ("Nightcore", "nightcore"),
    ("Hyperpop", "hyperpop"),
    ("Bass Boost", "bass"),
    ("Super Bass", "subbass"),
    ("Concert Hall", "concerthall"),
    ("Grand Hall", "grandhall"),
    ("Cathedral Hall", "cathedral"),
    ("Studio Reverb", "studioreverb"),
    ("Club Reverb", "clubreverb"),
    ("8D Audio", "8d"),
    ("3D Spatial", "spatial"),
    ("Stereo Panner", "panner"),
    ("Phaser", "phaser"),
    ("Chorus", "chorus"),
    ("Vaporwave", "vaporwave"),
    ("Lo-Fi Chill", "lofi"),
    ("8-Bit Retro", "8bit"),
    ("Radio", "radio"),
    ("Treble Boost", "treble"),
    ("Pitch Down", "pitchdown"),
    ("Pitch Up", "pitchup"),
    ("Underwater", "underwater")
]

EFFECT_SLUG_MAP = {slug: name for name, slug in ALL_EFFECTS}

EFFECT_FILTERS = {
    "No Vocals": "stereotools=mlev=0.015625:slev=2.0:mode=lr>l-r,bandreject=f=1000:w=1.2,bass=g=12:f=100:w=0.6,treble=g=6:f=8000:w=0.5,volume=1.8",
    "Slowed": "atempo=0.82",
    "Deep Slowed": "atempo=0.72,bass=g=5:f=100,volume=1.2",
    "Slowed + Reverb": "atempo=0.85,aecho=0.8:0.88:60:0.4",
    "Daycore": "asetrate=48000*0.80,aresample=48000",
    "Speed Up": "atempo=1.30",
    "Nightcore": "asetrate=48000*1.25,aresample=48000",
    "Hyperpop": "asetrate=48000*1.15,aresample=48000,treble=g=8:f=7000:w=0.5,volume=1.2",
    "Bass Boost": "bass=g=5:f=110:w=0.5",
    "Super Bass": "bass=g=9:f=90:w=0.4",
    "Concert Hall": "aecho=0.8:0.88:100|200|350:0.4|0.3|0.25",
    "Grand Hall": "aecho=0.8:0.9:500|1000:0.4|0.25",
    "Cathedral Hall": "aecho=0.8:0.9:1000|2000:0.5|0.35",
    "Studio Reverb": "aecho=0.8:0.8:60|120:0.3|0.2",
    "Club Reverb": "aecho=0.8:0.9:40|80:0.5|0.3",
    "8D Audio": "aphaser=in_gain=0.7:out_gain=0.8:delay=3:decay=0.4:speed=0.5",
    "3D Spatial": "extrastereo=m=2.5",
    "Stereo Panner": "apulsator=mode=sine:hz=0.5:amount=0.9",
    "Phaser": "aphaser=in_gain=0.8:out_gain=0.9:delay=3:decay=0.5:speed=1",
    "Chorus": "chorus=0.7:0.9:55:0.4:0.25:2",
    "Vaporwave": "asetrate=48000*0.88,aresample=48000",
    "Lo-Fi Chill": "lowpass=f=3500,highpass=f=200,bass=g=5:f=120,volume=1.2",
    "8-Bit Retro": "lowpass=f=2500,highpass=f=400,volume=1.3",
    "Radio": "highpass=f=500,lowpass=f=3000,volume=1.6",
    "Treble Boost": "treble=g=12:f=6000:w=0.5,volume=1.1",
    "Pitch Down": "asetrate=48000*0.75,aresample=48000,atempo=1.333",
    "Pitch Up": "asetrate=48000*1.35,aresample=48000,atempo=0.74",
    "Underwater": "lowpass=f=600,volume=1.5"
}

def build_stream(file_path, offset=0, speed="1.0x", effects=None, is_video=False):
    speed_val = {"0.75x": 0.75, "1.0x": 1.0, "1.25x": 1.25, "1.5x": 1.5, "2.0x": 2.0}.get(speed, 1.0)
    # Always include aresample to keep audio clock perfectly in sync and prevent stutter/packet drops
    filters = ["aresample=48000:async=1:first_pts=0"]
    
    # Handle single string, list, set, or None
    if isinstance(effects, str):
        effects_list = [effects] if effects != "Normal" else []
    elif isinstance(effects, (list, set, tuple)):
        effects_list = [e for e in effects if e != "Normal"]
    else:
        effects_list = []
        
    for eff in effects_list:
        if eff in EFFECT_FILTERS:
            filters.append(EFFECT_FILTERS[eff])
            
    # Playback speed
    if speed_val != 1.0:
        filters.append(f"atempo={speed_val}")
        
    audio_start = ["-thread_queue_size", "4096", "-threads", "4"]
    if offset > 0:
        audio_start.extend(["-ss", str(int(offset))])
        
    ffmpeg_parts = ["--audio", "---start"] + audio_start
    if filters:
        ffmpeg_parts.extend(["---mid", "-af", ",".join(filters)])
        
    if is_video:
        video_start = ["-thread_queue_size", "4096", "-threads", "4"]
        if offset > 0:
            video_start.extend(["-ss", str(int(offset))])
        ffmpeg_parts.extend(["--video", "---start"] + video_start)
        
    ffmpeg_params = " ".join(ffmpeg_parts)
    
    # 48000 Hz mono matches Telegram WebRTC specifications exactly, eliminating video-call packet drops
    ap = AudioParameters(bitrate=48000, channels=1)
    if is_video:
        return MediaStream(file_path, video_parameters=VideoQuality.SD_480p, audio_parameters=ap, ffmpeg_parameters=ffmpeg_params)
    else:
        return MediaStream(file_path, audio_parameters=ap, video_flags=MediaStream.Flags.IGNORE, ffmpeg_parameters=ffmpeg_params)

COLOR_STYLES = ["primary", "success", "danger"]

_SHARED_SESSION = None
def get_shared_session():
    global _SHARED_SESSION
    if _SHARED_SESSION is None or _SHARED_SESSION.closed:
        connector = aiohttp.TCPConnector(limit=50, keepalive_timeout=60)
        _SHARED_SESSION = aiohttp.ClientSession(connector=connector)
    return _SHARED_SESSION

EMOJI_FILE = os.path.join(DATA_DIR, "all_custom_emojis.json")
CUSTOM_EMOJIS = {}
if os.path.exists(EMOJI_FILE):
    try:
        with open(EMOJI_FILE, "r") as f:
            CUSTOM_EMOJIS = json.load(f)
    except Exception:
        pass

def format_html(text: str) -> str:
    if not text:
        return text
    import re, html
    
    placeholders = {}
    idx = 0
    
    # Helper to register placeholder
    def add_ph(content):
        nonlocal idx
        key = f"___PH_{idx}___"
        idx += 1
        placeholders[key] = content
        return key

    # 1. Existing HTML links <a href="...">...</a>
    text = re.sub(
        r"<a\s+href=[\x27\x22]?(.*?)[\x27\x22]?>(.*?)</a>",
        lambda m: add_ph(f"<a href=\"{html.escape(m.group(1))}\">{html.escape(m.group(2))}</a>"),
        text,
        flags=re.IGNORECASE
    )

    # 2. Markdown links [label](url)
    text = re.sub(
        r"\[(.*?)\]\((.*?)\)",
        lambda m: add_ph(f"<a href=\"{html.escape(m.group(2))}\">{html.escape(m.group(1))}</a>"),
        text
    )

    # 3. Code `code`
    text = re.sub(
        r"`(.*?)`",
        lambda m: add_ph(f"<code>{html.escape(m.group(1))}</code>"),
        text
    )

    # 4. Bold **bold**
    text = re.sub(
        r"\*\*(.*?)\*\*",
        lambda m: add_ph(f"<b>{m.group(1)}</b>"),
        text
    )

    # 5. Escape all raw text (outside placeholders)
    text = html.escape(text)

    # 6. Restore placeholders repeatedly until all nested tags are fully resolved
    changed = True
    while changed:
        changed = False
        for k, v in list(placeholders.items()):
            if k in text:
                text = text.replace(k, v)
                changed = True

    # 7. Replace all custom animated emojis dynamically sorted by length descending
    if not hasattr(format_html, "_sorted_emojis"):
        format_html._sorted_emojis = sorted(CUSTOM_EMOJIS.items(), key=lambda x: len(x[0]), reverse=True)
    
    for emo, eid in format_html._sorted_emojis:
        if emo in text and f'emoji-id="{eid}"' not in text:
            text = text.replace(emo, f'<tg-emoji emoji-id="{eid}">{emo}</tg-emoji>')
            
    # 8. Quote format wrapper
    if not text.startswith("<blockquote>") and not text.startswith("<blockquote"):
        text = f"<blockquote>{text}</blockquote>"
        
    return text

async def _post_json(token, endpoint, payload):
    url = f"https://api.telegram.org/bot{token}/{endpoint}"
    try:
        session = get_shared_session()
        async with session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=4.0)) as resp:
            data = await resp.json()
            if data and data.get("ok"):
                if isinstance(data.get("result"), dict):
                    data["result"]["_used_token"] = token
                return data
            return data
    except Exception as e:
        logging.error(f"Bot API {endpoint} error on {token[:8] if token else 'None'}: {e}")
        return None

async def bot_api_send_message(token, chat_id, text, reply_markup_dict=None):
    payload = {
        "chat_id": chat_id,
        "text": format_html(text),
        "parse_mode": "HTML"
    }
    if reply_markup_dict:
        payload["reply_markup"] = reply_markup_dict
    
    res = await _post_json(token, "sendMessage", payload)
    if (not res or not res.get("ok")) and token != BOT_TOKEN:
        res = await _post_json(BOT_TOKEN, "sendMessage", payload)
    return res

async def bot_api_edit_message(token, chat_id, message_id, text, reply_markup_dict=None):
    payload = {
        "chat_id": chat_id,
        "message_id": message_id,
        "text": format_html(text),
        "parse_mode": "HTML"
    }
    if reply_markup_dict:
        payload["reply_markup"] = reply_markup_dict
    res = await _post_json(token, "editMessageText", payload)
    if (not res or not res.get("ok")) and token != BOT_TOKEN:
        res = await _post_json(BOT_TOKEN, "editMessageText", payload)
    return res

async def send_smart_reply(m, text, reply_markup_dict=None, bot_token=None):
    cid = m.chat.id
    tok = bot_token or getattr(getattr(m, "_client", None), "bot_token", None) or BOT_TOKEN
    res = await bot_api_send_message(tok, cid, text, reply_markup_dict)
    if res and res.get("ok"):
        return res
    import re
    clean_text = re.sub(r'<tg-emoji emoji-id="[^"]*">(.*?)</tg-emoji>', r'\1', text)
    try:
        return await m.reply(clean_text)
    except Exception:
        return None

async def bot_api_send_photo(token, chat_id, photo, caption, reply_markup_dict=None):
    session = get_shared_session()
    
    # Pre-download photo on VPS to prevent Telegram URL fetching errors and guarantee colors
    img_bytes = None
    if isinstance(photo, str):
        if photo.startswith("http://") or photo.startswith("https://"):
            try:
                headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
                async with session.get(photo, headers=headers, timeout=aiohttp.ClientTimeout(total=4.0)) as r:
                    if r.status == 200:
                        img_bytes = await r.read()
            except Exception as e:
                logging.warning(f"Failed to pre-download photo URL {photo}: {e}")
        elif os.path.exists(photo):
            try:
                with open(photo, "rb") as f:
                    img_bytes = f.read()
            except Exception as e:
                logging.warning(f"Failed to read local photo file {photo}: {e}")
    elif isinstance(photo, bytes):
        img_bytes = photo

    async def _try_send(cur_tok):
        url = f"https://api.telegram.org/bot{cur_tok}/sendPhoto"
        try:
            if img_bytes:
                data = aiohttp.FormData()
                data.add_field("chat_id", str(chat_id))
                data.add_field("caption", format_html(caption))
                data.add_field("parse_mode", "HTML")
                if reply_markup_dict:
                    data.add_field("reply_markup", json.dumps(reply_markup_dict) if isinstance(reply_markup_dict, dict) else reply_markup_dict)
                data.add_field("photo", img_bytes, filename="thumb.jpg", content_type="image/jpeg")
                async with session.post(url, data=data, timeout=aiohttp.ClientTimeout(total=8.0)) as resp:
                    res = await resp.json()
                    if res and res.get("ok"):
                        if isinstance(res.get("result"), dict):
                            res["result"]["_used_token"] = cur_tok
                        return res
            
            # Fallback to direct JSON payload if image bytes not obtained
            payload = {
                "chat_id": chat_id,
                "photo": photo if isinstance(photo, str) else "",
                "caption": format_html(caption),
                "parse_mode": "HTML"
            }
            if reply_markup_dict:
                payload["reply_markup"] = reply_markup_dict
            async with session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=6.0)) as resp:
                res = await resp.json()
                if res and res.get("ok"):
                    if isinstance(res.get("result"), dict):
                        res["result"]["_used_token"] = cur_tok
                    return res
                return res
        except Exception as e:
            logging.error(f"bot_api_send_photo error on {cur_tok[:8] if cur_tok else 'None'}: {e}")
            return None

    res = await _try_send(token)
    if (not res or not res.get("ok")) and token != BOT_TOKEN:
        res = await _try_send(BOT_TOKEN)
    return res

async def bot_api_edit_text(token, chat_id, message_id, text, reply_markup_dict=None):
    payload = {
        "chat_id": chat_id,
        "message_id": message_id,
        "text": format_html(text),
        "parse_mode": "HTML"
    }
    if reply_markup_dict:
        payload["reply_markup"] = reply_markup_dict
    res = await _post_json(token, "editMessageText", payload)
    if (not res or not res.get("ok")) and token != BOT_TOKEN:
        res = await _post_json(BOT_TOKEN, "editMessageText", payload)
    return res

async def bot_api_edit_markup(token, chat_id, message_id, reply_markup_dict):
    payload = {
        "chat_id": chat_id,
        "message_id": message_id,
        "reply_markup": reply_markup_dict
    }
    res = await _post_json(token, "editMessageReplyMarkup", payload)
    if (not res or not res.get("ok")) and token != BOT_TOKEN:
        res = await _post_json(BOT_TOKEN, "editMessageReplyMarkup", payload)
    return res

async def bot_api_delete_message(token, chat_id, message_id):
    payload = {
        "chat_id": chat_id,
        "message_id": message_id
    }
    res = await _post_json(token, "deleteMessage", payload)
    if (not res or not res.get("ok")) and token != BOT_TOKEN:
        res = await _post_json(BOT_TOKEN, "deleteMessage", payload)
    return res

USER_CACHE = {}

async def resolve_user_profile(user_id, chat_id=None, bot_client=None, user_client=None):
    if not user_id:
        return "User", "No username"
    
    uid_int = int(user_id) if str(user_id).isdigit() or (str(user_id).startswith("-") and str(user_id)[1:].isdigit()) else user_id
    if uid_int in USER_CACHE:
        cached = USER_CACHE[uid_int]
        if cached.get("name") and not cached["name"].startswith("User "):
            return cached["name"], cached.get("username", "No username")

    # 1. Try bot_client get_chat_member if chat_id provided
    if bot_client and chat_id:
        try:
            m = await bot_client.get_chat_member(chat_id, uid_int)
            if m and m.user:
                name = m.user.first_name + (f" {m.user.last_name}" if m.user.last_name else "")
                uname = f"@{m.user.username}" if m.user.username else "No username"
                USER_CACHE[uid_int] = {"name": name, "username": uname}
                return name, uname
        except Exception:
            pass

    # 2. Try user_client get_chat_member (assistant account in group)
    if user_client and chat_id:
        try:
            m = await user_client.get_chat_member(chat_id, uid_int)
            if m and m.user:
                name = m.user.first_name + (f" {m.user.last_name}" if m.user.last_name else "")
                uname = f"@{m.user.username}" if m.user.username else "No username"
                USER_CACHE[uid_int] = {"name": name, "username": uname}
                return name, uname
        except Exception:
            pass

    # 3. Try user_client get_users
    if user_client:
        try:
            u = await user_client.get_users(uid_int)
            if u:
                name = u.first_name + (f" {u.last_name}" if u.last_name else "")
                uname = f"@{u.username}" if u.username else "No username"
                USER_CACHE[uid_int] = {"name": name, "username": uname}
                return name, uname
        except Exception:
            pass

    # 4. Try bot_client get_users
    if bot_client:
        try:
            u = await bot_client.get_users(uid_int)
            if u:
                name = u.first_name + (f" {u.last_name}" if u.last_name else "")
                uname = f"@{u.username}" if u.username else "No username"
                USER_CACHE[uid_int] = {"name": name, "username": uname}
                return name, uname
        except Exception:
            pass

    # 5. Check if user_id is SUPER_ADMIN
    if uid_int == SUPER_ADMIN:
        name = "𓆩𓆩𝐅ᴇᴀʀʟᴇssツ ⁴⁵𓆪𓆪 </> 🜲"
        uname = "@Prime_Fearless_45"
        USER_CACHE[uid_int] = {"name": name, "username": uname}
        return name, uname

    return f"User {user_id}", "No username"

EVENT_COOLDOWN = {}

def should_send_event(event_key, cooldown_seconds=10):
    now = time.time()
    last_time = EVENT_COOLDOWN.get(event_key, 0)
    if (now - last_time) < cooldown_seconds:
        return False
    EVENT_COOLDOWN[event_key] = now
    return True

def get_effects_menu_markup(chat_id, current_effects=None):
    if current_effects is None: current_effects = []
    elif isinstance(current_effects, str): current_effects = [current_effects] if current_effects != "Normal" else []
    keyboard = []
    row = []
    for name, slug in ALL_EFFECTS:
        if slug == "normal":
            is_active = (len(current_effects) == 0 or "Normal" in current_effects)
            label = "✅ Normal (Clean)" if is_active else "Normal (Clean)"
            btn_style = "success" if is_active else "primary"
        else:
            is_active = (name in current_effects)
            label = f"✅ {name}" if is_active else name
            btn_style = "success" if is_active else "primary"
        row.append(InlineKeyboardButton(label, callback_data=f"set_eff:{slug}:{chat_id}", style=btn_style))
        if len(row) == 2:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)
    keyboard.append([
        InlineKeyboardButton("🔄 Reset All to Normal", callback_data=f"set_eff:normal:{chat_id}", style="danger"),
        InlineKeyboardButton("« Back to Player", callback_data=f"back_player:{chat_id}", style="primary")
    ])
    return InlineKeyboardMarkup(keyboard)

def get_effects_menu_json(chat_id, current_effects=None):
    if current_effects is None: current_effects = []
    elif isinstance(current_effects, str): current_effects = [current_effects] if current_effects != "Normal" else []
    keyboard = []
    row = []
    for name, slug in ALL_EFFECTS:
        if slug == "normal":
            is_active = (len(current_effects) == 0 or "Normal" in current_effects)
            label = "✅ Normal (Clean)" if is_active else "Normal (Clean)"
            btn_style = "success" if is_active else "primary"
        else:
            is_active = (name in current_effects)
            label = f"✅ {name}" if is_active else name
            btn_style = "success" if is_active else "primary"
        row.append({"text": label, "callback_data": f"set_eff:{slug}:{chat_id}", "style": btn_style})
        if len(row) == 2:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)
    keyboard.append([
        {"text": "🔄 Reset All to Normal", "callback_data": f"set_eff:normal:{chat_id}", "style": "danger"},
        {"text": "« Back to Player", "callback_data": f"back_player:{chat_id}", "style": "primary"}
    ])
    return {"inline_keyboard": keyboard}

def get_controls_json(bot_id, chat_id, elapsed=0, total=0, randomize=True):
    st = get_state(bot_id, chat_id); info = st['current_data']; is_p = info.get('is_paused', False) if info else False
    speed = info.get('speed', '1.0x') if info else '1.0x'
    effects = info.get('effects', [info.get('effect', 'Normal')]) if info else ['Normal']
    if not effects or effects == ['Normal']:
        eff_label = "Audio Effects: Normal"
    elif len(effects) == 1:
        eff_label = f"Audio Effects: {effects[0]}"
    else:
        eff_label = f"Audio Effects ({len(effects)}): {', '.join(effects[:2])}{'...' if len(effects) > 2 else ''}"
    bar_l = 10; perc = (elapsed / total) * 100 if total > 0 else 0; filled = int(bar_l * perc // 100)
    bar = "━" * min(filled, bar_l) + "🔘" + "━" * max(0, bar_l - filled)
    cur_s, tot_s = f"{elapsed // 60}:{elapsed % 60:02d}", f"{total // 60}:{total % 60:02d}"

    def rnd_style():
        return random.choice(COLOR_STYLES) if randomize else "primary"

    return {
        "inline_keyboard": [
            [
                {"text": f"⏳ {cur_s} {bar} {tot_s}", "callback_data": "bar_ignore", "style": rnd_style()}
            ],
            [
                {"text": "Resume" if is_p else "Pause", "callback_data": f"pause_resume:{chat_id}", "style": "success" if is_p else rnd_style()},
                {"text": "Stop", "callback_data": f"stop:{chat_id}", "style": "danger"}
            ],
            [
                {"text": "« -20s", "callback_data": f"seek_back:{chat_id}", "style": rnd_style()},
                {"text": "🔄", "callback_data": f"replay:{chat_id}", "style": rnd_style()},
                {"text": "+20s »", "callback_data": f"seek_fwd:{chat_id}", "style": rnd_style()}
            ],
            [
                {"text": "Skip to Next", "callback_data": f"skip:{chat_id}", "style": rnd_style()},
                {"text": f"Speed: {speed}", "callback_data": f"speed:{chat_id}", "style": rnd_style()}
            ],
            [
                {"text": eff_label, "callback_data": f"effect:{chat_id}", "style": rnd_style()}
            ]
        ]
    }

def get_controls_markup(bot_id, chat_id, elapsed=0, total=0, randomize=True):
    st = get_state(bot_id, chat_id); info = st['current_data']; is_p = info.get('is_paused', False) if info else False
    speed = info.get('speed', '1.0x') if info else '1.0x'
    effects = info.get('effects', [info.get('effect', 'Normal')]) if info else ['Normal']
    if not effects or effects == ['Normal']:
        eff_label = "Audio Effects: Normal"
    elif len(effects) == 1:
        eff_label = f"Audio Effects: {effects[0]}"
    else:
        eff_label = f"Audio Effects ({len(effects)}): {', '.join(effects[:2])}{'...' if len(effects) > 2 else ''}"
    bar_l = 10; perc = (elapsed / total) * 100 if total > 0 else 0; filled = int(bar_l * perc // 100)
    bar = "━" * min(filled, bar_l) + "🔘" + "━" * max(0, bar_l - filled)
    cur_s, tot_s = f"{elapsed // 60}:{elapsed % 60:02d}", f"{total // 60}:{total % 60:02d}"

    def rnd_style():
        return random.choice(COLOR_STYLES) if randomize else "primary"

    return InlineKeyboardMarkup([
        [InlineKeyboardButton(f"⏳ {cur_s} {bar} {tot_s}", callback_data="bar_ignore", style=rnd_style())],
        [
            InlineKeyboardButton("Resume" if is_p else "Pause", callback_data=f"pause_resume:{chat_id}", style="success" if is_p else rnd_style()),
            InlineKeyboardButton("Stop", callback_data=f"stop:{chat_id}", style="danger")
        ],
        [
            InlineKeyboardButton("« -20s", callback_data=f"seek_back:{chat_id}", style=rnd_style()),
            InlineKeyboardButton("🔄", callback_data=f"replay:{chat_id}", style=rnd_style()),
            InlineKeyboardButton("+20s »", callback_data=f"seek_fwd:{chat_id}", style=rnd_style())
        ],
        [
            InlineKeyboardButton("Skip to Next", callback_data=f"skip:{chat_id}", style=rnd_style()),
            InlineKeyboardButton(f"Speed: {speed}", callback_data=f"speed:{chat_id}", style=rnd_style())
        ],
        [
            InlineKeyboardButton(eff_label, callback_data=f"effect:{chat_id}", style=rnd_style())
        ]
    ])

async def progress_loop(bot_id, chat_id, message, duration, bot_token=None):
    msg_id = message.id if hasattr(message, 'id') else (message.get('message_id') if isinstance(message, dict) else message)
    chat_num = message.chat.id if hasattr(message, 'chat') else (message.get('chat', {}).get('id', chat_id) if isinstance(message, dict) else chat_id)
    while True:
        st = get_state(bot_id, chat_id)
        if not st['is_playing'] or not st['current_data']: break
        if st.get('in_effects_menu'): await asyncio.sleep(2); continue
        if st['current_data']['is_paused']: await asyncio.sleep(5); continue
        el = int(time.time() - st['current_data']['start_time']) + st['current_data']['offset']
        if el >= duration: break

        tok = st.get('last_ui_token') or bot_token or BOT_TOKEN
        markup_json = get_controls_json(bot_id, chat_id, el, duration, randomize=True)
        res = await bot_api_edit_markup(tok, chat_num, msg_id, markup_json)
        if not res or not res.get("ok"):
            try:
                if hasattr(message, 'edit_reply_markup'):
                    await message.edit_reply_markup(reply_markup=get_controls_markup(bot_id, chat_id, el, duration, randomize=True))
            except: pass
        await asyncio.sleep(5)

async def monitor_vc_participants(bot_id, chat_id, calls_client, bot_client, user_client, bot_token):
    st = get_state(bot_id, chat_id)
    if st.get('is_monitoring_vc'):
        return
    st['is_monitoring_vc'] = True
    tok = bot_token or BOT_TOKEN
    known_participants = set()
    
    try:
        init_parts = await calls_client.get_participants(chat_id)
        if init_parts:
            known_participants = {p.user_id for p in init_parts if getattr(p, 'user_id', None)}
    except Exception:
        pass

    bot_uid = bot_client.me.id if bot_client.me else None
    user_uid = user_client.me.id if user_client.me else None

    while st.get('is_playing') or st.get('is_monitoring_vc'):
        try:
            await asyncio.sleep(2.5)
            if not st.get('is_playing'):
                break
            
            parts = await calls_client.get_participants(chat_id)
            if parts is None:
                continue
            
            current_ids = {p.user_id for p in parts if getattr(p, 'user_id', None) and p.user_id not in [bot_uid, user_uid]}
            joined_ids = current_ids - known_participants
            left_ids = known_participants - current_ids

            for p_uid in joined_ids:
                # Delete any pending invitation message for this user immediately upon joining VC
                if 'pending_vc_invites' in st and p_uid in st['pending_vc_invites']:
                    inv_mid, inv_tok = st['pending_vc_invites'].pop(p_uid)
                    try:
                        asyncio.create_task(bot_api_delete_message(inv_tok, chat_id, inv_mid))
                    except Exception:
                        pass

                name, uname = await resolve_user_profile(p_uid, chat_id=chat_id, bot_client=bot_client, user_client=user_client)
                st['last_active_user_info'] = {"name": name, "username": uname, "id": p_uid}

                if should_send_event(f"join:{chat_id}:{p_uid}", 15):
                    join_msg = (
                        "🎤 **User Joined VC**\n\n"
                        f"👋 {name} ({uname}) joined the voice chat.\n\n"
                        f"🆔 User ID: {p_uid}\n\n"
                        f"👤 {name} | {uname} | ID: {p_uid}"
                    )
                    res_api = await bot_api_send_message(tok, chat_id, join_msg)
                    if res_api and res_api.get("ok"):
                        msg_id = res_api["result"]["message_id"]
                        async def _del_j(m_id):
                            await asyncio.sleep(20)
                            await bot_api_delete_message(tok, chat_id, m_id)
                        asyncio.create_task(_del_j(msg_id))

            for p_uid in left_ids:
                name, uname = await resolve_user_profile(p_uid, chat_id=chat_id, bot_client=bot_client, user_client=user_client)
                st['last_active_user_info'] = {"name": name, "username": uname, "id": p_uid}

                if should_send_event(f"leave:{chat_id}:{p_uid}", 15):
                    leave_msg = (
                        "🚪 **User Left VC**\n\n"
                        f"👋 {name} ({uname}) left the voice chat.\n\n"
                        f"🆔 User ID: {p_uid}\n\n"
                        f"👤 {name} | {uname} | ID: {p_uid}"
                    )
                    res_api = await bot_api_send_message(tok, chat_id, leave_msg)
                    if res_api and res_api.get("ok"):
                        msg_id = res_api["result"]["message_id"]
                        async def _del_l(m_id):
                            await asyncio.sleep(20)
                            await bot_api_delete_message(tok, chat_id, m_id)
                        asyncio.create_task(_del_l(msg_id))

            known_participants = current_ids
        except Exception as e_poll:
            logging.debug(f"DEBUG: Participant poller error: {e_poll}")

    st['is_monitoring_vc'] = False

def clean_song_tokens(title: str, artist_seed: str = "") -> set:
    t = re.sub(r"\(.*?\)|\[.*?\]|official|video|audio|lyric|lyrics|feat\..*|ft\..*|prod\..*|full song|hd|4k|remix|slowed|reverb|by|song|songs|music|records", "", title, flags=re.IGNORECASE)
    if artist_seed:
        for aw in artist_seed.split():
            if len(aw) > 1:
                t = re.sub(re.escape(aw), "", t, flags=re.IGNORECASE)
    t = re.sub(r"[^\w\s]", "", t)
    return {w for w in t.lower().split() if len(w) > 1}

def is_duplicate_song(title: str, seen_titles: list, artist_seed: str = "") -> bool:
    if not seen_titles:
        return False
    toks = clean_song_tokens(title, artist_seed)
    if not toks:
        return any(title.lower() in st.lower() or st.lower() in title.lower() for st in seen_titles)
    for st in seen_titles:
        s_toks = clean_song_tokens(st, artist_seed)
        if not s_toks: continue
        overlap = len(toks.intersection(s_toks))
        if overlap > 0 and (overlap / min(len(toks), len(s_toks))) >= 0.6:
            return True
    return False

async def get_autoplay_next_track(bot_id, chat_id, seed_query, is_video=False):
    st = get_state(bot_id, chat_id)
    if 'played_history' not in st:
        st['played_history'] = set()
    if 'played_titles' not in st:
        st['played_titles'] = []
        
    loop = asyncio.get_event_loop()
    
    variations = [
        f"{seed_query} top songs",
        f"{seed_query} hit songs",
        f"{seed_query} latest tracks",
        f"{seed_query} popular songs",
        f"{seed_query} album songs",
        f"best songs of {seed_query}",
        f"{seed_query} all songs",
        f"{seed_query} playlist hits"
    ]
    random.shuffle(variations)
    
    search_opts = {
        "format": "bestaudio/best" if not is_video else "best",
        "extract_flat": True,
        "quiet": True,
        "no_warnings": True,
        "nocheckcertificate": True,
        "cookiefile": COOKIES_FILE,
        "noplaylist": True,
    }
    
    for query_term in variations[:3]:
        yt_query = f"ytsearch35:{query_term}"
        try:
            with YoutubeDL(search_opts) as ytdl:
                info = await asyncio.wait_for(loop.run_in_executor(None, lambda: ytdl.extract_info(yt_query, download=False)), timeout=15)
                entries = info.get("entries", []) if info else []
                
                candidates = []
                for e in entries:
                    if not e: continue
                    vid_id = e.get("id") or e.get("url")
                    title = e.get("title", "")
                    dur = int(e.get("duration") or 0)
                    
                    # Filter out long jukeboxes or tiny clips
                    if dur > 600 or (dur > 0 and dur < 30):
                        continue
                    # Skip previously played video IDs or titles
                    if vid_id in st['played_history'] or title in st['played_history']:
                        continue
                    # Check fuzzy title duplicate against history
                    if is_duplicate_song(title, st['played_titles'], seed_query):
                        continue
                    candidates.append((vid_id, title))
                    
                if candidates:
                    chosen_id, chosen_title = random.choice(candidates[:10])
                    st['played_history'].add(chosen_id)
                    st['played_history'].add(chosen_title)
                    st['played_titles'].append(chosen_title)
                    
                    target_url = f"https://www.youtube.com/watch?v={chosen_id}" if len(chosen_id) == 11 else chosen_title
                    fp, dtitle, dur, thumb = await search_and_download(target_url, video=is_video)
                    if fp and os.path.exists(fp):
                        return (fp, dtitle or chosen_title, dur, thumb, is_video)
        except Exception as e:
            logging.error(f"DEBUG: get_autoplay_next_track query '{query_term}' error: {e}")
            continue
            
    return None

async def ensure_autoplay_prebuffer(bot_id, chat_id):
    st = get_state(bot_id, chat_id)
    if not st.get('autoplay') or not st.get('autoplay_query'):
        return
    if len(st['queue']) >= 1:
        return
    if st.get('is_buffering_autoplay'):
        return
    st['is_buffering_autoplay'] = True
    try:
        seed = st['autoplay_query']
        logging.info(f"DEBUG: Pre-buffering upcoming autoplay track for '{seed}' in {chat_id} so queue is never empty...")
        next_task = await get_autoplay_next_track(bot_id, chat_id, seed, is_video=st.get('is_video', False))
        if next_task:
            fp, title, dur, thumb, is_v = next_task
            st['queue'].append((fp, title, dur, thumb, is_v, chat_id, f"Autoplay ({seed})", None))
            logging.info(f"DEBUG: Successfully pre-buffered next autoplay track: '{title}'")
    except Exception as e:
        logging.error(f"DEBUG: ensure_autoplay_prebuffer error: {e}")
    finally:
        st['is_buffering_autoplay'] = False

async def play_next(bot_id, chat_id, user_client, bot_client, calls_client, retry_count=0):
    st = get_state(bot_id, chat_id)
    if st['is_transitioning'] and retry_count == 0: return

    async with st['lock']:
        st['is_transitioning'] = True
        try:
            old_fp = None
            if retry_count == 0 and st.get('current_data'):
                old_fp = st['current_data'].get('file_path')

            if not st['queue'] and retry_count == 0:
                if st.get('autoplay') and st.get('autoplay_query'):
                    seed = st['autoplay_query']
                    logging.info(f"DEBUG: Queue empty in {chat_id}, Autoplay is ACTIVE for '{seed}'. Fetching next track...")
                    next_task = await get_autoplay_next_track(bot_id, chat_id, seed, is_video=st.get('is_video', False))
                    if next_task:
                        fp, title, dur, thumb, is_v = next_task
                        st['queue'].append((fp, title, dur, thumb, is_v, chat_id, f"Autoplay ({seed})", None))
                        logging.info(f"DEBUG: Autoplay queued next track: {title}")

            if not st['queue'] and retry_count == 0:
                logging.info(f"DEBUG: Queue empty for {chat_id}")
                st['is_playing'] = False
                st['current_data'] = None
                if st.get('last_ui_msg'):
                    old_ui_chat = st.get('last_ui_chat', chat_id)
                    try: await bot_client.delete_messages(old_ui_chat, st['last_ui_msg'])
                    except: pass
                    st['last_ui_msg'] = None
                    st['last_ui_chat'] = None
                try: await asyncio.wait_for(calls_client.leave_call(chat_id), timeout=10)
                except: pass
                if old_fp:
                    asyncio.create_task(safe_delete_file(old_fp))
                return

            if retry_count == 0:
                task = st['queue'].pop(0)
                if len(task) == 8:
                    fp, title, dur, thumb, is_v, origin_chat, requester, query_msg_id = task
                elif len(task) == 7:
                    fp, title, dur, thumb, is_v, origin_chat, requester = task
                    query_msg_id = None
                elif len(task) == 6:
                    fp, title, dur, thumb, is_v, origin_chat = task
                    requester = "Unknown"
                    query_msg_id = None
                else:
                    fp, title, dur, thumb, is_v = task
                    origin_chat = chat_id
                    requester = "Unknown"
                    query_msg_id = None
                
                active_speed = st.get('active_speed', '1.0x')
                active_effect = st.get('active_effect', 'Normal')
                active_effects = st.get('active_effects', [active_effect] if active_effect != 'Normal' else [])
                st['current_data'] = {'file_path': fp, 'title': title, 'duration': dur, 'start_time': time.time(), 'offset': 0, 'is_video': is_v, 'is_paused': False, 'origin_chat': origin_chat, 'query': title, 'requester': requester, 'query_msg_id': query_msg_id, 'speed': active_speed, 'effect': active_effect, 'effects': active_effects}
                if old_fp:
                    asyncio.create_task(safe_delete_file(old_fp))
            else:
                # Retry logic
                cur = st['current_data']
                fp, title, dur, thumb, is_v, requester, query_msg_id = cur['file_path'], cur['title'], cur['duration'], None, cur['is_video'], cur.get('requester', 'Unknown'), cur.get('query_msg_id')
                origin_chat = cur.get('origin_chat', chat_id)
                logging.info(f"DEBUG: Retrying playback for {title} (attempt {retry_count+1})")

                # If file missing, try to re-download using the title as query
                if not os.path.exists(fp):
                    logging.warning(f"DEBUG: File missing for {title}, attempting re-download...")
                    fp, _, _, _ = await search_and_download(title, is_v)
                    if not fp:
                        raise FileNotFoundError(f"Could not re-download {title}")
                    cur['file_path'] = fp

            if not os.path.exists(fp):
                raise FileNotFoundError(f"File not found: {fp}")

            st['is_playing'] = True
            if st.get('autoplay'):
                asyncio.create_task(ensure_autoplay_prebuffer(bot_id, chat_id))
            logging.info(f"DEBUG: Starting playback for {title} (is_v={is_v}, path={fp[:50]}...)")

            try:
                # Robustness: Explicitly leave call before playing next if skipping or if transitioning 
                # to ensure fresh state and avoid glitches.
                if st.get('skip_requested'):
                    try: await asyncio.wait_for(calls_client.leave_call(chat_id), timeout=5)
                    except: pass
                    st['skip_requested'] = False # Reset flag

                speed = st['current_data'].get('speed', '1.0x')
                effects = st['current_data'].get('effects', [st['current_data'].get('effect', 'Normal')])
                if "No Vocals" in effects:
                    target_fp = await get_or_create_instrumental(title, fp)
                else:
                    target_fp = fp
                stream = build_stream(target_fp, offset=0, speed=speed, effects=effects, is_video=is_v)

                await asyncio.sleep(1.0)
                await asyncio.wait_for(calls_client.play(chat_id, stream), timeout=60)
                logging.info(f"DEBUG: Playing {title} on {chat_id} (speed={speed}, effects={effects})")

                if retry_count == 0 or st.get('refresh_requested'):
                    st['refresh_requested'] = False
                    # Delete old "Now Playing" message if it exists
                    if st.get('last_ui_msg'):
                        old_ui_chat = st.get('last_ui_chat', origin_chat)
                        try: await bot_client.delete_messages(old_ui_chat, st['last_ui_msg'])
                        except: pass
                        st['last_ui_msg'] = None
                        st['last_ui_chat'] = None
                    
                    dur_str = f"{dur // 60}:{dur % 60:02d}"
                    cap = (
                        f"🎧 **Now Streaming**\n"
                        f"┌ 🎶 **Title:** {title}\n"
                        f"├ ⏰ **Duration:** {dur_str}\n"
                        f"└ 👤 **Requested by:** {requester}"
                    )
                    
                    b_tok = getattr(bot_client, "bot_token", None) or BOT_TOKEN
                    markup_json = get_controls_json(bot_id, chat_id, 0, dur, randomize=True)
                    actual_thumb = task[3] if retry_count == 0 else None
                    ui = None
                    used_tok = b_tok
                    if actual_thumb:
                        res_api = await bot_api_send_photo(b_tok, origin_chat, actual_thumb, cap, markup_json)
                        if res_api and res_api.get("ok"):
                            ui = res_api["result"]
                            used_tok = res_api["result"].get("_used_token", b_tok)
                    if not ui:
                        res_api = await bot_api_send_message(b_tok, origin_chat, cap, markup_json)
                        if res_api and res_api.get("ok"):
                            ui = res_api["result"]
                            used_tok = res_api["result"].get("_used_token", b_tok)

                    if not ui:
                        markup = get_controls_markup(bot_id, chat_id, 0, dur)
                        try: 
                            if actual_thumb: ui = await asyncio.wait_for(bot_client.send_photo(origin_chat, photo=actual_thumb, caption=format_html(cap), parse_mode=enums.ParseMode.HTML, reply_markup=markup), timeout=15)
                            else: ui = await asyncio.wait_for(bot_client.send_message(origin_chat, text=format_html(cap), parse_mode=enums.ParseMode.HTML, reply_markup=markup), timeout=15)
                        except Exception: 
                            try: ui = await asyncio.wait_for(bot_client.send_message(origin_chat, text=format_html(cap), parse_mode=enums.ParseMode.HTML, reply_markup=markup), timeout=15)
                            except Exception: pass
                    
                    msg_id_val = ui.id if hasattr(ui, 'id') else (ui.get('message_id') if isinstance(ui, dict) else None)
                    st['last_ui_msg'] = msg_id_val
                    st['last_ui_chat'] = origin_chat
                    st['last_ui_token'] = used_tok
                    # Delete the original query message if not already deleted
                    if query_msg_id:
                        try: await bot_client.delete_messages(origin_chat, query_msg_id)
                        except: pass
                    
                    asyncio.create_task(progress_loop(bot_id, chat_id, ui, dur, bot_token=used_tok))
                    asyncio.create_task(monitor_vc_participants(bot_id, chat_id, calls_client, bot_client, user_client, used_tok))

            except asyncio.TimeoutError:
                logging.error(f"DEBUG: Playback TIMEOUT for {title}. Resetting call...")
                try: await asyncio.wait_for(calls_client.leave_call(chat_id), timeout=10)
                except: pass
                if retry_count < 2:
                    asyncio.create_task(play_next(bot_id, chat_id, user_client, bot_client, calls_client, retry_count + 1))
                else:
                    try: await bot_client.send_message(origin_chat, f"⚠️ **Playback Failed:** `{title}`\nReason: Timeout after 3 attempts.")
                    except: pass
                    asyncio.create_task(play_next(bot_id, chat_id, user_client, bot_client, calls_client))

            except Exception as e:
                err_msg = str(e) or e.__class__.__name__
                logging.error(f"DEBUG: Playback error for {title}: {err_msg}")
                if "CHAT_ADMIN_REQUIRED" in err_msg or "CreateGroupCall" in err_msg or "GROUPCALL_FORBIDDEN" in err_msg:
                    admin_notice = (
                        f"⚠️ **Voice Chat Not Active / Admin Rights Required!**\n\n"
                        f"🎵 Track: `{title}`\n\n"
                        f"👉 **How to fix in 5 seconds:**\n"
                        f"1. **Start the Voice Chat (Live Stream)** manually in your group or channel.\n"
                        f"2. Make sure the Bot (or Assistant) has **'Manage Video Chats'** (Manage Live Streams) permission.\n"
                        f"3. Type `/play` again!"
                    )
                    try: await bot_client.send_message(origin_chat, admin_notice)
                    except: pass
                elif retry_count < 1:
                    asyncio.create_task(play_next(bot_id, chat_id, user_client, bot_client, calls_client, retry_count + 1))
                else:
                    try: await bot_client.send_message(origin_chat, f"❌ **Playback Error:** `{title}`\nReason: `{err_msg}`")
                    except: pass
                    asyncio.create_task(play_next(bot_id, chat_id, user_client, bot_client, calls_client))
        finally:
            st['is_transitioning'] = False


async def handle_callback_unified(c, q, bot_id, user_client, bot_client, calls_client):
    cid, uid, data = q.message.chat.id, str(q.from_user.id), q.data
    b_tok = getattr(bot_client, "bot_token", None) or BOT_TOKEN
    
    if ":" in data:
        parts = data.split(":")
        if parts[0] in ["pause_resume", "stop", "skip", "seek_back", "seek_fwd", "replay", "speed", "effect", "back_player"]:
            data = parts[0]
            try: cid = int(parts[-1])
            except: pass
        elif parts[0] == "set_eff":
            data = f"set_eff:{parts[1]}"
            try: cid = int(parts[2])
            except: pass
        
    st = get_state(bot_id, cid)
    logging.info(f"DEBUG: Callback {data} from {uid}. Current Admins: {ADMINS}")
    
    if data == "admin_stats": await q.answer(f"Users: {len(USERS)} | Chats: {len(CHATS)}", show_alert=True)
    elif data == "close_admin": await q.message.delete()
    elif data == "help_back":
        help_text = """
📖 **Music Bot Help Menu**

**User Commands:**
• `/play [query]` - Play audio
• `/vplay [query]` - Play video
• `/autoplay [artist/genre]` - Continuous songs stream
• `/stop` - Stop streaming & autoplay
• `/skip` - Skip to next
• `/refresh` - Restart stream
• `/queue` - Check queued musics
• `/ping` - Check speed
"""
        help_markup = {"inline_keyboard": [[{"text": "Back", "callback_data": "start_back", "style": "primary"}]]}
        res = await bot_api_edit_text(b_tok, q.message.chat.id, q.message.id, help_text, help_markup)
        if not res or not res.get("ok"):
            await q.message.edit(help_text, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Back", callback_data="start_back", style="primary")]]))
    elif data == "start_back":
        me = bot_client.me
        text = f"👋 **Hello {q.from_user.mention}!**\n\nI am **{me.first_name}**, a powerful Music Player Bot.\n\n✨ **Status:** Online"
        start_markup = {
            "inline_keyboard": [
                [{"text": "Add to Group", "url": f"https://t.me/{me.username}?startgroup=true", "style": "success"}],
                [{"text": "Add to Channel", "url": f"https://t.me/{me.username}?startchannel=true", "style": "success"}],
                [{"text": "Developer", "url": DEVELOPER_URL, "style": "primary"}, {"text": "Help", "callback_data": "help_back", "style": "primary"}]
            ]
        }
        res = await bot_api_edit_text(b_tok, q.message.chat.id, q.message.id, text, start_markup)
        if not res or not res.get("ok"):
            await q.message.edit(text,
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("Add to Group", url=f"https://t.me/{me.username}?startgroup=true", style="success")],
                    [InlineKeyboardButton("Add to Channel", url=f"https://t.me/{me.username}?startchannel=true", style="success")],
                    [InlineKeyboardButton("Developer", url=DEVELOPER_URL, style="primary"), InlineKeyboardButton("Help", callback_data="help_back", style="primary")]
                ]))
    elif data == "main_admin_back":
        admin_markup = {
            "inline_keyboard": [
                [{"text": "Add Admin", "callback_data": "admin_add", "style": "success"}, {"text": "Rem Admin", "callback_data": "admin_rem", "style": "danger"}],
                [{"text": "Manage Clones", "callback_data": "clones_manage", "style": "primary"}, {"text": "Broadcast", "callback_data": "admin_bc", "style": "primary"}],
                [{"text": "Bot Stats", "callback_data": "admin_stats", "style": "primary"}, {"text": "Clear Cache", "callback_data": "admin_clear_storage", "style": "danger"}],
                [{"text": "Close Panel", "callback_data": "close_admin", "style": "danger"}]
            ]
        }
        res = await bot_api_edit_text(b_tok, q.message.chat.id, q.message.id, "🛠 **Main Admin Panel**", admin_markup)
        if not res or not res.get("ok"):
            await q.message.edit("🛠 **Main Admin Panel**", reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("Add Admin", callback_data="admin_add", style="success"), InlineKeyboardButton("Rem Admin", callback_data="admin_rem", style="danger")],
                [InlineKeyboardButton("Manage Clones", callback_data="clones_manage", style="primary"), InlineKeyboardButton("Broadcast", callback_data="admin_bc", style="primary")],
                [InlineKeyboardButton("Bot Stats", callback_data="admin_stats", style="primary"), InlineKeyboardButton("Clear Cache", callback_data="admin_clear_storage", style="danger")],
                [InlineKeyboardButton("Close Panel", callback_data="close_admin", style="danger")]
            ]))
    elif data == "admin_add":
        if uid not in ADMINS and int(uid) != SUPER_ADMIN: return await q.answer("❌ No permission (Super Admin only).", show_alert=True)
        clone_wizard[uid] = {'step': 'admin_add_id'}; await q.message.edit("Send **User ID** to add as Admin:")
    elif data == "admin_rem":
        if uid not in ADMINS and int(uid) != SUPER_ADMIN: return await q.answer("❌ No permission (Super Admin only).", show_alert=True)
        clone_wizard[uid] = {'step': 'admin_rem_id'}; await q.message.edit("Send **User ID** to remove from Admins:")
    elif data == "admin_clear_storage":
        if uid not in ADMINS: return await q.answer("No permission.")
        DOWNLOAD_CACHE.clear()
        save_json(CACHE_FILE, DOWNLOAD_CACHE)
        files = glob.glob(os.path.join(DOWNLOAD_DIR, "*"))
        count = 0
        for f in files:
            try:
                if os.path.isfile(f):
                    os.remove(f)
                    count += 1
            except: pass
        await q.answer(f"🗑 Cleared {count} files from storage.", show_alert=True)
    elif data == "clones_manage":
        btns_json = [[{"text": f"Clone: {v.get('phone','Bot')}", "callback_data": f"cl_opt_{t[:8]}", "style": "primary"}] for t, v in CLONES.items()]
        btns_json.append([{"text": "Create New Clone", "callback_data": "admin_clone", "style": "success"}])
        btns_json.append([{"text": "Back to Admin", "callback_data": "main_admin_back", "style": "primary"}])
        res = await bot_api_edit_markup(b_tok, q.message.chat.id, q.message.id, {"inline_keyboard": btns_json})
        if not res or not res.get("ok"):
            btns = [[InlineKeyboardButton(f"Clone: {v.get('phone','Bot')}", callback_data=f"cl_opt_{t[:8]}", style="primary")] for t, v in CLONES.items()]
            btns.append([InlineKeyboardButton("Create New Clone", callback_data="admin_clone", style="success")])
            btns.append([InlineKeyboardButton("Back to Admin", callback_data="main_admin_back", style="primary")])
            await q.message.edit("🤖 **Clones Manager:**", reply_markup=InlineKeyboardMarkup(btns))
    elif data == "admin_clone":
        if uid not in ADMINS: return await q.answer("❌ No permission.")
        clone_wizard[uid] = {'step': 'token'}; await q.message.edit("📟 **Send Bot Token:**")
    elif data.startswith("cl_opt_"):
        t_pre = data.split("_")[2]; token = next((t for t in CLONES if t.startswith(t_pre)), None)
        if not token: return await q.answer("❌ Not found.")
        d = CLONES[token]; status = d.get('status', 'running')
        cl_markup = {
            "inline_keyboard": [
                [{"text": "Delete Clone", "callback_data": f"cl_del_{t_pre}", "style": "danger"}, {"text": "Check Validity", "callback_data": f"cl_val_{t_pre}", "style": "primary"}],
                [{"text": "Back", "callback_data": "clones_manage", "style": "primary"}]
            ]
        }
        res = await bot_api_edit_markup(b_tok, q.message.chat.id, q.message.id, cl_markup)
        if not res or not res.get("ok"):
            await q.message.edit(f"🤖 **Clone Settings**\n\n📱 Phone: `{d.get('phone')}`\n📅 Expiry: `{d.get('expiry','?')[:10]}`\n🚦 Status: `{status.upper()}`", reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("Delete Clone", callback_data=f"cl_del_{t_pre}", style="danger"), InlineKeyboardButton("Check Validity", callback_data=f"cl_val_{t_pre}", style="primary")],
                [InlineKeyboardButton("Back", callback_data="clones_manage", style="primary")]
            ]))
    elif data.startswith("cl_del_"):
        token = next((t for t in CLONES if t.startswith(data.split("_")[2])), None)
        if token in CLONES:
            if token in active_clones:
                try:
                    await active_clones[token]['bot'].stop()
                    await active_clones[token]['user'].stop()
                    del active_clones[token]
                except: pass
            del CLONES[token]; save_json(CLONES_FILE, CLONES); await q.answer("Stopped & Deleted.", show_alert=True)
    elif data.startswith("cl_val_"):
        token = next((t for t in CLONES if t.startswith(data.split("_")[2])), None)
        await q.answer(f"Valid: {CLONES[token].get('expiry','?')[:10]}", show_alert=True)
    elif data == "bar_ignore": await q.answer("Progress Bar")
    else:
        info = st['current_data']
        # Only group admins with manage video chats permission can use buttons in groups
        if data in ["pause_resume", "stop", "skip", "seek_back", "seek_fwd", "replay", "speed", "effect", "back_player"] or data.startswith("set_eff:"):
            if q.message.chat.type in [enums.ChatType.GROUP, enums.ChatType.SUPERGROUP, enums.ChatType.CHANNEL]:
                if not await is_authorized_controller(bot_client, cid, q.from_user.id):
                    return await q.answer("❌ Only Group Admins with 'Manage Video Chats' permission can use controls!", show_alert=True)

        if not info and data in ["pause_resume", "stop", "skip", "seek_back", "seek_fwd", "replay", "speed", "effect"]: return await q.answer("No active stream.")
        if data == "stop":
            cur_song = info.get('title', 'Active Track') if info else (st['queue'][0][1] if st.get('queue') else "Active Song")
            user = q.from_user
            name = (user.first_name + (f" {user.last_name}" if user.last_name else "")) if user else "User"
            uname = f"@{user.username}" if (user and user.username) else "No username"
            uid = user.id if user else "Unknown"

            stop_song_notif = (
                "⏹️ **User Stopped a Song**\n\n"
                f"🛑 {name} ({uname}) stopped the playback.\n\n"
                f"🆔 User ID: {uid}\n"
                f"🎵 Song: {cur_song}\n\n"
                f"👤 {name} | {uname} | ID: {uid}"
            )
            async def send_stop_song_notif():
                try:
                    res_api = await bot_api_send_message(b_tok, q.message.chat.id, stop_song_notif)
                    if res_api and res_api.get("ok"):
                        msg_id = res_api["result"]["message_id"]
                        await asyncio.sleep(15)
                        await bot_api_delete_message(b_tok, q.message.chat.id, msg_id)
                except Exception: pass
            asyncio.create_task(send_stop_song_notif())

            st['is_playing'] = False
            st['queue'] = []
            st['autoplay'] = False
            st['autoplay_query'] = None
            if 'played_history' in st:
                st['played_history'].clear()
            if 'played_titles' in st:
                st['played_titles'].clear()
            old_fp = st['current_data'].get('file_path') if st.get('current_data') else None
            try:
                await calls_client.leave_call(cid)
            except: pass
            st['current_data'] = None
            if old_fp:
                asyncio.create_task(safe_delete_file(old_fp))
            if st.get('last_ui_msg'):
                old_ui_chat = st.get('last_ui_chat', cid)
                try: await bot_api_delete_message(b_tok, old_ui_chat, st['last_ui_msg'])
                except: pass
                st['last_ui_msg'] = None
                st['last_ui_chat'] = None
            try:
                await q.message.delete()
            except: pass
        elif data == "skip":
            await q.answer("⏭ Skipping to next...")
            st['skip_requested'] = True
            
            cur_song = info.get('title', 'Active Track') if info else (st['queue'][0][1] if st.get('queue') else "Active Song")
            user = q.from_user
            name = (user.first_name + (f" {user.last_name}" if user.last_name else "")) if user else "User"
            uname = f"@{user.username}" if (user and user.username) else "No username"
            uid = user.id if user else "Unknown"

            skip_notif = (
                "⏭️ **User Skipped a Song**\n\n"
                f"⏭️ {name} ({uname}) skipped the current song.\n\n"
                f"🆔 User ID: {uid}\n"
                f"🎵 Song: {cur_song}\n\n"
                f"👤 {name} | {uname} | ID: {uid}"
            )
            async def send_skip_notif():
                try:
                    res_api = await bot_api_send_message(b_tok, q.message.chat.id, skip_notif)
                    if res_api and res_api.get("ok"):
                        msg_id = res_api["result"]["message_id"]
                        await asyncio.sleep(15)
                        await bot_api_delete_message(b_tok, q.message.chat.id, msg_id)
                except Exception: pass
            asyncio.create_task(send_skip_notif())

            async def clear_skip_flag():
                await asyncio.sleep(5)
                if st.get('skip_requested'):
                    st['skip_requested'] = False
                    logging.info("DEBUG: Cleared skip_requested flag automatically")
            asyncio.create_task(clear_skip_flag())
            
            asyncio.create_task(play_next(bot_id, cid, user_client, bot_client, calls_client))
        elif data == "pause_resume":
            try:
                if not info['is_paused']:
                    await calls_client.pause(cid); info['is_paused'] = True; info['offset'] += int(time.time() - info['start_time'])
                    await q.answer("Paused")
                else:
                    await calls_client.resume(cid); info['is_paused'] = False; info['start_time'] = time.time()
                    await q.answer("Resumed")
                m_json = get_controls_json(bot_id, cid, info['offset'], info['duration'], randomize=True)
                res = await bot_api_edit_markup(b_tok, q.message.chat.id, q.message.id, m_json)
                if not res or not res.get("ok"):
                    await q.message.edit_reply_markup(reply_markup=get_controls_markup(bot_id, cid, info['offset'], info['duration']))
            except Exception as e: await q.answer(f"Error: {e}")
        elif data == "seek_back":
            try:
                el = (int(time.time() - info['start_time']) + info['offset']) if not info['is_paused'] else info['offset']
                new_offset = max(0, el - 20)
                info['offset'] = new_offset
                info['start_time'] = time.time()
                st['is_transitioning'] = True
                stream = build_stream(info['file_path'], offset=new_offset, speed=info.get('speed', '1.0x'), effects=info.get('effects', [info.get('effect', 'Normal')]), is_video=info.get('is_video', False))
                await calls_client.play(cid, stream)
                if info.get('is_paused'):
                    await calls_client.pause(cid)
                async def _c1(): await asyncio.sleep(2.5); st['is_transitioning'] = False
                asyncio.create_task(_c1())
                await q.answer(f"⏮ Rewound to {new_offset // 60}:{new_offset % 60:02d}")
                m_json = get_controls_json(bot_id, cid, new_offset, info['duration'], randomize=True)
                res = await bot_api_edit_markup(b_tok, q.message.chat.id, q.message.id, m_json)
                if not res or not res.get("ok"):
                    await q.message.edit_reply_markup(reply_markup=get_controls_markup(bot_id, cid, new_offset, info['duration']))
            except Exception as e: await q.answer(f"Error: {e}")
        elif data == "seek_fwd":
            try:
                el = (int(time.time() - info['start_time']) + info['offset']) if not info['is_paused'] else info['offset']
                new_offset = min(max(0, info['duration'] - 5), el + 20)
                info['offset'] = new_offset
                info['start_time'] = time.time()
                st['is_transitioning'] = True
                stream = build_stream(info['file_path'], offset=new_offset, speed=info.get('speed', '1.0x'), effects=info.get('effects', [info.get('effect', 'Normal')]), is_video=info.get('is_video', False))
                await calls_client.play(cid, stream)
                if info.get('is_paused'):
                    await calls_client.pause(cid)
                async def _c2(): await asyncio.sleep(2.5); st['is_transitioning'] = False
                asyncio.create_task(_c2())
                await q.answer(f"⏭ Fast-forwarded to {new_offset // 60}:{new_offset % 60:02d}")
                m_json = get_controls_json(bot_id, cid, new_offset, info['duration'], randomize=True)
                res = await bot_api_edit_markup(b_tok, q.message.chat.id, q.message.id, m_json)
                if not res or not res.get("ok"):
                    await q.message.edit_reply_markup(reply_markup=get_controls_markup(bot_id, cid, new_offset, info['duration']))
            except Exception as e: await q.answer(f"Error: {e}")
        elif data == "replay":
            try:
                info['offset'] = 0
                info['start_time'] = time.time()
                st['is_transitioning'] = True
                stream = build_stream(info['file_path'], offset=0, speed=info.get('speed', '1.0x'), effects=info.get('effects', [info.get('effect', 'Normal')]), is_video=info.get('is_video', False))
                await calls_client.play(cid, stream)
                if info.get('is_paused'):
                    info['is_paused'] = False
                async def _c3(): await asyncio.sleep(2.5); st['is_transitioning'] = False
                asyncio.create_task(_c3())
                await q.answer("🔄 Replaying from start")
                m_json = get_controls_json(bot_id, cid, 0, info['duration'], randomize=True)
                res = await bot_api_edit_markup(b_tok, q.message.chat.id, q.message.id, m_json)
                if not res or not res.get("ok"):
                    await q.message.edit_reply_markup(reply_markup=get_controls_markup(bot_id, cid, 0, info['duration']))
            except Exception as e: await q.answer(f"Error: {e}")
        elif data == "speed":
            try:
                speeds = ["1.0x", "1.25x", "1.5x", "2.0x", "0.75x"]
                cur_spd = info.get('speed', '1.0x')
                next_spd = speeds[(speeds.index(cur_spd) + 1) % len(speeds)]
                info['speed'] = next_spd
                st['active_speed'] = next_spd
                el = (int(time.time() - info['start_time']) + info['offset']) if not info['is_paused'] else info['offset']
                info['offset'] = el
                info['start_time'] = time.time()
                st['is_transitioning'] = True
                stream = build_stream(info['file_path'], offset=el, speed=next_spd, effects=info.get('effects', [info.get('effect', 'Normal')]), is_video=info.get('is_video', False))
                await calls_client.play(cid, stream)
                if info.get('is_paused'):
                    await calls_client.pause(cid)
                async def _c4(): await asyncio.sleep(2.5); st['is_transitioning'] = False
                asyncio.create_task(_c4())
                await q.answer(f"⚡ Speed: {next_spd}")
                m_json = get_controls_json(bot_id, cid, el, info['duration'], randomize=True)
                res = await bot_api_edit_markup(b_tok, q.message.chat.id, q.message.id, m_json)
                if not res or not res.get("ok"):
                    await q.message.edit_reply_markup(reply_markup=get_controls_markup(bot_id, cid, el, info['duration']))
            except Exception as e: await q.answer(f"Error: {e}")
        elif data == "effect":
            try:
                st['in_effects_menu'] = True
                cur_time = time.time()
                st['effects_menu_time'] = cur_time
                cur_effects = info.get('effects', [info.get('effect', 'Normal')]) if info else ['Normal']
                effects_json = get_effects_menu_json(cid, cur_effects)
                res = await bot_api_edit_markup(b_tok, q.message.chat.id, q.message.id, effects_json)
                if not res or not res.get("ok"):
                    await q.message.edit_reply_markup(reply_markup=get_effects_menu_markup(cid, cur_effects))
                await q.answer("🎛 Audio Effects Multi-Select (Toggle any combination):")

                async def auto_revert_effects_menu(session_t, target_cid, target_msg_id):
                    await asyncio.sleep(10)
                    cur_st = get_state(bot_id, target_cid)
                    if cur_st.get('in_effects_menu') and cur_st.get('effects_menu_time') == session_t:
                        cur_st['in_effects_menu'] = False
                        cur_info = cur_st.get('current_data')
                        if cur_info and cur_st.get('is_playing'):
                            cur_el = (int(time.time() - cur_info['start_time']) + cur_info['offset']) if not cur_info.get('is_paused') else cur_info.get('offset', 0)
                            m_json = get_controls_json(bot_id, target_cid, cur_el, cur_info.get('duration', 0), randomize=True)
                            r = await bot_api_edit_markup(b_tok, target_cid, target_msg_id, m_json)
                            if not r or not r.get("ok"):
                                try:
                                    await bot_client.edit_message_reply_markup(chat_id=target_cid, message_id=target_msg_id, reply_markup=get_controls_markup(bot_id, target_cid, cur_el, cur_info.get('duration', 0), randomize=True))
                                except: pass

                asyncio.create_task(auto_revert_effects_menu(cur_time, q.message.chat.id, q.message.id))
            except Exception as e:
                logging.error(f"DEBUG: Error opening effects menu: {e}")
                await q.answer(f"Error: {e}")
        elif data == "back_player":
            try:
                st['in_effects_menu'] = False
                st['effects_menu_time'] = 0
                el = (int(time.time() - info['start_time']) + info['offset']) if not info['is_paused'] else info['offset']
                markup_json = get_controls_json(bot_id, cid, el, info['duration'], randomize=True)
                res = await bot_api_edit_markup(b_tok, q.message.chat.id, q.message.id, markup_json)
                if not res or not res.get("ok"):
                    await q.message.edit_reply_markup(reply_markup=get_controls_markup(bot_id, cid, el, info['duration'], randomize=True))
                await q.answer("« Back to Player")
            except Exception as e:
                await q.answer(f"Error: {e}")
        elif data.startswith("set_eff:"):
            try:
                slug = data.split(":")[1]
                cur_effects = [e for e in info.get('effects', [info.get('effect', 'Normal')]) if e != "Normal"]

                if slug == "normal":
                    cur_effects = []
                    info['effects'] = []
                    info['effect'] = "Normal"
                    st['active_effects'] = []
                    st['active_effect'] = "Normal"
                    await q.answer("🔄 Reset all effects to Normal")
                else:
                    selected_name = EFFECT_SLUG_MAP.get(slug)
                    if selected_name:
                        if selected_name in cur_effects:
                            cur_effects.remove(selected_name)
                            await q.answer(f"❌ Disabled: {selected_name}")
                        else:
                            cur_effects.append(selected_name)
                            await q.answer(f"✅ Enabled: {selected_name} ({len(cur_effects)} active)")
                    
                    info['effects'] = cur_effects
                    info['effect'] = cur_effects[0] if len(cur_effects) == 1 else ("Normal" if not cur_effects else f"{len(cur_effects)} active")
                    st['active_effects'] = cur_effects
                    st['active_effect'] = info['effect']

                st['in_effects_menu'] = True
                cur_time = time.time()
                st['effects_menu_time'] = cur_time

                el = (int(time.time() - info['start_time']) + info['offset']) if not info['is_paused'] else info['offset']
                info['offset'] = el
                info['start_time'] = time.time()

                if "No Vocals" in cur_effects:
                    target_fp = await get_or_create_instrumental(info['title'], info['file_path'])
                else:
                    target_fp = info['file_path']

                st['is_transitioning'] = True
                stream = build_stream(target_fp, offset=el, speed=info.get('speed', '1.0x'), effects=cur_effects, is_video=info.get('is_video', False))
                await calls_client.play(cid, stream)
                if info.get('is_paused'):
                    await calls_client.pause(cid)

                async def _c5(): await asyncio.sleep(2.5); st['is_transitioning'] = False
                asyncio.create_task(_c5())

                effects_json = get_effects_menu_json(cid, cur_effects)
                res = await bot_api_edit_markup(b_tok, q.message.chat.id, q.message.id, effects_json)
                if not res or not res.get("ok"):
                    await q.message.edit_reply_markup(reply_markup=get_effects_menu_markup(cid, cur_effects))

                async def auto_revert_effects_menu(session_t, target_cid, target_msg_id):
                    await asyncio.sleep(10)
                    cur_st = get_state(bot_id, target_cid)
                    if cur_st.get('in_effects_menu') and cur_st.get('effects_menu_time') == session_t:
                        cur_st['in_effects_menu'] = False
                        cur_info = cur_st.get('current_data')
                        if cur_info and cur_st.get('is_playing'):
                            cur_el = (int(time.time() - cur_info['start_time']) + cur_info['offset']) if not cur_info.get('is_paused') else cur_info.get('offset', 0)
                            m_json = get_controls_json(bot_id, target_cid, cur_el, cur_info.get('duration', 0), randomize=True)
                            r = await bot_api_edit_markup(b_tok, target_cid, target_msg_id, m_json)
                            if not r or not r.get("ok"):
                                try:
                                    await bot_client.edit_message_reply_markup(chat_id=target_cid, message_id=target_msg_id, reply_markup=get_controls_markup(bot_id, target_cid, cur_el, cur_info.get('duration', 0), randomize=True))
                                except: pass

                asyncio.create_task(auto_revert_effects_menu(cur_time, q.message.chat.id, q.message.id))
            except Exception as e:
                logging.error(f"DEBUG: Error applying multi-effects: {e}")
                await q.answer(f"Error: {e}")

async def auto_delete(message, delay=60):
    await asyncio.sleep(delay)
    try: await message.delete()
    except: pass

async def delete_cmd(m):
    try: await m.delete()
    except: pass

async def check_perms(m):
    # Completely open for all users and all groups without approval
    return True

async def is_authorized_controller(bot_client, chat_id, user_id):
    if not user_id:
        return False
    if int(user_id) == SUPER_ADMIN or str(user_id) in ADMINS:
        return True
    try:
        member = await bot_client.get_chat_member(chat_id, user_id)
        if member.status == enums.ChatMemberStatus.OWNER:
            return True
        if member.status == enums.ChatMemberStatus.ADMINISTRATOR:
            if member.privileges:
                if member.privileges.can_manage_video_chats or member.privileges.can_manage_chat:
                    return True
            return True
    except Exception as e:
        logging.debug(f"is_authorized_controller check error: {e}")
    return False

def register_bot(bot_c, user_c, calls_c, clone_owner=None):
    bid = str(bot_c.me.id) if bot_c.me else "main"
    
    # Custom filter for admins (Global Super Admin + Clone Owner + Admins List)
    async def admin_check(_, __, m):
        if not m or not m.from_user: return False
        uid = m.from_user.id
        if uid == SUPER_ADMIN: return True
        if clone_owner and uid == clone_owner: return True
        return str(uid) in ADMINS

    admin_filter = filters.create(admin_check)

    @bot_c.on_message(filters.command("approve") & admin_filter)
    async def _approve(c, m):
        await delete_cmd(m)
        await m.reply("✅ **The bot is 100% public and authorized for all groups!** No approval needed.")

    @bot_c.on_message(filters.command("cleanmode") & admin_filter)
    async def _cleanmode(c, m):
        await delete_cmd(m)
        cid = str(m.chat.id)
        if cid not in APPROVED_CHATS:
            APPROVED_CHATS[cid] = {"mode": "all", "clean": False}
        curr = APPROVED_CHATS[cid].get("clean", False)
        APPROVED_CHATS[cid]["clean"] = not curr
        save_json(APPROVED_FILE, APPROVED_CHATS)
        status = "ENABLED" if not curr else "DISABLED"
        await m.reply(f"🧹 **Clean Mode {status}!**\nNow, all messages except bot and broadcasts will be deleted.")

    @bot_c.on_message(filters.command("disapprove") & admin_filter)
    async def _disapprove(c, m):
        await delete_cmd(m)
        await m.reply("ℹ️ **The bot is publicly available for all groups.**")

    @bot_c.on_message(filters.command("toggleall") & admin_filter)
    async def _toggleall(c, m):
        await delete_cmd(m)
        await m.reply("✅ **All members can freely use the bot in any group!**")

    @bot_c.on_message(filters.command(["start", "start@PrimeFearless_BeatsBot"]))
    async def _st(c, m):
        try:
            if m.chat.type != enums.ChatType.PRIVATE:
                await delete_cmd(m)
            me = c.me or await c.get_me()
            b_tok = getattr(c, "bot_token", None) or BOT_TOKEN
            user_mention = m.from_user.mention if m.from_user else "User"
            first_name = getattr(me, "first_name", "Music Bot")
            username = getattr(me, "username", "PrimeFearless_BeatsBot")
            text = f"👋 **Hello {user_mention}!**\n\nI am **{first_name}**, a powerful Music Player Bot for Telegram Voice Chats.\n\n✨ **Status:** Online\n🛠 **Maintainer:** [Owner]({DEVELOPER_URL})"
            start_markup = {
                "inline_keyboard": [
                    [{"text": "Add to Group", "url": f"https://t.me/{username}?startgroup=true", "style": "success"}],
                    [{"text": "Add to Channel", "url": f"https://t.me/{username}?startchannel=true", "style": "success"}],
                    [{"text": "Developer", "url": DEVELOPER_URL, "style": "primary"}, {"text": "Help", "callback_data": "help_back", "style": "primary"}]
                ]
            }
            res_api = await bot_api_send_message(b_tok, m.chat.id, text, start_markup)
            if not res_api or not res_api.get("ok"):
                res = await m.reply(text,
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("Add to Group", url=f"https://t.me/{username}?startgroup=true", style="success")],
                        [InlineKeyboardButton("Add to Channel", url=f"https://t.me/{username}?startchannel=true", style="success")],
                        [InlineKeyboardButton("Developer", url=DEVELOPER_URL, style="primary"), InlineKeyboardButton("Help", callback_data="help_back", style="primary")]
                    ]))
                if m.chat.type != enums.ChatType.PRIVATE:
                    asyncio.create_task(auto_delete(res, 60))
            else:
                if m.chat.type != enums.ChatType.PRIVATE:
                    msg_id = res_api["result"]["message_id"]
                    async def _auto_del_api():
                        await asyncio.sleep(60)
                        try: await c.delete_messages(m.chat.id, msg_id)
                        except: pass
                    asyncio.create_task(_auto_del_api())
        except Exception as e_st:
            logging.error(f"Error in _st handler: {e_st}")
            try: await m.reply(f"👋 **Hello!** Send `/play [song]` to stream music.")
            except: pass

    if clone_owner is None:
        @bot_c.on_message(filters.command("getsource") & filters.user(int(SUPER_ADMIN)))
        async def _gs(c, m):
            if c.me and bot.me and c.me.id != bot.me.id:
                return await send_smart_reply(m, "❌ **Access Denied:** `/getsource` can only be used on the Main Bot!")
            await delete_cmd(m)
            logging.info(f"GS: Source requested by {m.from_user.id}")
            try:
                # Send the script itself
                await m.reply_document(os.path.abspath(__file__), caption="Bot Source Code")
                c_file = find_cookies_file()
                if os.path.exists(c_file):
                    await m.reply_document(c_file, caption="YouTube Cookies")
                else:
                    await m.reply("Cookies file not found.")
            except Exception as e:
                logging.error(f"GS ERROR: {e}")
                await m.reply(f"❌ Error sending source: {e}")

        @bot_c.on_message(filters.command("setcookies") & filters.user(int(SUPER_ADMIN)))
        async def _setcookies(c, m):
            doc = m.document or (m.reply_to_message.document if m.reply_to_message else None)
            if not doc:
                return await m.reply("⚠️ Please send or reply to a valid `cookies.txt` file with `/setcookies`.")
            wait = await m.reply("🔄 **Downloading and updating YouTube cookies...**")
            try:
                for dest in [os.path.join(BASE_DIR, "cookies.txt"), os.path.join(BASE_DIR, "cookies (1).txt")]:
                    await bot_c.download_media(doc, file_name=dest)
                await wait.edit("✅ **YouTube Cookies successfully updated and active!**")
            except Exception as e:
                await wait.edit(f"❌ Failed to update cookies: {e}")
    else:
        @bot_c.on_message(filters.command(["getsource", "setcookies"]))
        async def _clone_deny_source(c, m):
            await delete_cmd(m)
            res = await send_smart_reply(m, "❌ **Access Denied:** This command is only available on the Main Bot!")
            asyncio.create_task(auto_delete(res, 10))

    @bot_c.on_message(filters.command("ping"))
    async def _ping(c, m):
        await delete_cmd(m)
        start = time.time()
        msg = await m.reply("🏓 **Pinging...**")
        latency = round((time.time() - start) * 1000, 2)

        uptime_sec = int(time.time() - BOT_START_TIME)
        d = uptime_sec // 86400
        h = (uptime_sec % 86400) // 3600
        m_up = (uptime_sec % 3600) // 60
        s = uptime_sec % 60
        uptime_str = f"{d}d {h}h {m_up}m {s}s"

        try:
            pytgcalls_ping = f"{round(calls_c.ping, 1)} ms"
        except Exception:
            pytgcalls_ping = "0.0 ms"

        def _format_bytes(b):
            for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
                if b < 1024: return f"{b:.1f} {unit}"
                b /= 1024
            return f"{b:.1f} PB"

        try:
            cpu_val = psutil.cpu_percent(interval=0.05)
            cpu_cores = psutil.cpu_count(logical=True) or 1
            cpu_str = f"{cpu_val:.1f}% ({cpu_cores} Cores)"
        except Exception:
            cpu_str = "0.0%"

        try:
            ram = psutil.virtual_memory()
            ram_str = f"{ram.percent:.1f}% ({_format_bytes(ram.used)} / {_format_bytes(ram.total)})"
        except Exception:
            ram_str = "0.0%"

        try:
            disk = psutil.disk_usage('/')
            disk_str = f"{disk.percent:.1f}% ({_format_bytes(disk.used)} / {_format_bytes(disk.total)})"
        except Exception:
            disk_str = "0.0%"

        ping_text = (
            f"🏓 **Pong!**\n\n"
            f"**Connection**\n"
            f"Latency   : `{latency} ms`\n"
            f"Uptime    : `{uptime_str}`\n"
            f"PyTgCalls : `{pytgcalls_ping}`\n\n"
            f"**System**\n"
            f"CPU   : `{cpu_str}`\n"
            f"RAM   : `{ram_str}`\n"
            f"Disk  : `{disk_str}`"
        )
        await msg.edit(ping_text)

    @bot_c.on_message(filters.command("refresh"))
    async def _refresh(c, m):
        if not await check_perms(m): return
        await delete_cmd(m)
        if m.chat.type in [enums.ChatType.GROUP, enums.ChatType.SUPERGROUP, enums.ChatType.CHANNEL]:
            if not await is_authorized_controller(bot_c, m.chat.id, m.from_user.id):
                res = await m.reply("❌ **Only Group Admins with 'Manage Video Chats' permission can use /refresh!**")
                asyncio.create_task(auto_delete(res, 10))
                return
        st = get_state(bid, m.chat.id)
        wait = await m.reply("🔄 **Refreshing Voice Chat...**")
        try:
            await asyncio.wait_for(calls_c.leave_call(m.chat.id), timeout=10)
        except: pass
        
        if st['current_data']:
            # Force restart the current song
            st['refresh_requested'] = True
            await wait.edit("✅ **Call reset! Restarting current stream...**")
            asyncio.create_task(play_next(bid, m.chat.id, user_c, bot_c, calls_c, retry_count=1))
        else:
            await wait.edit("✅ **Voice Chat Refreshed!** (No active queue to restart)")
        asyncio.create_task(auto_delete(wait, 10))

    @bot_c.on_message(filters.command("help"))
    async def _hlp(c, m):
        await delete_cmd(m)
        help_text = """
📖 **Music Bot Help Menu**

**User Commands:**
• `/play [query]` - Play audio in voice chat
• `/vplay [query]` - Play video in voice chat
• `/autoplay [artist/genre]` - Continuous non-stop songs stream
• `/stop` - Stop streaming & autoplay
• `/skip` - Skip to next song
• `/refresh` - Restart current stream if stuck
• `/queue` - Check current and queued songs
• `/settarget [chat_id]` - Set target channel for DM controls
• `/ping` - Check bot response speed
• `/start` - Start the bot
• `/help` - Show this help message

**Super Admin Commands:**
• `/cleanmode` - Toggle Auto-Delete (Clean Chat)
• `/addchannel [id]` - Add a remote channel to CHATS
• `/removechannel [id]` - Remove a channel from CHATS
• `/admin` - Open Admin Panel
• `/broadcast` - Broadcast message to all
• `/getsource` - Receive source code and cookies
"""
        await m.reply(help_text)

    @bot_c.on_message(filters.command(["queue", "q", "queued"]))
    async def _queue(c, m):
        await delete_cmd(m)
        target_id = m.chat.id
        if m.chat.type == enums.ChatType.PRIVATE:
            target_id = ACTIVE_TARGET.get(str(m.from_user.id), m.chat.id)
        
        st = get_state(bid, target_id)
        cur = st.get('current_data')
        queue_list = st.get('queue', [])
        
        if not cur and not queue_list:
            res = await m.reply("📭 **The music queue is currently empty!**\nUse `/play [song name]` to start streaming.")
            return asyncio.create_task(auto_delete(res, 15))
            
        text = "📋 **Current Music Queue:**\n\n"
        if cur:
            dur_str = f"{cur['duration'] // 60}:{cur['duration'] % 60:02d}" if cur.get('duration') else "Live"
            req_by = f" | Requested by: {cur.get('requester', 'User')}" if cur.get('requester') else ""
            type_str = "🎬 Video" if cur.get('is_video') else "🎵 Audio"
            text += f"▶️ **Now Playing ({type_str}):**\n• **{cur.get('title', 'Unknown')}** (`{dur_str}`){req_by}\n\n"
            
        if queue_list:
            text += f"📑 **Upcoming Tracks ({len(queue_list)}):**\n"
            for i, task in enumerate(queue_list[:15], 1):
                # task = (fp, title, dur, thumb, is_v, origin_chat, requester, query_msg_id)
                q_title = task[1] if len(task) > 1 else "Unknown"
                q_dur = task[2] if len(task) > 2 else 0
                q_v = task[4] if len(task) > 4 else False
                q_req = f" ({task[6]})" if len(task) > 6 and task[6] else ""
                dur_fmt = f"{q_dur // 60}:{q_dur % 60:02d}" if q_dur else "Live"
                type_icon = "🎬" if q_v else "🎵"
                text += f"`{i}.` {type_icon} **{q_title}** (`{dur_fmt}`){q_req}\n"
            if len(queue_list) > 15:
                text += f"\n*...and {len(queue_list) - 15} more in queue.*"
        else:
            text += "📑 **Upcoming Tracks:** None"
            
        res = await m.reply(text)
        asyncio.create_task(auto_delete(res, 60))
    @bot_c.on_message(filters.command("check"))
    async def _chk(c, m):
        if not await check_perms(m): return
        await delete_cmd(m)
        st = get_state(bid, m.chat.id)
        is_in = "No"
        perms = "Unknown"
        try:
            member = await user_c.get_chat_member(m.chat.id, user_c.me.id)
            is_in = "Yes"
            if member.privileges:
                perms = "Admin" if member.privileges.can_manage_video_chats else "Admin (No VC perms)"
            else:
                perms = "Member"
        except Exception as e: is_in = f"Error ({e})"
        cur = st['current_data']
        await m.reply(f"**Bot Diagnostics:**\n- Assistant: {user_c.me.id} (DC{user_c.dc_id})\n- Assistant in Chat: {is_in}\n- Permissions: {perms}\n- Is Playing: {st['is_playing']}\n- Queue Size: {len(st['queue'])}\n- Current: {cur['title'] if cur else 'None'}\n- Type: {'Video' if cur and cur.get('is_video') else 'Audio'}")
    @bot_c.on_message(filters.command("settarget"))
    async def _starg(c, m):
        await delete_cmd(m)
        if len(m.command) < 2: return await m.reply("Usage: `/settarget [chat_id]`\nExample: `/settarget -100123456789`")
        try:
            cid = int(m.command[1])
            ACTIVE_TARGET[m.from_user.id] = cid
            await m.reply(f"🎯 **Target Set!**\nNow, when you use `/play` in this DM, it will stream to `{cid}`.")
        except ValueError:
            await m.reply("❌ Invalid Chat ID. It must be a number.")

    @bot_c.on_message(filters.command(["play", "vplay"]))
    async def _p(c, m):
        if not await check_perms(m): return
        # Delete user's query message immediately
        await delete_cmd(m)
        is_v = m.command[0] == "vplay"; query = " ".join(m.command[1:])
        b_tok = getattr(bot_c, "bot_token", None) or BOT_TOKEN
        if not query and not m.reply_to_message:
            return await send_smart_reply(m, "Usage: `/play [query]`")
        wait_res = await bot_api_send_message(b_tok, m.chat.id, "⏳ **Processing...**")
        wait_mid = wait_res.get("result", {}).get("message_id") if (wait_res and wait_res.get("ok")) else None
        
        u_name = (m.from_user.first_name + (f" {m.from_user.last_name}" if m.from_user.last_name else "")) if m.from_user else "User"
        requester = f"[{u_name}](tg://openmessage?user_id={m.from_user.id})" if m.from_user else "Unknown"
        
        # Determine target chats
        targets = []
        if m.chat.type in [enums.ChatType.GROUP, enums.ChatType.SUPERGROUP, enums.ChatType.CHANNEL]:
            targets = [m.chat.id]
        else:
            target = ACTIVE_TARGET.get(m.from_user.id)
            if not target:
                err_t = "❌ **No target set!**\nPlease use `/settarget [chat_id]` first to tell the bot which channel to stream in."
                if wait_mid:
                    return await bot_api_edit_message(b_tok, m.chat.id, wait_mid, err_t)
                return await send_smart_reply(m, err_t)
            targets = [target]
        
        if m.reply_to_message and (m.reply_to_message.audio or m.reply_to_message.video):
            try:
                fp = await bot_c.download_media(m.reply_to_message); title = "Telegram File"; dur = 180; thumb = None
                if m.reply_to_message.audio: title = m.reply_to_message.audio.title or "Audio"; dur = m.reply_to_message.audio.duration
                elif m.reply_to_message.video: title = "Video"; dur = m.reply_to_message.video.duration; thumb = m.reply_to_message.video.thumbs[0].file_id if m.reply_to_message.video.thumbs else None
            except Exception as e:
                err_t = f"❌ Download Error: {e}"
                if wait_mid: return await bot_api_edit_message(b_tok, m.chat.id, wait_mid, err_t)
                return await send_smart_reply(m, err_t)
        else:
            fp, title, dur, thumb = await search_and_download(query, is_v)
            
        if not fp:
            err_t = "❌ Failed to find or download media."
            if wait_mid: return await bot_api_edit_message(b_tok, m.chat.id, wait_mid, err_t)
            return await send_smart_reply(m, err_t)
        
        success_count = 0
        last_error = ""
        queued = False
        for target_id in targets:
            try:
                await ensure_user_in_chat(target_id, user_c, bot_c)
                st = get_state(bid, target_id)
                # Store task with requester info and query message ID
                st['queue'].append((fp, title, dur, thumb, is_v, m.chat.id, requester, m.id))
                if not st['is_playing']: 
                    st['is_playing'] = True
                    await play_next(bid, target_id, user_c, bot_c, calls_c)
                else:
                    queued = True
                success_count += 1
            except Exception as e:
                last_error = str(e)
                logging.error(f"Error starting playback in {target_id}: {last_error}")
        
        if success_count > 0:
            if m.chat.type == enums.ChatType.PRIVATE:
                action_text = "Added to queue" if queued else "Started playback"
                q_text = f"✅ **{action_text} in {success_count} authorized channel(s).**\n🎵 `{title}`"
                if wait_mid: await bot_api_edit_message(b_tok, m.chat.id, wait_mid, q_text)
                else: await send_smart_reply(m, q_text)
            else:
                if queued:
                    q_text = f"✅ **Added to queue:**\n🎵 `{title}`"
                    if wait_mid:
                        await bot_api_edit_message(b_tok, m.chat.id, wait_mid, q_text)
                        async def _del_q(mid):
                            await asyncio.sleep(30)
                            await bot_api_delete_message(b_tok, m.chat.id, mid)
                        asyncio.create_task(_del_q(wait_mid))
                    else:
                        r = await send_smart_reply(m, q_text)
                else:
                    if wait_mid:
                        await bot_api_delete_message(b_tok, m.chat.id, wait_mid)
        else:
            err_t = f"❌ **Assistant Error:** {last_error}"
            if wait_mid: await bot_api_edit_message(b_tok, m.chat.id, wait_mid, err_t)
            else: await send_smart_reply(m, err_t)
    @bot_c.on_message(filters.command(["autoplay", "ap", "radio"]))
    async def _autoplay_cmd(c, m):
        if not await check_perms(m): return
        await delete_cmd(m)
        if m.chat.type in [enums.ChatType.GROUP, enums.ChatType.SUPERGROUP, enums.ChatType.CHANNEL]:
            if not await is_authorized_controller(bot_c, m.chat.id, m.from_user.id):
                res = await send_smart_reply(m, "❌ **Only Group Admins with 'Manage Video Chats' permission can configure /autoplay!**")
                asyncio.create_task(auto_delete(res, 10))
                return

        st = get_state(bid, m.chat.id)
        query = " ".join(m.command[1:]).strip() if len(m.command) > 1 else ""
        b_tok = getattr(bot_c, "bot_token", None) or BOT_TOKEN
        
        # Case 1: Disable autoplay
        if query.lower() in ["off", "stop", "disable", "no", "false", "0"]:
            st['autoplay'] = False
            st['autoplay_query'] = None
            if 'played_history' in st:
                st['played_history'].clear()
            return await send_smart_reply(m, "⏹️ **Autoplay Mode Disabled!**\n\nAutomatic continuous playback has been turned off.")

        # Case 2: No query provided -> Check status or show usage
        if not query:
            if st.get('autoplay') and st.get('autoplay_query'):
                return await send_smart_reply(m,
                    f"📻 **Autoplay is currently ACTIVE!**\n\n"
                    f"🎙️ **Artist / Genre:** `{st['autoplay_query']}`\n"
                    f"🎵 *The bot will automatically queue and stream non-stop songs by this artist/genre until you use `/stop`.*"
                )
            
            cur = st.get('current_data')
            if cur and cur.get('title'):
                query = cur.get('title')
            else:
                return await send_smart_reply(m,
                    "📻 **Autoplay / Continuous Radio Mode**\n\n"
                    "**Usage:** `/autoplay [artist name or genre]`\n\n"
                    "**Examples:**\n"
                    "• `/autoplay Arijit Singh`\n"
                    "• `/autoplay Sidhu Moosewala`\n"
                    "• `/autoplay Punjabi Hits`\n"
                    "• `/autoplay Lo-Fi Chill`\n"
                    "• `/autoplay Romantic Hindi`\n"
                    "• `/autoplay off` *(to disable)*\n\n"
                    "ℹ️ *The bot will automatically queue and stream non-stop songs by your chosen artist or genre until you use `/stop`.*"
                )

        # Case 3: Set and activate autoplay with query
        st['autoplay'] = True
        st['autoplay_query'] = query
        if 'played_history' not in st:
            st['played_history'] = set()

        user_name = (m.from_user.first_name + (f" {m.from_user.last_name}" if m.from_user.last_name else "")) if m.from_user else "User"
        requester_str = f"[{user_name}](tg://openmessage?user_id={m.from_user.id})" if m.from_user else "Unknown"

        if st.get('is_playing'):
            return await send_smart_reply(m,
                f"📻 **Autoplay Activated Successfully!**\n\n"
                f"🎙️ **Artist / Genre:** `{query}`\n"
                f"👤 **Activated by:** {requester_str}\n\n"
                f"🎵 *Continuous stream is active. When the current track ends, matching songs will play automatically until you use `/stop`.*"
            )

        # If nothing is playing, find first track and start immediately!
        wait_res = await bot_api_send_message(b_tok, m.chat.id, f"⏳ **Finding and starting autoplay for '{query}'...**")
        wait_mid = wait_res.get("result", {}).get("message_id") if (wait_res and wait_res.get("ok")) else None
        try:
            await ensure_user_in_chat(m.chat.id, user_c, bot_c)
            next_task = await get_autoplay_next_track(bid, m.chat.id, query, is_video=False)
            if not next_task:
                err_t = f"❌ **Could not find songs for:** `{query}`. Please try another artist or genre name."
                if wait_mid: return await bot_api_edit_message(b_tok, m.chat.id, wait_mid, err_t)
                return await send_smart_reply(m, err_t)
            
            fp, title, dur, thumb, is_v = next_task
            st['queue'].append((fp, title, dur, thumb, is_v, m.chat.id, f"Autoplay ({query})", None))
            st['is_playing'] = True
            if wait_mid:
                await bot_api_delete_message(b_tok, m.chat.id, wait_mid)
            await play_next(bid, m.chat.id, user_c, bot_c, calls_c)
        except Exception as e:
            logging.error(f"Error starting autoplay: {e}")
            err_t = f"❌ **Error starting autoplay:** {e}"
            if wait_mid: await bot_api_edit_message(b_tok, m.chat.id, wait_mid, err_t)
            else: await send_smart_reply(m, err_t)

    @bot_c.on_message(filters.command("stop"))
    async def _s(c, m):
        if not await check_perms(m): return
        await delete_cmd(m)
        if m.chat.type in [enums.ChatType.GROUP, enums.ChatType.SUPERGROUP, enums.ChatType.CHANNEL]:
            if not await is_authorized_controller(bot_c, m.chat.id, m.from_user.id):
                res = await m.reply("❌ **Only Group Admins with 'Manage Video Chats' permission can use /stop!**")
                asyncio.create_task(auto_delete(res, 10))
                return
        st = get_state(bid, m.chat.id)
        logging.info(f"DEBUG: Stop command received for {m.chat.id}")
        st['is_playing'] = False
        st['queue'] = []
        st['autoplay'] = False
        st['autoplay_query'] = None
        if 'played_history' in st:
            st['played_history'].clear()
        if 'played_titles' in st:
            st['played_titles'].clear()
        old_fp = st['current_data'].get('file_path') if st.get('current_data') else None
        try:
            await asyncio.wait_for(calls_c.leave_call(m.chat.id), timeout=10)
        except Exception as e:
            logging.error(f"DEBUG: Error in leave_call during stop: {e}")
        st['current_data'] = None
        if old_fp:
            asyncio.create_task(safe_delete_file(old_fp))

        # Delete active "Now Streaming" message immediately
        if st.get('last_ui_msg'):
            target_chat = st.get('last_ui_chat', m.chat.id)
            try: await bot_c.delete_messages(target_chat, st['last_ui_msg'])
            except: pass
            st['last_ui_msg'] = None
            st['last_ui_chat'] = None

        cur_song = st['current_data'].get('title', 'Unknown') if st.get('current_data') else (st['queue'][0][1] if st.get('queue') else "Active Song")
        user = m.from_user
        name = (user.first_name + (f" {user.last_name}" if user.last_name else "")) if user else "User"
        uname = f"@{user.username}" if (user and user.username) else "No username"
        uid = user.id if user else "Unknown"

        stop_song_msg = (
            "⏹️ **User Stopped a Song**\n\n"
            f"🛑 {name} ({uname}) stopped the playback.\n\n"
            f"🆔 User ID: {uid}\n"
            f"🎵 Song: {cur_song}\n\n"
            f"👤 {name} | {uname} | ID: {uid}"
        )
        rep = await send_smart_reply(m, stop_song_msg)
        if hasattr(rep, 'delete'):
            asyncio.create_task(auto_delete(rep, 15))
        elif isinstance(rep, dict) and rep.get("result", {}).get("message_id"):
            mid = rep["result"]["message_id"]
            tok = getattr(getattr(m, "_client", None), "bot_token", None) or BOT_TOKEN
            async def _d_stop(msgid):
                await asyncio.sleep(15)
                await bot_api_delete_message(tok, m.chat.id, msgid)
            asyncio.create_task(_d_stop(mid))

    @bot_c.on_message(filters.command("skip"))
    async def _skip_cmd(c, m):
        if not await check_perms(m): return
        await delete_cmd(m)
        if m.chat.type in [enums.ChatType.GROUP, enums.ChatType.SUPERGROUP, enums.ChatType.CHANNEL]:
            if not await is_authorized_controller(bot_c, m.chat.id, m.from_user.id):
                res = await m.reply("❌ **Only Group Admins with 'Manage Video Chats' permission can use /skip!**")
                asyncio.create_task(auto_delete(res, 10))
                return
        st = get_state(bid, m.chat.id)
        logging.info(f"DEBUG: Skip command received for {m.chat.id}")
        if not st['is_playing'] and not st['queue']:
            return await m.reply("❌ **No active stream to skip.**")
        
        st['skip_requested'] = True
        async def clear_skip_flag():
            await asyncio.sleep(5)
            if st.get('skip_requested'):
                st['skip_requested'] = False
                logging.info("DEBUG: Cleared skip_requested flag automatically")
        asyncio.create_task(clear_skip_flag())
        
        cur_song = st['current_data'].get('title', 'Unknown') if st.get('current_data') else (st['queue'][0][1] if st.get('queue') else "Active Song")
        user = m.from_user
        name = (user.first_name + (f" {user.last_name}" if user.last_name else "")) if user else "User"
        uname = f"@{user.username}" if (user and user.username) else "No username"
        uid = user.id if user else "Unknown"

        skip_msg = (
            "⏭️ **User Skipped a Song**\n\n"
            f"⏭️ {name} ({uname}) skipped the current song.\n\n"
            f"🆔 User ID: {uid}\n"
            f"🎵 Song: {cur_song}\n\n"
            f"👤 {name} | {uname} | ID: {uid}"
        )
        rep = await send_smart_reply(m, skip_msg)
        if hasattr(rep, 'delete'):
            asyncio.create_task(auto_delete(rep, 15))
        elif isinstance(rep, dict) and rep.get("result", {}).get("message_id"):
            mid = rep["result"]["message_id"]
            tok = getattr(getattr(m, "_client", None), "bot_token", None) or BOT_TOKEN
            async def _d_skip(msgid):
                await asyncio.sleep(15)
                await bot_api_delete_message(tok, m.chat.id, msgid)
            asyncio.create_task(_d_skip(mid))
        asyncio.create_task(play_next(bid, m.chat.id, user_c, bot_c, calls_c))
    @bot_c.on_callback_query()
    async def _cb(c, q): await handle_callback_unified(c, q, bid, user_c, bot_c, calls_c)
    async def cleanup_vc_session(cid, reason="Voice Chat Ended"):
        st = get_state(bid, cid)
        logging.info(f"DEBUG: {reason} for {cid}. Resetting state, stopping playback, and clearing queue...")
        st['is_playing'] = False
        st['queue'] = []
        st['autoplay'] = False
        st['autoplay_query'] = None
        if 'played_history' in st:
            st['played_history'].clear()
        if 'played_titles' in st:
            st['played_titles'].clear()
        st['is_transitioning'] = False
        st['skip_requested'] = False
        st['reconnect_count'] = 0
        old_fp = st['current_data'].get('file_path') if st.get('current_data') else None
        st['current_data'] = None
        if old_fp:
            asyncio.create_task(safe_delete_file(old_fp))
        try:
            await calls_c.leave_call(cid)
        except Exception:
            pass
        if st.get('last_ui_msg'):
            target_chat = st.get('last_ui_chat', cid)
            try: await bot_c.delete_messages(target_chat, st['last_ui_msg'])
            except: pass
            st['last_ui_msg'] = None
            st['last_ui_chat'] = None

        if 'pending_vc_invites' in st and st['pending_vc_invites']:
            for inv_uid, (inv_mid, inv_tok) in list(st['pending_vc_invites'].items()):
                try:
                    asyncio.create_task(bot_api_delete_message(inv_tok, cid, inv_mid))
                except Exception:
                    pass
            st['pending_vc_invites'].clear()

    @calls_c.on_update()
    async def _up(c, u):
        if isinstance(u, ChatUpdate):
            logging.info(f"DEBUG: PyTgCalls ChatUpdate for {u.chat_id}: status={u.status}")
            if u.status in [ChatUpdate.Status.CLOSED_VOICE_CHAT, ChatUpdate.Status.KICKED, ChatUpdate.Status.LEFT_GROUP, ChatUpdate.Status.DISCARDED_CALL]:
                await cleanup_vc_session(u.chat_id, reason=f"Voice Chat Ended ({u.status})")
                return
        elif isinstance(u, UpdatedGroupCallParticipant):
            try:
                p_uid = u.participant.user_id
                if not p_uid: return
                bot_uid = bot_c.me.id if bot_c.me else None
                user_uid = user_c.me.id if user_c.me else None
                if p_uid in [bot_uid, user_uid]: return

                name, uname = await resolve_user_profile(p_uid, chat_id=u.chat_id, bot_client=bot_c, user_client=user_c)
                st = get_state(bid, u.chat_id)
                st['last_active_user_info'] = {"name": name, "username": uname, "id": p_uid}
                b_tok = getattr(bot_c, "bot_token", None) or BOT_TOKEN

                if u.action == GroupCallParticipant.Action.JOINED:
                    if should_send_event(f"join:{u.chat_id}:{p_uid}", 15):
                        join_msg = (
                            "🎤 **User Joined VC**\n\n"
                            f"👋 {name} ({uname}) joined the voice chat.\n\n"
                            f"🆔 User ID: {p_uid}\n\n"
                            f"👤 {name} | {uname} | ID: {p_uid}"
                        )
                        res = await bot_api_send_message(b_tok, u.chat_id, join_msg)
                        if res and res.get("ok"):
                            msg_id = res["result"]["message_id"]
                            async def _del_j(m_id):
                                await asyncio.sleep(20)
                                await bot_api_delete_message(b_tok, u.chat_id, m_id)
                            asyncio.create_task(_del_j(msg_id))
                elif u.action in [GroupCallParticipant.Action.LEFT, GroupCallParticipant.Action.KICKED]:
                    if should_send_event(f"leave:{u.chat_id}:{p_uid}", 15):
                        leave_msg = (
                            "🚪 **User Left VC**\n\n"
                            f"👋 {name} ({uname}) left the voice chat.\n\n"
                            f"🆔 User ID: {p_uid}\n\n"
                            f"👤 {name} | {uname} | ID: {p_uid}"
                        )
                        res = await bot_api_send_message(b_tok, u.chat_id, leave_msg)
                        if res and res.get("ok"):
                            msg_id = res["result"]["message_id"]
                            async def _del_l(m_id):
                                await asyncio.sleep(20)
                                await bot_api_delete_message(b_tok, u.chat_id, m_id)
                            asyncio.create_task(_del_l(msg_id))
            except Exception as e_part:
                logging.debug(f"DEBUG: Participant event error: {e_part}")
        elif isinstance(u, StreamEnded):
            logging.info(f"DEBUG: StreamEnded event received for {u.chat_id}")
            st = get_state(bid, u.chat_id)
            if st.get('skip_requested') or st.get('is_transitioning'):
                logging.info(f"DEBUG: Ignored StreamEnded because skip or stream transition is in progress")
                return
            
            # Auto-recovery for network drops (track ended prematurely before reaching the end)
            info = st.get('current_data')
            if info and st.get('is_playing') and not info.get('is_paused') and not st.get('is_transitioning'):
                el = int(time.time() - info['start_time']) + info.get('offset', 0)
                dur = info.get('duration', 0)
                # If more than 5s left on track, it's a network glitch! Auto-resume without skipping!
                if dur > 10 and el < (dur - 5):
                    reconn_count = st.get('reconnect_count', 0)
                    if reconn_count < 5:
                        st['reconnect_count'] = reconn_count + 1
                        logging.warning(f"DEBUG: Network packet drop at {el}s / {dur}s for {u.chat_id}. Auto-resuming stream (attempt {st['reconnect_count']})...")
                        try:
                            info['offset'] = el
                            info['start_time'] = time.time()
                            effects = info.get('effects', [info.get('effect', 'Normal')])
                            target_fp = await get_or_create_instrumental(info['title'], info['file_path']) if "No Vocals" in effects else info['file_path']
                            stream = build_stream(target_fp, offset=el, speed=info.get('speed', '1.0x'), effects=effects, is_video=info.get('is_video', False))
                            await asyncio.sleep(0.5)
                            await calls_c.play(u.chat_id, stream)
                            logging.info(f"DEBUG: Successfully auto-resumed stream at {el}s!")
                            return
                        except Exception as e_res:
                            logging.error(f"DEBUG: Auto-resume failed: {e_res}")

            # Natural song completion: reset reconnect counter and play next in queue
            st['reconnect_count'] = 0
            await play_next(bid, u.chat_id, user_c, bot_c, calls_c)

    @bot_c.on_message(filters.video_chat_ended)
    async def _vc_ended_msg(c, m):
        st = get_state(bid, m.chat.id)
        await cleanup_vc_session(m.chat.id, reason="Video Chat Ended Service Message")
        if not should_send_event(f"vc_stop:{m.chat.id}", 10):
            return
        try:
            dur = m.video_chat_ended.duration if hasattr(m, 'video_chat_ended') and m.video_chat_ended else 0
            dur_str = f"{dur // 60}:{dur % 60:02d}" if dur else "0:00"
            
            if st.get('last_active_user_info'):
                info = st['last_active_user_info']
                name = info.get("name", "Admin")
                uname = info.get("username", "No username")
                uid = info.get("id", SUPER_ADMIN)
            elif m.from_user and not m.from_user.is_bot:
                name, uname = await resolve_user_profile(m.from_user.id, chat_id=m.chat.id, bot_client=bot_c, user_client=user_c)
                uid = m.from_user.id
            else:
                user = st.get('last_active_user') or st.get('vc_starter')
                if not user:
                    try:
                        admins = await bot_c.get_chat_administrators(m.chat.id)
                        owner = next((adm.user for adm in admins if adm.status == enums.ChatMemberStatus.OWNER and not adm.user.is_bot), None)
                        user = owner or next((adm.user for adm in admins if not adm.user.is_bot), None)
                    except Exception:
                        pass
                if user:
                    name, uname = await resolve_user_profile(user.id, chat_id=m.chat.id, bot_client=bot_c, user_client=user_c)
                    uid = user.id
                else:
                    name, uname = await resolve_user_profile(SUPER_ADMIN, chat_id=m.chat.id, bot_client=bot_c, user_client=user_c)
                    uid = SUPER_ADMIN

            stop_msg = (
                "⏹️ **User Stopped VC**\n\n"
                f"🛑 {name} ({uname}) stopped the voice chat.\n\n"
                f"🆔 User ID: {uid}\n"
                f"⏱️ Duration: {dur_str}\n\n"
                f"👤 {name} | {uname} | ID: {uid}"
            )
            res = await send_smart_reply(m, stop_msg)
            if hasattr(res, 'delete'):
                asyncio.create_task(auto_delete(res, 25))
            elif isinstance(res, dict) and res.get("result", {}).get("message_id"):
                mid = res["result"]["message_id"]
                tok = getattr(getattr(m, "_client", None), "bot_token", None) or BOT_TOKEN
                async def _d_vc_end(msgid):
                    await asyncio.sleep(25)
                    await bot_api_delete_message(tok, m.chat.id, msgid)
                asyncio.create_task(_d_vc_end(mid))
        except Exception as e_end_vc:
            logging.error(f"Error in _vc_ended_msg: {e_end_vc}")

    @bot_c.on_message(filters.video_chat_started)
    async def _vc_started_msg(c, m):
        st = get_state(bid, m.chat.id)
        st['is_playing'] = False
        st['queue'] = []
        st['current_data'] = None
        logging.info(f"DEBUG: Video Chat Started Service Message in {m.chat.id}. Queue and player state are fresh.")
        if not should_send_event(f"vc_start:{m.chat.id}", 10):
            return
        try:
            user = m.from_user
            if not user or user.is_bot:
                try:
                    admins = await bot_c.get_chat_administrators(m.chat.id)
                    owner = next((adm.user for adm in admins if adm.status == enums.ChatMemberStatus.OWNER and not adm.user.is_bot), None)
                    user = owner or next((adm.user for adm in admins if not adm.user.is_bot), None)
                except Exception:
                    pass

            if user:
                st['vc_starter'] = user
                st['last_active_user'] = user
                name, uname = await resolve_user_profile(user.id, chat_id=m.chat.id, bot_client=bot_c, user_client=user_c)
                uid = user.id
            else:
                name, uname = await resolve_user_profile(SUPER_ADMIN, chat_id=m.chat.id, bot_client=bot_c, user_client=user_c)
                uid = SUPER_ADMIN

            start_msg = (
                "▶️ **User Started VC**\n\n"
                f"🎙️ {name} ({uname}) started the voice chat.\n\n"
                f"🆔 User ID: {uid}\n\n"
                f"👤 {name} | {uname} | ID: {uid}"
            )
            res = await send_smart_reply(m, start_msg)
            if hasattr(res, 'delete'):
                asyncio.create_task(auto_delete(res, 25))
            elif isinstance(res, dict) and res.get("result", {}).get("message_id"):
                mid = res["result"]["message_id"]
                tok = getattr(getattr(m, "_client", None), "bot_token", None) or BOT_TOKEN
                async def _d_vc_start(msgid):
                    await asyncio.sleep(25)
                    await bot_api_delete_message(tok, m.chat.id, msgid)
                asyncio.create_task(_d_vc_start(mid))
        except Exception as e_st_vc:
            logging.error(f"Error in _vc_started_msg: {e_st_vc}")

    @bot_c.on_message(filters.video_chat_members_invited)
    async def _vc_members_invited_msg(c, m):
        if not hasattr(m, 'video_chat_members_invited') or not m.video_chat_members_invited:
            return
        try:
            inviter = m.from_user
            if inviter:
                inviter_name, inviter_uname = await resolve_user_profile(inviter.id, chat_id=m.chat.id, bot_client=bot_c, user_client=user_c)
                inviter_id = str(inviter.id)
            else:
                inviter_name, inviter_uname, inviter_id = "Admin", "@admin", "Unknown"

            invited_list = getattr(m.video_chat_members_invited, "users", []) or []
            if not invited_list:
                return

            for invited in invited_list:
                invited_name, invited_uname = await resolve_user_profile(invited.id, chat_id=m.chat.id, bot_client=bot_c, user_client=user_c)
                invited_id = str(invited.id)

                invite_msg = (
                    "📨 **Voice Chat Invitation**\n\n"
                    f"👤 {inviter_name} ({inviter_uname}) invited {invited_name} ({invited_uname}) to join the voice chat.\n\n"
                    f"🆔 Inviter ID: \"{inviter_id}\"\n"
                    f"🆔 Invited User ID: \"{invited_id}\""
                )

                res = await send_smart_reply(m, invite_msg)
                mid = res.id if hasattr(res, 'id') else (res.get("result", {}).get("message_id") if isinstance(res, dict) else None)
                if mid:
                    tok = getattr(getattr(m, "_client", None), "bot_token", None) or BOT_TOKEN
                    st = get_state(bid, m.chat.id)
                    if 'pending_vc_invites' not in st:
                        st['pending_vc_invites'] = {}
                    st['pending_vc_invites'][invited.id] = (mid, tok)
        except Exception as e_inv:
            logging.error(f"Error in _vc_members_invited_msg: {e_inv}")

    @bot_c.on_message(filters.left_chat_member)
    async def _member_left_msg(c, m):
        try:
            bot_uid = bot_c.me.id if bot_c.me else None
            user_uid = user_c.me.id if user_c.me else None
            if m.left_chat_member and m.left_chat_member.id in [bot_uid, user_uid]:
                await cleanup_vc_session(m.chat.id, reason="Assistant/Bot Left Group")
        except Exception:
            pass
    
    @bot_c.on_message(filters.command("addchannel") & admin_filter)
    async def add_ch(c, m):
        if len(m.command) < 2: return await m.reply("Usage: `/addchannel [chat_id]`")
        cid = m.command[1]
        CHATS.add(cid); save_json(CHATS_FILE, CHATS)
        await m.reply(f"✅ Added `{cid}` to authorized chats.")

    @bot_c.on_message(filters.command("removechannel") & admin_filter)
    async def rem_ch(c, m):
        if len(m.command) < 2: return await m.reply("Usage: `/removechannel [chat_id]`")
        cid = m.command[1]
        if cid in CHATS: CHATS.remove(cid); save_json(CHATS_FILE, CHATS)
        await m.reply(f"✅ Removed `{cid}` from authorized chats.")

    @bot_c.on_message(filters.command(["broadcast", "boardcast", "bc", "gcast"]) & admin_filter)
    async def main_bc(c, m):
        await delete_cmd(m)
        b_tok = getattr(bot_c, "bot_token", None) or BOT_TOKEN
        text_arg = " ".join(m.command[1:]).strip() if len(m.command) > 1 else None
        if not m.reply_to_message and not text_arg:
            return await send_smart_reply(m, "❌ **Usage:** Reply to any message, photo, video, or sticker with `/broadcast` (or `/boardcast`) to forward it to all users and groups!")
        
        status_res = await bot_api_send_message(b_tok, m.chat.id, "📢 **Broadcasting message to all users and groups...**")
        status_mid = status_res.get("result", {}).get("message_id") if (status_res and status_res.get("ok")) else None
        
        # Targets: Users (DMs) + Groups only (no channels)
        raw_targets = set(USERS).union(set(CHATS)).union(set(APPROVED_CHATS.keys()))
        sent_users = 0
        sent_chats = 0
        failed = 0
        
        for t in raw_targets:
            try:
                target_id = int(t)
                # If negative ID, ensure it is a group and not a broadcast channel
                if str(target_id).startswith("-"):
                    try:
                        chat_info = await bot_c.get_chat(target_id)
                        if chat_info.type == enums.ChatType.CHANNEL:
                            continue # Skip channels
                    except Exception:
                        pass

                if m.reply_to_message:
                    msg = await m.reply_to_message.copy(target_id)
                else:
                    msg = await bot_c.send_message(target_id, text_arg)
                BROADCAST_MSGS.add(f"{target_id}:{msg.id}")
                if str(target_id).startswith("-"):
                    sent_chats += 1
                else:
                    sent_users += 1
                await asyncio.sleep(0.04)
            except Exception as e:
                failed += 1
                logging.debug(f"Broadcast to {t} error: {e}")
                
        res_text = (
            "📢 **Broadcast Completed Successfully!**\n\n"
            f"👤 **Direct Users Delivered:** `{sent_users}`\n"
            f"👥 **Groups Delivered:** `{sent_chats}`\n"
            f"📊 **Total Delivered:** `{sent_users + sent_chats}`\n"
            f"⚠️ **Failed / Blocked:** `{failed}`"
        )
        if status_mid:
            await bot_api_edit_message(b_tok, m.chat.id, status_mid, res_text)
        else:
            await send_smart_reply(m, res_text)

    @bot_c.on_message(filters.command(["login", "setassistant"]) & admin_filter)
    async def ast_login_cmd(c, m):
        if m.chat.type != enums.ChatType.PRIVATE:
            return await m.reply("❌ Please use `/login` in private chat with the bot for security.")
        uid = str(m.from_user.id)
        clone_wizard[uid] = {'step': 'ast_phone'}
        await m.reply("📱 **Assistant Login Wizard**\n\nPlease enter the **Phone Number** of your assistant Telegram account with country code (e.g. `+919876543210`):")

    @bot_c.on_message(filters.command("setsession") & admin_filter)
    async def set_sess_cmd(c, m):
        if len(m.command) < 2:
            return await m.reply("Usage: `/setsession [pyrogram_session_string]`")
        new_sess = m.text.split(None, 1)[1].strip()
        wait = await m.reply("🔄 **Validating new session string...**")
        temp = Client("temp_test_sess", api_id=API_ID, api_hash=API_HASH, session_string=new_sess, in_memory=True)
        try:
            await temp.start()
            me = await temp.get_me()
            await temp.stop()
        except Exception as e:
            return await wait.edit(f"❌ **Invalid Session String:** {e}")
        
        save_json(SESSION_FILE, {"session": new_sess, "phone": getattr(me, "phone_number", "") or ""})
        await wait.edit(f"✅ **Assistant Session Updated!**\n\n👤 Name: **{me.first_name}**\n🆔 ID: `{me.id}`\n\n🔄 Restarting music engine...")
        os.system("systemctl restart fearless-music.service &")

    @bot_c.on_message(filters.command("admin") & admin_filter)
    async def main_admin(c, m):
        await delete_cmd(m)
        b_tok = getattr(c, "bot_token", None) or BOT_TOKEN
        admin_markup = {
            "inline_keyboard": [
                [{"text": "Add Admin", "callback_data": "admin_add", "style": "success"}, {"text": "Rem Admin", "callback_data": "admin_rem", "style": "danger"}],
                [{"text": "Manage Clones", "callback_data": "clones_manage", "style": "primary"}, {"text": "Broadcast", "callback_data": "admin_bc", "style": "primary"}],
                [{"text": "Bot Stats", "callback_data": "admin_stats", "style": "primary"}, {"text": "Clear Cache", "callback_data": "admin_clear_storage", "style": "danger"}],
                [{"text": "Close Panel", "callback_data": "close_admin", "style": "danger"}]
            ]
        }
        res_api = await bot_api_send_message(b_tok, m.chat.id, "🛠 **Main Admin Panel**", admin_markup)
        if not res_api or not res_api.get("ok"):
            await m.reply("🛠 **Main Admin Panel**", reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("Add Admin", callback_data="admin_add", style="success"), InlineKeyboardButton("Rem Admin", callback_data="admin_rem", style="danger")],
                [InlineKeyboardButton("Manage Clones", callback_data="clones_manage", style="primary"), InlineKeyboardButton("Broadcast", callback_data="admin_bc", style="primary")],
                [InlineKeyboardButton("Bot Stats", callback_data="admin_stats", style="primary"), InlineKeyboardButton("Clear Cache", callback_data="admin_clear_storage", style="danger")],
                [InlineKeyboardButton("Close Panel", callback_data="close_admin", style="danger")]
            ]))

    @bot_c.on_message()
    async def _track(c, m: Message):
        logging.debug(f"DEBUG: Received message in {m.chat.id}: {m.text[:50] if m.text else 'Non-text'}")
        cid = str(m.chat.id)
        if m.from_user:
            u = m.from_user
            name = u.first_name + (f" {u.last_name}" if u.last_name else "")
            uname = f"@{u.username}" if u.username else "No username"
            USER_CACHE[u.id] = {"name": name, "username": uname}
            if str(u.id) not in USERS: USERS.add(str(u.id)); save_json(USERS_FILE, USERS)
        if m.chat.type in [enums.ChatType.GROUP, enums.ChatType.SUPERGROUP] and str(m.chat.id) not in CHATS: CHATS.add(str(m.chat.id)); save_json(CHATS_FILE, CHATS)
        
        uid = str(m.from_user.id) if m.from_user else None
        if uid and uid in ADMINS and uid in clone_wizard:
            state = clone_wizard[uid]
            if state['step'] == 'ast_phone':
                phone = m.text.strip()
                state['phone'] = phone
                temp = Client("temp_ast_" + uid, api_id=API_ID, api_hash=API_HASH, in_memory=True)
                try:
                    await temp.connect()
                    code = await temp.send_code(phone)
                    state['hash'] = code.phone_code_hash
                    state['client'] = temp
                    state['step'] = 'ast_otp'
                    await m.reply("📩 **OTP Code Sent to Telegram!**\n\nPlease enter the verification code (e.g. `1 2 3 4 5` or `12345`):")
                except Exception as e:
                    await m.reply(f"❌ Failed to send OTP: {e}")
                    del clone_wizard[uid]
                return
            elif state['step'] == 'ast_otp':
                otp = m.text.strip().replace(" ", "")
                try:
                    await state['client'].sign_in(state['phone'], state['hash'], otp)
                    sess = await state['client'].export_session_string()
                    me = await state['client'].get_me()
                    save_json(SESSION_FILE, {"session": sess, "phone": state['phone']})
                    await m.reply(f"✅ **Assistant Logged In Successfully!**\n\n👤 Name: **{me.first_name}**\n🆔 ID: `{me.id}`\n\n🔄 Restarting music engine...")
                    del clone_wizard[uid]
                    os.system("systemctl restart fearless-music.service &")
                except SessionPasswordNeeded:
                    state['step'] = 'ast_password'
                    await m.reply("🔐 **2FA Password Required!**\nPlease enter your Two-Step Verification Password:")
                except Exception as e:
                    await m.reply(f"❌ OTP Verification Failed: {e}")
                    del clone_wizard[uid]
                return
            elif state['step'] == 'ast_password':
                pwd = m.text.strip()
                try:
                    await state['client'].check_password(pwd)
                    sess = await state['client'].export_session_string()
                    me = await state['client'].get_me()
                    save_json(SESSION_FILE, {"session": sess, "phone": state['phone']})
                    await m.reply(f"✅ **Assistant Logged In Successfully!**\n\n👤 Name: **{me.first_name}**\n🆔 ID: `{me.id}`\n\n🔄 Restarting music engine...")
                    del clone_wizard[uid]
                    os.system("systemctl restart fearless-music.service &")
                except Exception as e:
                    await m.reply(f"❌ 2FA Password Failed: {e}")
                    del clone_wizard[uid]
                return
            elif state['step'] == 'admin_add_id':
                ADMINS.add(m.text); save_json(ADMINS_FILE, ADMINS)
                await m.reply(f"✅ User `{m.text}` added as Admin."); del clone_wizard[uid]
                return
            elif state['step'] == 'admin_rem_id':
                if m.text in ADMINS: ADMINS.remove(m.text); save_json(ADMINS_FILE, ADMINS)
                await m.reply(f"❌ User `{m.text}` removed from Admins."); del clone_wizard[uid]
                return
            elif state['step'] == 'token': state['token'] = m.text; state['step'] = 'phone'; await m.reply("Assistant Phone:")
            elif state['step'] == 'phone':
                state['phone'] = m.text; temp = Client("temp_"+uid, api_id=API_ID, api_hash=API_HASH, in_memory=True)
                await temp.connect(); code = await temp.send_code(m.text); state['hash'] = code.phone_code_hash; state['client'] = temp; state['step'] = 'otp'
                await m.reply("OTP Sent! Enter code:")
            elif state['step'] == 'otp':
                try:
                    await state['client'].sign_in(state['phone'], state['hash'], m.text)
                    state['step'] = 'super_admin_id'; await m.reply("Enter Bot Super Admin ID:")
                except SessionPasswordNeeded: state['step'] = 'password'; await m.reply("Enter 2FA Password:")
                except Exception as e: await m.reply(f"Failed: {e}"); del clone_wizard[uid]
                return
            elif state['step'] == 'password':
                try:
                    await state['client'].check_password(m.text)
                    state['step'] = 'super_admin_id'; await m.reply("Enter Bot Super Admin ID:")
                except Exception as e: await m.reply(f"2FA Failed: {e}"); del clone_wizard[uid]
                return
            elif state['step'] == 'super_admin_id':
                sess = await state['client'].export_session_string(); exp = (datetime.now() + timedelta(days=30)).isoformat()
                token = state['token']
                CLONES[token] = {"phone": state['phone'], "session": sess, "expiry": exp, "status": "running", "super_admin": m.text}
                save_json(CLONES_FILE, CLONES)
                if m.text not in ADMINS: ADMINS.add(m.text); save_json(ADMINS_FILE, ADMINS)
                await m.reply("✅ Bot Cloned and Started Successfully!")
                asyncio.create_task(start_single_clone(token, CLONES[token]))
                del clone_wizard[uid]
                return
        
        # Auto-delete in Approved Groups with Clean Mode enabled
        if cid in APPROVED_CHATS and APPROVED_CHATS[cid].get("clean", False):
            # If not broadcast and not from bot -> delete
            if f"{cid}:{m.id}" not in BROADCAST_MSGS and not (m.from_user and m.from_user.is_bot):
                try: await m.delete()
                except: pass
                return # Don't propagate further if deleted

        m.continue_propagation()

async def setup_bot_menu_commands(token, is_clone=False):
    base_commands = [
        {"command": "play", "description": "Play audio in voice chat"},
        {"command": "vplay", "description": "Play video in voice chat"},
        {"command": "autoplay", "description": "Continuous songs stream by artist/genre"},
        {"command": "stop", "description": "Stop streaming and clear queue"},
        {"command": "skip", "description": "Skip to the next track"},
        {"command": "queue", "description": "Check current and queued songs"},
        {"command": "refresh", "description": "Restart current stream if stuck"},
        {"command": "ping", "description": "Check bot latency and uptime"},
        {"command": "help", "description": "Show help menu & command guide"},
        {"command": "start", "description": "Start the bot"},
        {"command": "settarget", "description": "Set target channel for DM controls"},
        {"command": "admin", "description": "Open Admin Control Panel"},
        {"command": "cleanmode", "description": "Toggle auto-delete in group"}
    ]
    if not is_clone:
        base_commands.extend([
            {"command": "broadcast", "description": "Broadcast message to all chats"},
            {"command": "getsource", "description": "Receive source code (Owner only)"}
        ])

    group_commands = [
        {"command": "play", "description": "Play audio in voice chat"},
        {"command": "vplay", "description": "Play video in voice chat"},
        {"command": "autoplay", "description": "Continuous songs stream by artist/genre"},
        {"command": "stop", "description": "Stop streaming and clear queue"},
        {"command": "skip", "description": "Skip to the next track"},
        {"command": "queue", "description": "Check queued songs"},
        {"command": "refresh", "description": "Restart stream if stuck"},
        {"command": "ping", "description": "Check latency"},
        {"command": "help", "description": "Show help menu"}
    ]

    try:
        session = get_shared_session()
        await session.post(
            f"https://api.telegram.org/bot{token}/setMyCommands",
            json={"commands": base_commands},
            timeout=aiohttp.ClientTimeout(total=5.0)
        )
        await session.post(
            f"https://api.telegram.org/bot{token}/setMyCommands",
            json={"commands": group_commands, "scope": {"type": "all_group_chats"}},
            timeout=aiohttp.ClientTimeout(total=5.0)
        )
        await session.post(
            f"https://api.telegram.org/bot{token}/setMyCommands",
            json={"commands": base_commands, "scope": {"type": "all_chat_administrators"}},
            timeout=aiohttp.ClientTimeout(total=5.0)
        )
        logging.info(f"DEBUG: Bot menu commands configured for {token[:8]}...")
    except Exception as e:
        logging.error(f"Failed to set bot menu commands: {e}")

async def start_single_clone(token, d):
    if token in active_clones:
        logging.info(f"Clone {token[:8]} already running.")
        return
    try:
        if 'session' not in d: return
        logging.info(f"Starting clone for {d.get('phone')}...")
        c_bot = Client("bot_"+token[:8], api_id=API_ID, api_hash=API_HASH, bot_token=token)
        c_bot.bot_token = token
        c_user = Client("user_"+token[:8], api_id=API_ID, api_hash=API_HASH, session_string=d['session'])
        c_calls = PyTgCalls(c_user)
        await c_bot.start()
        await c_user.start()
        await c_calls.start()
        c_bot.me = await c_bot.get_me()
        register_bot(c_bot, c_user, c_calls, clone_owner=int(d.get('super_admin', 0)))
        active_clones[token] = {"bot": c_bot, "user": c_user, "calls": c_calls}
        asyncio.create_task(setup_bot_menu_commands(token, is_clone=True))
        logging.info(f"Clone {d.get('phone')} started!")
    except Exception as e:
        logging.error(f"Clone {token[:8]} failed: {e}")

async def main():
    # Render Web Services require an HTTP listener. This lightweight endpoint
    # is independent of Telegram and is used only for health checks.
    global _health_runner
    if _health_runner is None:
        async def health_check(request):
            return web.json_response({"status": "ok", "service": "FearlessXMusic45"})

        health_app = web.Application()
        health_app.router.add_get("/", health_check)
        health_app.router.add_get("/health", health_check)
        _health_runner = web.AppRunner(health_app)
        await _health_runner.setup()
        port = int(os.environ.get("PORT", "10000"))
        health_site = web.TCPSite(_health_runner, "0.0.0.0", port)
        await health_site.start()
        logging.info("HTTP health server listening on 0.0.0.0:%s", port)

    await bot.start()
    bot.me = await bot.get_me()
    
    try:
        await user.start()
        await call_py.start()
        logging.info("Assistant and PyTgCalls connected successfully!")
    except Exception as e_user:
        logging.error(f"CRITICAL: Assistant account failed to start: {e_user}")
        try:
            await bot.send_message(
                SUPER_ADMIN,
                f"⚠️ **Assistant Session Expired / Unregistered!**\n\n"
                f"Error: `{e_user}`\n\n"
                f"👉 Send `/login` in bot DM to log in your assistant with OTP, or send `/setsession <session_string>`."
            )
        except Exception as e_notify:
            logging.error(f"Failed to notify super admin: {e_notify}")

    register_bot(bot, user, call_py)
    asyncio.create_task(setup_bot_menu_commands(BOT_TOKEN, is_clone=False))
    
    # Heartbeat task to keep bot alive
    async def heartbeat():
        while True:
            logging.info("HEARTBEAT: Bot is alive and active.")
            await asyncio.sleep(1800) # Every 30 mins
    asyncio.create_task(heartbeat())

    for token, d in CLONES.items():
        asyncio.create_task(start_single_clone(token, d))
        
    logging.info("Main Bot Ready!"); await asyncio.Event().wait()

if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    def handle_exception(loop, context):
        msg = context.get("exception", context["message"])
        logging.error(f"Caught exception: {msg}")
        if "exception" in context:
            traceback.print_handler = lambda x: logging.error(x)
            traceback.print_exception(type(msg), msg, msg.__traceback__)
    loop.set_exception_handler(handle_exception)
    
    while True:
        try:
            logging.info("Starting bot...")
            loop.run_until_complete(main())
        except Exception as e:
            logging.error(f"Main loop crashed: {e}")
            traceback.print_exc()
            time.sleep(10)
