import json
import sys

import xbmc
import xbmcgui
import xbmcplugin

import iso8601
from models import Album, ItemAsset
from utils import (
    API_KEY,
    RAW_SERVER_URL,
    TAG_FILTER,
    conn,
    get_asset_name,
    get_url,
    getThumbUrl,
)

HANDLE = int(sys.argv[1])


def get_asset_info(asset_id):
    """Backward-compatible helper for single-asset fetch (used by old code paths)."""
    conn.request("GET", f"/api/assets/{asset_id}", "", _headers())
    return ItemAsset.from_api_response(json.loads(conn.getresponse().read().decode("utf-8")))


def _headers(content_type=False):
    headers = {
        "Accept": "application/json",
        "User-agent": xbmc.getUserAgent(),
        "x-api-key": API_KEY,
    }
    if content_type:
        headers["Content-Type"] = "application/json"
    return headers


def _extract_assets(payload):
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]

    if not isinstance(payload, dict):
        return []

    candidates = [
        payload.get("assets"),
        payload.get("items"),
        payload.get("results"),
    ]

    for candidate in candidates:
        if isinstance(candidate, list):
            return [item for item in candidate if isinstance(item, dict)]
        if isinstance(candidate, dict):
            nested = candidate.get("items") or candidate.get("assets") or candidate.get("results")
            if isinstance(nested, list):
                return [item for item in nested if isinstance(item, dict)]

    return []


def _get_tag_id_by_name(tag_name):
    conn.request("GET", "/api/tags", "", _headers())
    tags = json.loads(conn.getresponse().read().decode("utf-8"))

    normalized = tag_name.strip().lower()
    for tag in tags:
        value = tag.get("value")
        if isinstance(value, str) and value.strip().lower() == normalized:
            tag_id = tag.get("id")
            if tag_id:
                return str(tag_id)

    return None


def _get_excluded_asset_ids_for_album(album_id, tag_name):
    tag_id = _get_tag_id_by_name(tag_name)
    if not tag_id:
        return set()

    conn.request(
        "POST",
        "/api/search/metadata",
        body=json.dumps({"albumIds": [album_id], "tagIds": [tag_id], "page": 1}),
        headers=_headers(content_type=True),
    )
    payload = json.loads(conn.getresponse().read().decode("utf-8"))

    excluded_ids = set()
    for asset in _extract_assets(payload):
        asset_id = asset.get("id")
        if asset_id:
            excluded_ids.add(asset_id)

    return excluded_ids


def list_albums():
    conn.request("GET", "/api/albums", "", _headers())
    res = json.loads(conn.getresponse().read().decode("utf-8"))
    res = [Album.from_api_response(i) for i in res]

    items = [
        (get_url(action="album", id=album.id), xbmcgui.ListItem(album.albumName), True)
        for album in res
    ]
    for item, album in zip(items, res):
        if album.startDate:
            item[1].setDateTime(
                iso8601.parse_date(album.startDate).strftime("%Y-%m-%dT%H:%M:%SZ")
            )
        if album.albumThumbnailAssetId:
            item[1].setArt({"thumb": getThumbUrl(album.albumThumbnailAssetId)})
    xbmcplugin.addSortMethod(HANDLE, sortMethod=xbmcplugin.SORT_METHOD_DATE)
    xbmcplugin.addSortMethod(HANDLE, sortMethod=xbmcplugin.SORT_METHOD_LABEL)
    xbmcplugin.addDirectoryItems(HANDLE, items, len(items))
    xbmcplugin.endOfDirectory(HANDLE, cacheToDisc=False)


def album(id):
    xbmcplugin.setContent(HANDLE, "images")

    conn.request("GET", f"/api/albums/{id}", "", _headers())
    res = json.loads(conn.getresponse().read().decode("utf-8"))["assets"]
    res = [ItemAsset.from_api_response(i) for i in res]

    if TAG_FILTER:
        excluded_ids = _get_excluded_asset_ids_for_album(id, TAG_FILTER)
        if excluded_ids:
            res = [asset for asset in res if asset.id not in excluded_ids]

    for i in res:
        if not i.exifInfo.dateTimeOriginal:
            i.exifInfo.dateTimeOriginal = iso8601.parse_date(
                i.fileModifiedAt
            ).strftime("%Y-%m-%dT%H:%M:%S%z")

    items = []
    for asset in res:
        if asset.type == "IMAGE":
            url = f"{RAW_SERVER_URL}/api/assets/{asset.id}/original|x-api-key={API_KEY}"
        else:
            url = f"{RAW_SERVER_URL}/api/assets/{asset.id}/video/playback|x-api-key={API_KEY}"
        items.append((url, xbmcgui.ListItem(get_asset_name(asset)), False))

    for item, asset in zip(items, res):
        item[1].setArt({"thumb": getThumbUrl(asset.id)})
        item[1].setProperty("MimeType", asset.originalMimeType)
        item[1].setDateTime(asset.exifInfo.dateTimeOriginal)

    xbmcplugin.addDirectoryItems(HANDLE, items, len(items))
    xbmcplugin.addSortMethod(HANDLE, sortMethod=xbmcplugin.SORT_METHOD_DATE)
    xbmcplugin.endOfDirectory(HANDLE, cacheToDisc=False)
