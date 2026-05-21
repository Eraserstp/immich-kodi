import json
import sys
import xbmc
import xbmcgui
import xbmcplugin

import iso8601
from models import ItemAsset
from utils import API_KEY, conn, get_asset_name, get_playback, get_url, getThumbUrl

HANDLE = int(sys.argv[1])


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


def list_tags():
    conn.request("GET", "/api/tags", "", _headers())
    res = json.loads(conn.getresponse().read().decode("utf-8"))

    items = [
        (get_url(action="tag", id=str(tag["id"])), xbmcgui.ListItem(tag["value"]), True)
        for tag in res
    ]

    xbmcplugin.addSortMethod(HANDLE, sortMethod=xbmcplugin.SORT_METHOD_LABEL)
    xbmcplugin.addDirectoryItems(HANDLE, items, len(items))
    xbmcplugin.endOfDirectory(HANDLE, cacheToDisc=False)


def tag(tag_id):
    xbmcplugin.setContent(HANDLE, "images")

    conn.request(
        "POST",
        "/api/search/metadata",
        body=json.dumps({"tagIds": [tag_id], "withExif": True, "page": 1}),
        headers=_headers(content_type=True),
    )
    res = json.loads(conn.getresponse().read().decode("utf-8"))

    assets_response = _extract_assets(res)

    assets = [ItemAsset.from_api_response(i) for i in assets_response]

    for asset in assets:
        if not asset.exifInfo.dateTimeOriginal:
            asset.exifInfo.dateTimeOriginal = iso8601.parse_date(
                asset.fileModifiedAt
            ).strftime("%Y-%m-%dT%H:%M:%S%z")

    items = [
        (
            get_playback(asset.id, asset.type),
            xbmcgui.ListItem(get_asset_name(asset)),
            False,
        )
        for asset in assets
    ]

    for item, asset in zip(items, assets):
        item[1].setArt({"thumb": getThumbUrl(asset.id)})
        item[1].setProperty("MimeType", asset.originalMimeType)
        item[1].setDateTime(asset.exifInfo.dateTimeOriginal)

    xbmcplugin.addDirectoryItems(HANDLE, items, len(items))
    xbmcplugin.addSortMethod(HANDLE, sortMethod=xbmcplugin.SORT_METHOD_DATE)
    xbmcplugin.endOfDirectory(HANDLE, cacheToDisc=False)
