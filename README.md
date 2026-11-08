# Immich for Kodi

[English](README.md) | [Русский](README.ru.md)

> **This project is a fork of [vladd11/immich-kodi](https://github.com/vladd11/immich-kodi).**
>
> The original addon was created by Vladislav ([vladd11](https://github.com/vladd11)).
> Many thanks to all upstream contributors, including Alexander Groß, aLiEnHeAd13,
> bpawnzz, Christopher Hall, milaq, symc and TheHacker66, as well as to
> [t-berst](https://github.com/t-berst) for the Immich 3.x compatibility work that
> was merged into this fork.
>
> This fork is maintained by [Eraserstp](https://github.com/Eraserstp).

An unofficial Kodi addon for browsing photos and videos stored in
[Immich](https://immich.app).

## Requirements

- Kodi 19 (Matrix) or newer (`xbmc.python` 3.0.0).
- Immich 3.x; the addon is tested against Immich 3.3.3. Legacy API fallbacks
  exist for older servers, but they are not the primary target.
- Network access from the Kodi device to the Immich server.

## Installation

1. Obtain the addon as a ZIP archive (`plugin.video.immich-<version>.zip`).
2. In Kodi open **Add-ons → Install from ZIP file** and select the archive.
3. Open the addon settings and fill in:
   - **Immich URL with http(s)://** — for example
     `http://YOUR_IMMICH_HOST:2283`;
   - **Immich API key** — create one in Immich under
     **User settings → API Keys**.
4. Optionally adjust the display name format and the cache lifetime.

## Features

- **Timeline** — browse the library by month, photos and videos together.
- **Videos** — same timeline, videos only.
- **Albums** — browse albums and their assets.
- **Albums by Timeline** — open an album as a list of dates (days), then browse
  only the assets from the selected day.
- **Tags** — browse assets by tag. Tags without any assets are hidden.
- Automatic thumbnails, sorting by date and locale-aware date labels.
- English and Russian interface.

## What is different in this fork

The following changes were made under the maintainer's control.

### Immich 3.x API compatibility

- Models tolerate missing and unknown fields returned by newer Immich versions.
- Album assets are loaded through `POST /api/search/metadata` when the server no
  longer embeds them in the album response.
- Search uses the current `filter` object and cursor pagination, with a fallback
  to the legacy `albumIds`/`tagIds`/`page` parameters for Immich < 3.2.
- Timeline includes partners' assets via `withPartners=true` and gracefully falls
  back to the user's own assets when a server rejects the parameters.
- Albums use the `video/playback` endpoint for encoded videos and the original
  media endpoint for images.

### New browsing views

- Added the **Albums by Timeline** menu entry: album → day-level date list →
  assets of that day.
- Added tag browsing with tag asset loading and removal of empty tags from the
  tag list.

### Performance

- Added a persistent on-disk API cache in the addon profile with a configurable
  TTL (default 300 seconds) and LRU-style eviction (1000 files / 256 MB).
- Large timeline months and albums are fetched in batches through
  `/api/search/metadata` instead of one `/api/assets/{id}` request per item.
  A 3352-asset month now opens in about 0.4 seconds instead of roughly 140
  seconds in local testing.
- List artwork requests the small `thumbnail` size, and video items are given
  duration/resolution metadata so Kodi does not have to probe large streams
  while building the list.

### Localization

- English and Russian string catalogues.
- Localized addon summary, description and release notes in `addon.xml`.

### Settings

- Added the **Cache lifetime, seconds (0 disables cache)** setting.

## AI-assisted development

Some of the changes in this fork were implemented with AI coding agents under
the maintainer's supervision:

- **ChatGPT via Codex**
- **DeepSeek V4.1 Flash via OpenCode**

All changes were reviewed, tested and adapted to the current Immich API before
being committed.

## Credits

- Original project: [vladd11/immich-kodi](https://github.com/vladd11/immich-kodi)
  by Vladislav and the upstream contributors.
- Immich: [immich-app/immich](https://github.com/immich-app/immich).
- Immich API documentation: [api.immich.app](https://api.immich.app).

## License

MIT. See [LICENSE.txt](LICENSE.txt).
