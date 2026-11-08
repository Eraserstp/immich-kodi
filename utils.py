import hashlib
import http.client
import json
import os
import sys
import time
from datetime import datetime
from urllib.parse import urlencode, urlparse

import xbmc
import xbmcplugin
from xbmcaddon import Addon
from xbmcvfs import translatePath

import iso8601

HANDLE = int(sys.argv[1])

RAW_SERVER_URL = xbmcplugin.getSetting(HANDLE, "immich_url")
SHARED_ONLY = xbmcplugin.getSetting(HANDLE, "shared_only")
ASSET_NAMETYPE = int(xbmcplugin.getSetting(HANDLE, "asset_name"))
SERVER_URL = urlparse(RAW_SERVER_URL)
API_KEY = xbmcplugin.getSetting(HANDLE, "api_key")
ADDON_PATH = translatePath(Addon().getAddonInfo("path"))
profile_path = translatePath(Addon().getAddonInfo("profile") or "")
CACHE_DIR = os.path.join(profile_path, "cache") if profile_path else ""
CACHE_TTL = int(
    os.environ.get("IMMICH_KODI_CACHE_TTL")
    or xbmcplugin.getSetting(HANDLE, "cache_ttl")
    or "300"
)
CACHE_ENABLED = (
    bool(CACHE_DIR)
    and CACHE_TTL > 0
    and os.environ.get("IMMICH_KODI_NO_CACHE") != "1"
)
CACHE_MAX_FILES = 1000
CACHE_MAX_BYTES = 256 * 1024 * 1024
CACHE_NAMESPACE = hashlib.sha256(
    f"{RAW_SERVER_URL}|{API_KEY}".encode("utf-8")
).hexdigest()
conn = (
    http.client.HTTPSConnection(SERVER_URL.netloc)
    if SERVER_URL.scheme == "https"
    else http.client.HTTPConnection(SERVER_URL.netloc)
)
datelong = xbmc.getRegion("datelong")
timestamp = xbmc.getRegion("time")


# Kodi/JSON-RPC and locale helpers adapted from plugin.video.vrt.nu
# (GPL-3.0); see THIRD_PARTY_NOTICES.md.
# https://github.com/add-ons/plugin.video.vrt.nu/blob/15c545d16a26c9d601c424cc29e4ff8e0f7b25df/resources/lib/kodiutils.py#L388
def kodi_version():
    """Returns full Kodi version as string"""
    return xbmc.getInfoLabel("System.BuildVersion").split(" ")[0]


def kodi_version_major():
    """Returns major Kodi version as integer"""
    return int(kodi_version().split(".")[0])


workaround = (
    xbmc.getCondVisibility("System.Platform.Android") and kodi_version_major() > 20
)


def strftime_polyfill(dt: datetime, fmt: str):
    if workaround and "%-d" in fmt:
        fmt = fmt.replace("%-d", dt.strftime("%d").lstrip("0"))
    return dt.strftime(fmt)


def get_asset_name(asset):
    if ASSET_NAMETYPE == 0:
        return strftime_polyfill(
            iso8601.parse_date(asset.localDateTime), datelong + " " + timestamp
        )
    elif ASSET_NAMETYPE == 1:
        return asset.originalFileName
    else:
        return strftime_polyfill(
            iso8601.parse_date(asset.localDateTime), datelong + " " + timestamp
        )


def jsonrpc(*args, **kwargs):
    """Perform JSONRPC calls"""
    from json import dumps, loads

    # We do not accept both args and kwargs
    if args and kwargs:
        return None

    # Process a list of actions
    if args:
        for idx, cmd in enumerate(args):
            if cmd.get("id") is None:
                cmd.update(id=idx)
            if cmd.get("jsonrpc") is None:
                cmd.update(jsonrpc="2.0")
        return loads(xbmc.executeJSONRPC(dumps(args)))

    # Process a single action
    if kwargs.get("id") is None:
        kwargs.update(id=0)
    if kwargs.get("jsonrpc") is None:
        kwargs.update(jsonrpc="2.0")
    return loads(xbmc.executeJSONRPC(dumps(kwargs)))


def get_global_setting(key):
    """Get a Kodi setting"""
    result = jsonrpc(method="Settings.GetSettingValue", params={"setting": key})
    return result.get("result", {}).get("value")


def set_locale():
    """Load the proper locale for date strings, only once"""
    if hasattr(set_locale, "cached"):
        return getattr(set_locale, "cached")
    from locale import LC_ALL, Error, setlocale

    locale_lang = get_global_setting("locale.language").split(".")[-1]
    locale_lang = locale_lang[:-2] + locale_lang[-2:].upper()
    # NOTE: setlocale() only works if the platform supports the Kodi configured locale
    try:
        setlocale(LC_ALL, locale_lang)
    except (Error, ValueError):
        if locale_lang != "en_GB":
            set_locale.cached = False
            return False
    set_locale.cached = True
    return True


def _cache_path(key):
    digest = hashlib.sha256(f"{CACHE_NAMESPACE}|{key}".encode("utf-8")).hexdigest()
    return os.path.join(CACHE_DIR, digest + ".json")


def _prune_cache():
    try:
        entries = []
        total = 0
        for name in os.listdir(CACHE_DIR):
            if not name.endswith(".json"):
                continue
            path = os.path.join(CACHE_DIR, name)
            try:
                stat = os.stat(path)
            except OSError:
                continue
            entries.append((stat.st_mtime, stat.st_size, path))
            total += stat.st_size
    except OSError:
        return

    if len(entries) <= CACHE_MAX_FILES and total <= CACHE_MAX_BYTES:
        return

    over_files = len(entries) - CACHE_MAX_FILES
    over_bytes = total - CACHE_MAX_BYTES
    for _mtime, size, path in sorted(entries):
        if over_files <= 0 and over_bytes <= 0:
            break
        try:
            os.remove(path)
            over_files -= 1
            over_bytes -= size
        except OSError:
            pass


def cache_get(key):
    """Return a fresh cached payload, or None. Reading refreshes LRU order."""
    if not CACHE_ENABLED:
        return None

    path = _cache_path(key)
    try:
        with open(path, encoding="utf-8") as cache_file:
            entry = json.load(cache_file)
        if time.time() - float(entry.get("time", 0)) > CACHE_TTL:
            os.remove(path)
            return None
        os.utime(path, None)
        return entry.get("payload")
    except (OSError, ValueError, TypeError):
        return None


def cache_set(key, payload):
    if not CACHE_ENABLED:
        return

    path = _cache_path(key)
    tmp_path = f"{path}.{os.getpid()}.tmp"
    try:
        os.makedirs(CACHE_DIR, exist_ok=True)
        with open(tmp_path, "w", encoding="utf-8") as cache_file:
            json.dump(
                {"time": time.time(), "payload": payload},
                cache_file,
                ensure_ascii=False,
            )
        os.replace(tmp_path, path)
        _prune_cache()
    except OSError:
        try:
            os.remove(tmp_path)
        except OSError:
            pass


def cache_clear():
    if not CACHE_ENABLED:
        return
    try:
        for name in os.listdir(CACHE_DIR):
            if name.endswith(".json"):
                try:
                    os.remove(os.path.join(CACHE_DIR, name))
                except OSError:
                    pass
    except OSError:
        pass


def cached_get(path, headers=None):
    """GET a JSON endpoint through the on-disk cache and return (status, payload)."""
    cache_key = "GET " + path
    payload = cache_get(cache_key)
    if payload is not None:
        return 200, payload

    if headers is None:
        headers = {
            "Accept": "application/json",
            "User-agent": xbmc.getUserAgent(),
            "x-api-key": API_KEY,
        }
    conn.request("GET", path, "", headers)
    response = conn.getresponse()
    payload = json.loads(response.read().decode("utf-8"))
    if response.status == 200:
        cache_set(cache_key, payload)
    return response.status, payload


def get_playback(id, type=None):
    if type == "IMAGE":
        # if item["type"] == "IMAGE":
        return f"{RAW_SERVER_URL}/api/assets/{id}/thumbnail?size=preview|x-api-key={API_KEY}"
    else:
        return f"{RAW_SERVER_URL}/api/assets/{id}/video/playback|x-api-key={API_KEY}"


def _asset_duration_seconds(value):
    if isinstance(value, str):
        parts = value.split(":")
        if len(parts) == 3:
            try:
                return int(
                    float(parts[0]) * 3600
                    + float(parts[1]) * 60
                    + float(parts[2])
                )
            except ValueError:
                return 0
        try:
            value = float(value)
        except ValueError:
            return 0
    if isinstance(value, (int, float)):
        # Immich returns video duration in milliseconds
        return max(0, int(value / 1000))
    return 0


def apply_media_info(item, asset):
    """Give Kodi enough metadata to render the item without probing the stream."""
    item.setProperty("MimeType", asset.originalMimeType or "")

    if asset.type != "VIDEO":
        return

    info = {"mediatype": "video"}
    duration = _asset_duration_seconds(asset.duration)
    if duration:
        info["duration"] = duration
    if asset.width:
        info["width"] = asset.width
    if asset.height:
        info["height"] = asset.height
    try:
        item.setInfo("video", info)
    except (AttributeError, TypeError, ValueError):
        pass


def search_metadata(payload):
    """Call POST /api/search/metadata and return (status, parsed response)."""
    cache_key = "POST /api/search/metadata " + json.dumps(
        payload, sort_keys=True, separators=(",", ":")
    )
    cached = cache_get(cache_key)
    if cached is not None:
        return 200, cached

    conn.request(
        "POST",
        "/api/search/metadata",
        body=json.dumps(payload),
        headers={
            "Accept": "application/json",
            "User-agent": xbmc.getUserAgent(),
            "x-api-key": API_KEY,
            "Content-Type": "application/json",
        },
    )
    response = conn.getresponse()
    parsed = json.loads(response.read().decode("utf-8"))
    if response.status == 200:
        cache_set(cache_key, parsed)
    return response.status, parsed





def get_url(**kwargs):
    """
    Create a URL for calling the plugin recursively from the given set of keyword arguments.

    :param kwargs: "argument=value" pairs
    :return: plugin call URL
    :rtype: str
    """
    return "{}?{}".format(sys.argv[0], urlencode(kwargs))


def getThumbUrl(id):
    return f"{RAW_SERVER_URL}/api/assets/{id}/thumbnail?size=thumbnail|x-api-key={API_KEY}"
