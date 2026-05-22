import socket
import json

import sys
import datetime
from urllib.parse import parse_qsl

import xbmc
import xbmcaddon
import xbmcgui
import xbmcplugin

from album import list_albums, album
from tags import list_tags, tag
from timeline import timeline, time
from utils import get_url, API_KEY, conn, RAW_SERVER_URL, set_locale

DEBUG = False
if DEBUG:
    import debug

URL = sys.argv[0]
HANDLE = int(sys.argv[1])
addon = xbmcaddon.Addon()


def _headers():
    return {
        'Accept': 'application/json',
        'User-agent': xbmc.getUserAgent(),
        'x-api-key': API_KEY
    }


def check_connection_settings():
    try:
        conn.request("GET", "/api/users/me", headers=_headers())
        response = conn.getresponse()
        response.read()
        if response.code == 200:
            addon.setSetting("connection_status", addon.getLocalizedString(30025))
            addon.setSettingBool("tags_filter_ready", True)
        elif response.code == 401:
            addon.setSetting("connection_status", addon.getLocalizedString(30010))
            addon.setSettingBool("tags_filter_ready", False)
        else:
            addon.setSetting("connection_status", addon.getLocalizedString(30026))
            addon.setSettingBool("tags_filter_ready", False)
    except socket.error:
        addon.setSetting("connection_status", addon.getLocalizedString(30008))
        addon.setSettingBool("tags_filter_ready", False)


def select_tags_filter_settings():
    if not addon.getSettingBool("tags_filter_ready"):
        return
    try:
        conn.request("GET", "/api/tags", "", _headers())
        tags = json.loads(conn.getresponse().read().decode("utf-8"))
    except Exception:
        addon.setSetting("connection_status", addon.getLocalizedString(30027))
        return

    labels = [tag.get("value", "") for tag in tags]
    ids = [str(tag.get("id")) for tag in tags]
    selected = xbmcgui.Dialog().multiselect(addon.getLocalizedString(30024), labels)
    if selected is None:
        return
    selected_ids = [ids[i] for i in selected]
    addon.setSetting("excluded_tag_ids", json.dumps(selected_ids))
    addon.setSetting("connection_status", addon.getLocalizedString(30028) % len(selected_ids))
if __name__ == '__main__':
    set_locale()
    params = dict(parse_qsl(sys.argv[2][1:]))

    if not RAW_SERVER_URL:
        addon.openSettings()
        exit(0)

    try:
        conn.request("GET", "/api/users/me", headers={
            'Accept': 'application/json',
            'User-agent': xbmc.getUserAgent(),
            'x-api-key': API_KEY
        })
        response = conn.getresponse()
        response.read()
        if response.code == 401:
            dialog = xbmcgui.Dialog()
            d = dialog.ok(addon.getLocalizedString(30009),
                          addon.getLocalizedString(30010))
            exit(0)
        elif response.code != 200:
            raise Exception('Can\'t connect to Immich')
    except socket.error as e:
        dialog = xbmcgui.Dialog()
        d = dialog.ok(addon.getLocalizedString(30007),
                      addon.getLocalizedString(30008))
        exit(0)

    if not params.get('action'):
        xbmcplugin.addDirectoryItem(HANDLE, get_url(action='timeline'),
                                    xbmcgui.ListItem(addon.getLocalizedString(30002)), True)
        xbmcplugin.addDirectoryItem(HANDLE, get_url(action='timeline', video='1'),
                                    xbmcgui.ListItem(addon.getLocalizedString(30015)), True)
        xbmcplugin.addDirectoryItem(HANDLE, get_url(action='albums'),
                                    xbmcgui.ListItem(addon.getLocalizedString(30003)), True)
        xbmcplugin.addDirectoryItem(HANDLE, get_url(action='tags'),
                                    xbmcgui.ListItem(addon.getLocalizedString(30019)), True)

        xbmcplugin.endOfDirectory(HANDLE)
    elif params['action'] == 'settings':
        addon.openSettings()
    elif params['action'] == 'timeline':
        timeline('video' in params)
    elif params['action'] == 'albums':
        list_albums()
    elif params['action'] == 'album':
        album(params['id'])
    elif params['action'] == 'tags':
        list_tags()
    elif params['action'] == 'tag':
        tag(params['id'])
    elif params['action'] == 'time':
        time(params['id'], 'video' in params)
    elif params['action'] == 'check_connection':
        check_connection_settings()
    elif params['action'] == 'select_tags_filter':
        select_tags_filter_settings()

if DEBUG:
    import pydevd

    pydevd.stoptrace()
