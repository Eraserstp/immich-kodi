import json
import sys
from datetime import datetime, timedelta

import xbmc
import xbmcgui
import xbmcplugin

import iso8601
from album import get_album_assets
from models import ItemAsset, TimelineBucket
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


def _asset_datetime(asset):
    value = asset.localDateTime or asset.fileCreatedAt
    if not value:
        return None
    try:
        return iso8601.parse_date(value)
    except iso8601.ParseError:
        return None


def _asset_day(asset):
    dt = _asset_datetime(asset)
    return dt.strftime("%Y-%m-%d") if dt else None


def _build_items(assets, video):
    items = []

    for asset in assets:
        if video and asset.type == "IMAGE":
            continue
        if not asset.exifInfo.dateTimeOriginal and asset.fileModifiedAt:
            try:
                asset.exifInfo.dateTimeOriginal = iso8601.parse_date(
                    asset.fileModifiedAt
                ).strftime("%Y-%m-%dT%H:%M:%S%z")
            except iso8601.ParseError:
                pass
        if not asset.exifInfo.dateTimeOriginal:
            continue

        try:
            label = get_asset_name(asset)
        except (iso8601.ParseError, TypeError):
            label = asset.originalFileName or asset.id

        item = xbmcgui.ListItem(label)
        item.setArt({"thumb": getThumbUrl(asset.id)})
        item.setProperty("MimeType", asset.originalMimeType or "")
        item.setDateTime(asset.exifInfo.dateTimeOriginal.replace("Z", "+00:00"))
        items.append((get_playback(asset.id, asset.type), item, False))

    return items


def _album_day_buckets(assets, video):
    buckets = {}
    for asset in assets:
        if video and asset.type == "IMAGE":
            continue
        day = _asset_day(asset)
        if day:
            buckets[day] = buckets.get(day, 0) + 1
    return sorted(buckets.items(), reverse=True)


def time(time_bucket, video, album_id=None):
    xbmcplugin.setContent(HANDLE, "images")

    if album_id:
        assets = [
            asset
            for asset in get_album_assets(album_id)
            if _asset_day(asset) == time_bucket
        ]
    else:
        headers = {
            "Accept": "application/json",
            "User-agent": xbmc.getUserAgent(),
            "x-api-key": API_KEY,
        }
        path = "/api/timeline/bucket?size=MONTH&timeBucket=" + time_bucket
        res = _timeline_get(path, headers)
        assets = [
            ItemAsset.from_api_response(get_asset_info(asset_id))
            for asset_id in res["id"]
        ]

    items = _build_items(assets, video)

    xbmcplugin.addDirectoryItems(HANDLE, items, len(items))
    xbmcplugin.addSortMethod(HANDLE, sortMethod=xbmcplugin.SORT_METHOD_DATE)
    xbmcplugin.endOfDirectory(HANDLE, cacheToDisc=False)


def timeline(video, album_id=None):
    video_flag = bool(video)
    video = "1" if video_flag else ""

    xbmcplugin.setContent(HANDLE, "files")

    if album_id:
        # Album view is day-based: a single-month album would otherwise show
        # only one month entry. Assets come from one paginated search instead
        # of one /api/assets call per item.
        items = []
        for day, _count in _album_day_buckets(
            get_album_assets(album_id), video_flag
        ):
            items.append(
                (
                    get_url(
                        action="album_time", id=day, video=video, album=album_id
                    ),
                    xbmcgui.ListItem(
                        strftime_polyfill(datetime.fromisoformat(day), datelong)
                    ),
                    True,
                )
            )
            items[-1][1].setDateTime(day + "T00:00:00Z")
    else:
        headers = {
            "Accept": "application/json",
            "User-agent": xbmc.getUserAgent(),
            "x-api-key": API_KEY,
        }
        res = _timeline_get("/api/timeline/buckets?size=MONTH", headers)
        res = [TimelineBucket.from_api_response(i) for i in res]

        items = [
            (
                get_url(action="time", id=i.timeBucket, video=video),
                xbmcgui.ListItem(
                    strftime_polyfill(datetime.fromisoformat(i.timeBucket), datelong)
                ),
                True,
            )
            for i in res
        ]
        for item, timeline in zip(items, res):
            item[1].setDateTime(
                last_day_of_month(
                    datetime.fromisoformat(timeline.timeBucket)
                ).strftime("%Y-%m-%dT00:00:00Z")
            )

    xbmcplugin.addDirectoryItems(HANDLE, items, len(items))
    xbmcplugin.addSortMethod(HANDLE, sortMethod=xbmcplugin.SORT_METHOD_DATE)
    xbmcplugin.endOfDirectory(HANDLE, cacheToDisc=False)
