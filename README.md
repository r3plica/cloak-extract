# cloak-extract

List every image embedded in a **cloaked Facebook-ad landing page**.

These pages serve a clean "wellness blog" article to desktop visitors and
an image-heavy page (often containing infringing content from MetArt,
FemJoy, Blogger image sets, etc.) to mobile users arriving from Facebook.

The cloaking trigger is a query parameter (commonly `?cs=vg04`), an iOS
mobile User-Agent, and a `facebook.com` referer. This tool sends that
combination and prints every `<img>` URL it finds, grouped by host.

## Install

Requires Python 3.9+.

The launcher (`cloak-extract.bat` on Windows, `cloak-extract` on
Linux/macOS) auto-installs dependencies on first run. Or do it manually:

```sh
pip install -r requirements.txt
```

Optional: add this folder to your `PATH` so you can invoke `cloak-extract`
from anywhere.

## Usage

### Single page

```sh
# Default: download Blogger-hosted images to ./downloads/<host>/<url-slug>/
cloak-extract https://example.com/some-post/

# Don't download, just list URLs
cloak-extract https://example.com/some-post/ --skip-download

# Include all image hosts (not just Blogger)
cloak-extract https://example.com/some-post/ --all-hosts

# Custom host filter (substring match, repeatable)
cloak-extract https://example.com/some-post/ --host blogger.googleusercontent.com

# Exclude a host (e.g. skip the site's own wp-content uploads)
cloak-extract https://example.com/some-post/ --all-hosts --exclude-host wp-content

# Save URLs to a text file (in addition to downloading)
cloak-extract https://example.com/some-post/ -o urls.txt

# Detailed CSV (parses Blogger GUID/size/filename when applicable)
cloak-extract https://example.com/some-post/ --csv out.csv

# Custom output folder + parallel workers
cloak-extract https://example.com/some-post/ --out-dir ./evidence --workers 12
```

### Whole site (sitemap walk)

```sh
# Discover sitemap, walk every cloaked-style post, download into per-page folders
cloak-extract https://example.com --site
# -> creates ./downloads/example.com/<slug-1>/, ./downloads/example.com/<slug-2>/, ... + _site_summary.csv

# Just list the discovered URLs (no fetch / download)
cloak-extract https://example.com --site --list-urls

# Process all sitemap URLs (don't filter to person-name slugs)
cloak-extract https://example.com --site --all-pages

# Limit and regex-filter
cloak-extract https://example.com --site --limit 10
cloak-extract https://example.com --site --filter "whitman|carter"

# Custom parent folder
cloak-extract https://example.com --site --out-dir ./evidence
```

By default `--site` only processes pages whose slug starts with what looks
like a person's name (e.g. `clara-whitman-...`, `coralie-finns-...`),
because cloaked posts on these sites always follow that pattern. Pass
`--all-pages` to process every URL in the sitemap.

Pages whose output folder already exists (and contains files) are
**skipped automatically**, so re-running on a site is cheap — only new
posts are fetched. Pass `--overwrite` to force re-download of everything.

### Other options

```sh
# JSON output (single page)
cloak-extract https://example.com/post/ --json --skip-download

# Just per-host counts
cloak-extract https://example.com/post/ --summary --skip-download

# Also print URLs while downloading
cloak-extract https://example.com/post/ --print-urls

# Don't auto-add cs=vg04&fbclid=...
cloak-extract https://example.com/post/ --no-auto-params

# Quiet (suppress progress on stderr)
cloak-extract https://example.com/post/ -q
```

> **Windows tip:** always wrap URLs in double quotes — `&` in cmd.exe is a
> command separator and will break unquoted URLs.

## How it works

1. Adds `?cs=vg04&fbclid=IwY2xjaw` to the URL if those params are missing.
2. Sends the request with iOS Safari mobile User-Agent + `Referer:
   https://l.facebook.com/` + `sec-ch-ua-mobile: ?1`.
3. Parses the response HTML for `<img src=>`, `<img srcset=>`,
   `<source srcset=>`, plus any bare `https://...image-extension` URLs.
4. Deduplicates, groups by host, and prints them.

Progress and host counts go to **stderr**; image URLs go to **stdout**, so
you can pipe:

```sh
cloak-extract URL > urls.txt
cloak-extract URL | wc -l
cloak-extract URL | grep blogger
```

## Notes

- Sends one request only — does not follow links, does not crawl.
- Does not download image bytes — metadata only.
- Some servers IP-throttle aggressive use; throttle yourself if scripting
  many calls.
- `--no-auto-params` if you want to test whether the cloaking is actually
  param-triggered on a given site.

## Exit codes

- `0` — success
- `1` — HTTP request failed
- `2` — missing dependency

## License

For use in DMCA / abuse-reporting workflows.
