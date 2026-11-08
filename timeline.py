import json
import sys
from datetime import datetime, timedelta

import xbmc
import xbmcgui
import xbmcplugin

from models import ItemAsset, TimeBucket, TimelineBucket
from utils import (
    API_KEY,
    conn,
    datelong,
    get_asset_name,
    get_playback,
    get_url,
    getThumbUrl,
    strftime_polyfill,
)

HANDLE = int(sys.argv[1])


def last_day_of_month(any_day):
    next_month = any_day.replace(day=28) + timedelta(days=4)
    return next_month - timedelta(days=next_month.day)


def get_asset_info(id):
    headers = {
        "Accept": "application/json",
        "User-agent": xbmc.getUserAgent(),
        "x-api-key": API_KEY,
    }
    conn.request("GET", "/api/assets/" + id, "", headers)
    return json.loads(conn.getresponse().read().decode("utf-8"))


def _timeline_get(path, headers, include_partners=True):
    """GET a timeline endpoint including partners' assets, falling back to own assets
    if the server rejects the request (error responses are JSON objects)."""
    suffixes = ("",)
    if include_partners:
        suffixes = ("&withPartners=true&visibility=timeline", "")
    for suffix in suffixes:
        conn.request("GET", path + suffix, "", headers)
        res = json.loads(conn.getresponse().read().decode("utf-8"))
        if suffix == "" or not (
            isinstance(res, dict) and "message" in res and "statusCode" in res
        ):
            return res


def time(time_bucket, video, album_id=None):
    xbmcplugin.setContent(HANDLE, "images")

    headers = {
        "Accept": "application/json",
        "User-agent": xbmc.getUserAgent(),
        "x-api-key": API_KEY,
    }
    path = "/api/timeline/bucket?size=MONTH&timeBucket=" + time_bucket
    if album_id:
        path += "&albumId=" + album_id
    res = _timeline_get(path, headers, include_partners=not album_id)

    items = []

    for asset_id in res["id"]:
        item = get_asset_info(asset_id)
        item = ItemAsset.from_api_response(item)
        if video and item.type == "IMAGE":
            continue
        if not item.exifInfo.dateTimeOriginal:
            item.exifInfo.dateTimeOriginal = datetime.fromisoformat(
                item.fileModifiedAt
            ).strftime("%Y-%m-%dT%H:%M:%S%z")

        items.append(
            (
                get_playback(item.id, item.type),
                xbmcgui.ListItem(get_asset_name(item)),
                False,
            )
        )
        items[-1][1].setArt({"thumb": getThumbUrl(item.id)})
        items[-1][1].setProperty("MimeType", item.originalMimeType)
        items[-1][1].setDateTime(item.exifInfo.dateTimeOriginal.replace("Z", "+00:00"))
        # itemsR.append(i)

    xbmcplugin.addDirectoryItems(HANDLE, items, len(items))
    xbmcplugin.addSortMethod(HANDLE, sortMethod=xbmcplugin.SORT_METHOD_DATE)
    xbmcplugin.endOfDirectory(HANDLE, cacheToDisc=False)


def timeline(video, album_id=None):
    video = "1" if video else ""

    headers = {
        "Accept": "application/json",
        "User-agent": xbmc.getUserAgent(),
        "x-api-key": API_KEY,
    }
    path = "/api/timeline/buckets?size=MONTH"
    if album_id:
        path += "&albumId=" + album_id
    res = _timeline_get(path, headers, include_partners=not album_id)
    res = [TimelineBucket.from_api_response(i) for i in res]

    xbmcplugin.setContent(HANDLE, "files")

    action = "album_time" if album_id else "time"
    extra = {"album": album_id} if album_id else {}
    items = [
        (
            get_url(action=action, id=i.timeBucket, video=video, **extra),
            xbmcgui.ListItem(
                strftime_polyfill(datetime.fromisoformat(i.timeBucket), datelong)
            ),
            True,
        )
        for i in res
    ]
    for item, timeline in zip(items, res):
        item[1].setDateTime(
            last_day_of_month(datetime.fromisoformat(timeline.timeBucket)).strftime(
                "%Y-%m-%dT00:00:00Z"
            )
        )

    xbmcplugin.addDirectoryItems(HANDLE, items, len(items))
    xbmcplugin.addSortMethod(HANDLE, sortMethod=xbmcplugin.SORT_METHOD_DATE)
    xbmcplugin.endOfDirectory(HANDLE, cacheToDisc=False)
