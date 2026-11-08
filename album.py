import json
import sys
from datetime import datetime

import xbmc
import xbmcgui
import xbmcplugin

import iso8601
from models import Album, ItemAsset
from utils import (
    API_KEY,
    RAW_SERVER_URL,
    SHARED_ONLY,
    conn,
    get_asset_name,
    get_url,
    getThumbUrl,
    search_metadata,
)

HANDLE = int(sys.argv[1])


def list_albums():
    headers = {
        "Accept": "application/json",
        "User-agent": xbmc.getUserAgent(),
        "x-api-key": API_KEY,
    }
    conn.request("GET", "/api/albums", "", headers)
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


def _search_album_assets(id):
    """Fetch album assets through /api/search/metadata.

    Uses the non-deprecated `filter` object with cursor pagination and falls
    back to the legacy `albumIds` + `page` parameters on Immich < 3.2.
    """
    assets = []
    cursor = None
    page = 1
    filter_api = True

    while True:
        if filter_api:
            body = {
                "filter": {
                    "albumIds": {"any": [id]},
                    # The `filter` API includes trashed assets unless excluded
                    "trashedAt": {"eq": None},
                },
                "size": 1000,
                "withExif": True,
            }
            if cursor:
                body["cursor"] = cursor
        else:
            body = {"albumIds": [id], "page": page, "size": 1000, "withExif": True}

        status, resp = search_metadata(body)
        if filter_api and status == 400:
            # Immich < 3.2 does not support the `filter` object yet
            filter_api = False
            continue
        if status != 200:
            break

        block = resp["assets"] if isinstance(resp, dict) else {"items": resp}
        assets.extend(block.get("items", []))

        if filter_api:
            cursor = block.get("nextCursor")
            if not cursor:
                break
        else:
            next_page = block.get("nextPage")
            if not next_page:
                break
            page = int(next_page)

    return assets


def album(id):
    xbmcplugin.setContent(HANDLE, "images")

    headers = {
        "Accept": "application/json",
        "User-agent": xbmc.getUserAgent(),
        "x-api-key": API_KEY,
    }
    conn.request("GET", f"/api/albums/{id}", "", headers)
    data = json.loads(conn.getresponse().read().decode("utf-8"))
    res = data.get("assets")
    if not res:
        # Newer Immich versions no longer embed assets in the album response
        res = _search_album_assets(id)
    res = [ItemAsset.from_api_response(i) for i in res]
    res = [i for i in res if i.fileModifiedAt or i.exifInfo.dateTimeOriginal]

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
