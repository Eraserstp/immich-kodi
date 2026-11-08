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
    cached_get,
    datelong,
    get_asset_name,
    get_playback,
    get_url,
    getThumbUrl,
    search_metadata,
    strftime_polyfill,
)

HANDLE = int(sys.argv[1])


def last_day_of_month(any_day):
    next_month = any_day.replace(day=28) + timedelta(days=4)
    return next_month - timedelta(days=next_month.day)


def get_asset_info(id):
    _, payload = cached_get("/api/assets/" + id)
    return payload


def _timeline_get(path, headers, include_partners=True):
    """GET a timeline endpoint including partners' assets, falling back to own assets
    if the server rejects the request (error responses are JSON objects)."""
    suffixes = ("",)
    if include_partners:
        suffixes = ("&withPartners=true&visibility=timeline", "")
    for suffix in suffixes:
        status, res = cached_get(path + suffix, headers)
        if suffix == "" or status == 200:
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


def _search_month_assets(month):
    """Fetch full assets for a timeline month through search (+/- one day).

    Returns a dict keyed by asset id, or None when the server does not
    support the `filter` search API.
    """
    start = datetime.fromisoformat(month + "-01")
    end = (start + timedelta(days=32)).replace(day=1)
    search_filter = {
        "takenAt": {
            "gte": (start - timedelta(days=1)).strftime("%Y-%m-%dT00:00:00.000Z"),
            "lt": (end + timedelta(days=1)).strftime("%Y-%m-%dT00:00:00.000Z"),
        },
        "trashedAt": {"eq": None},
    }

    assets = {}
    cursor = None
    while True:
        body = {"filter": search_filter, "size": 1000, "withExif": True}
        if cursor:
            body["cursor"] = cursor
        status, response = search_metadata(body)
        if status == 400:
            return None
        if status != 200 or not isinstance(response, dict):
            return None
        block = response.get("assets", {})
        for item in block.get("items", []):
            assets[item["id"]] = item
        cursor = block.get("nextCursor")
        if not cursor:
            return assets


def _bucket_assets(asset_ids, month):
    """Build ItemAsset models for the exact ids from /timeline/bucket."""
    assets_by_id = _search_month_assets(month)

    if assets_by_id is None:
        # Immich < 3.2: fall back to one /api/assets request per item
        return [
            ItemAsset.from_api_response(get_asset_info(asset_id))
            for asset_id in asset_ids
        ]

    assets = []
    missing = []
    for asset_id in asset_ids:
        item = assets_by_id.get(asset_id)
        if item is None:
            missing.append(asset_id)
        else:
            assets.append(ItemAsset.from_api_response(item))
    # Partner assets may not be returned by search; fetch only the gap
    assets.extend(
        ItemAsset.from_api_response(get_asset_info(asset_id))
        for asset_id in missing
    )
    return assets


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
        assets = _bucket_assets(res["id"], time_bucket[:7])

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
