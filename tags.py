import json
import sys
import xbmc
import xbmcgui
import xbmcplugin

import iso8601
from models import ItemAsset
from utils import API_KEY, conn, get_asset_name, get_playback, get_url, getThumbUrl

HANDLE = int(sys.argv[1])


def _headers():
    return {
        "Accept": "application/json",
        "User-agent": xbmc.getUserAgent(),
        "x-api-key": API_KEY,
    }


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

    conn.request("GET", f"/api/tags/{tag_id}", "", _headers())
    res = json.loads(conn.getresponse().read().decode("utf-8"))

    assets_response = res.get("assets") if isinstance(res, dict) else res
    assets = [ItemAsset.from_api_response(i) for i in assets_response or []]

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
