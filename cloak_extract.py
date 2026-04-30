"""
cloak-extract: list every image embedded in a cloaked Facebook-ad landing page.

These sites serve a clean "wellness blog" article to desktop / non-Facebook
visitors and an image-heavy page (often containing infringing content from
MetArt, FemJoy, Blogger image sets, etc.) to mobile users arriving from
Facebook. The cloaking trigger is a query parameter (commonly ?cs=vg04) plus
mobile iOS UA and a facebook.com referer.

This tool sends the cloaking request and prints every <img> URL it finds,
grouped by host. Useful for reporting infringing content to rights holders
or to the image-host's DMCA team.

Usage:
    cloak-extract <url>
    cloak-extract <url> --host blogger.googleusercontent.com
    cloak-extract <url> --csv out.csv
    cloak-extract <url> -o urls.txt
    cloak-extract <url> --no-auto-params
    cloak-extract <url> --json
"""
from __future__ import annotations
import argparse, csv, json, os, re, sys, time
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urlparse, urlunparse, parse_qsl, urlencode, unquote

try:
    import requests
except ImportError:
    sys.stderr.write("[!] Missing dependency 'requests'. Install with: pip install -r requirements.txt\n")
    sys.exit(2)

__version__ = "1.0.0"

DEFAULT_DOWNLOAD_ROOT = "downloads"

DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
                  "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 "
                  "Mobile/15E148 Safari/604.1",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
    "Accept-Language": "en-US,en;q=0.5",
    "Referer": "https://l.facebook.com/",
    "sec-ch-ua-mobile": "?1",
    "sec-ch-ua-platform": '"iOS"',
    "Upgrade-Insecure-Requests": "1",
}

CLOAK_DEFAULTS = {"cs": "vg04", "fbclid": "IwY2xjaw"}

IMG_TAG_RE = re.compile(r"<img\b[^>]*?\bsrc\s*=\s*[\"']([^\"']+)[\"']", re.I)
SRCSET_RE  = re.compile(r"<img\b[^>]*?\bsrcset\s*=\s*[\"']([^\"']+)[\"']", re.I)
PICTURE_RE = re.compile(r"<source\b[^>]*?\b(?:srcset|src)\s*=\s*[\"']([^\"']+)[\"']", re.I)
ABS_URL_RE = re.compile(r"https?://[^\s\"'<>]+", re.I)

BLOGGER_PARTS_RE = re.compile(
    r"https://blogger\.googleusercontent\.com/img/[ab]/[A-Za-z0-9_\-]+/"
    r"(?P<guid>[A-Za-z0-9_\-]+)/s(?P<size>\d+)/(?P<file>[^\s\"'<>]+)$"
)


def ensure_cloaking_params(url: str) -> str:
    p = urlparse(url)
    q = dict(parse_qsl(p.query, keep_blank_values=True))
    changed = False
    for k, v in CLOAK_DEFAULTS.items():
        if k not in q:
            q[k] = v
            changed = True
    if not changed:
        return url
    return urlunparse(p._replace(query=urlencode(q)))


def extract_image_urls(html: str, base_url: str) -> list[str]:
    """Return a de-duplicated, ordered list of absolute image URLs found in html."""
    seen: set[str] = set()
    out: list[str] = []

    def add(u: str) -> None:
        u = u.strip()
        if not u or u.startswith("data:"):
            return
        if u.startswith("//"):
            u = "https:" + u
        elif u.startswith("/"):
            base = urlparse(base_url)
            u = f"{base.scheme}://{base.netloc}{u}"
        elif not u.startswith(("http://", "https://")):
            return
        if u not in seen:
            seen.add(u)
            out.append(u)

    for src in IMG_TAG_RE.findall(html):
        add(src)
    for srcset in SRCSET_RE.findall(html) + PICTURE_RE.findall(html):
        for part in srcset.split(","):
            cand = part.strip().split(" ")[0]
            add(cand)

    img_ext_re = re.compile(r"\.(?:jpg|jpeg|png|gif|webp|bmp|svg|avif)(?:[?#]|$)", re.I)
    for u in ABS_URL_RE.findall(html):
        if img_ext_re.search(u):
            u_clean = u.rstrip(".,);\"'")
            add(u_clean)

    return out


def group_by_host(urls: list[str]) -> dict[str, list[str]]:
    g: dict[str, list[str]] = {}
    for u in urls:
        h = urlparse(u).netloc.lower()
        g.setdefault(h, []).append(u)
    return g


def parse_blogger(u: str) -> dict[str, str] | None:
    m = BLOGGER_PARTS_RE.match(u)
    if not m:
        return None
    return m.groupdict()


def fetch(url: str, timeout: int = 30) -> "requests.Response":
    return requests.get(url, headers=DEFAULT_HEADERS, timeout=timeout, allow_redirects=True)


SITEMAP_CANDIDATES = [
    "/wp-sitemap.xml",
    "/sitemap.xml",
    "/sitemap_index.xml",
    "/sitemap-index.xml",
]

# Common non-name words that appear at the start of legitimate-looking blog
# slugs. Used to reject "green-beans-onions" while accepting "coralie-finns-...".
_SLUG_STOPWORDS = {
    "how", "many", "much", "what", "does", "do", "can", "is", "are", "to",
    "the", "a", "an", "of", "in", "for", "on", "with", "best", "good", "top",
    "difference", "between", "types", "ways", "reasons", "make", "add", "use",
    "vs", "and", "or", "no", "not", "should", "will", "would", "get", "put",
    "keep", "let", "have", "has", "your", "my", "this", "that", "these",
    "those", "out", "off", "up", "down", "over", "under", "about", "from",
    "by", "at", "as", "it", "be", "was", "were", "because", "why", "when",
    "where", "who", "which", "easy", "simple", "quick", "homemade", "classic",
    "fresh", "healthy", "creamy", "crispy", "crunchy", "hot", "cold", "spicy",
    "sweet", "sour", "savory", "savoury", "delicious", "tasty", "perfect",
    "ultimate", "amazing", "favorite", "favourite", "famous", "popular",
    "low", "high", "free", "rich", "loaded", "stuffed", "baked", "fried",
    "grilled", "roasted", "steamed", "boiled", "smoked", "pan", "oven",
    "slow", "instant", "pressure", "air", "deep", "stir",
    "green", "red", "yellow", "white", "black", "brown", "blue", "purple",
    "orange", "pink",
    "beans", "rice", "pasta", "chicken", "beef", "pork", "fish", "salmon",
    "tuna", "shrimp", "lobster", "crab", "lamb", "turkey", "duck", "egg",
    "eggs", "cheese", "cream", "butter", "milk", "yogurt", "yoghurt",
    "bread", "cake", "cookie", "cookies", "pie", "pies", "soup", "soups",
    "salad", "salads", "stew", "stews", "sauce", "sauces", "dip", "dips",
    "drink", "drinks", "smoothie", "smoothies", "tea", "teas", "coffee",
    "juice", "juices", "potato", "potatoes", "tomato", "tomatoes", "onion",
    "onions", "garlic", "carrot", "carrots", "broccoli", "spinach", "kale",
    "lettuce", "cabbage", "pepper", "peppers", "corn", "peas", "lentil",
    "lentils", "noodle", "noodles", "pizza", "burger", "taco", "tacos",
    "wrap", "wraps", "sandwich", "sandwiches", "breakfast", "lunch",
    "dinner", "snack", "snacks", "dessert", "desserts", "appetizer",
    "appetizers", "side", "sides", "main", "mains", "recipe", "recipes",
    "casserole", "stuffing",
    "bacon", "ham", "sausage", "meatball", "meatballs", "steak", "ribs",
    "wings", "thighs", "breast", "drumstick", "fillet", "loin",
    "apple", "apples", "banana", "bananas", "berry", "berries", "cherry",
    "cherries", "lemon", "lemons", "lime", "limes", "orange", "oranges",
    "peach", "peaches", "pear", "pears", "grape", "grapes",
    "vegan", "vegetarian", "keto", "paleo", "gluten",
}


def looks_like_name_slug(url: str) -> bool:
    """Heuristic: True if the URL slug starts with what looks like a person's
    name (firstname-lastname...). Used to filter cloaked-style posts.

    Accepts: clara-whitman-..., coralie-finns-..., trista-colwyns-...
    Rejects: green-beans-..., how-much-..., what-does-...
    """
    p = urlparse(url)
    parts = [seg for seg in p.path.lower().split("/") if seg]
    if not parts:
        return False
    slug = parts[-1]
    tokens = re.split(r"[-_]", slug)
    tokens = [t for t in tokens if t]
    if len(tokens) < 2:
        return False
    a, b = tokens[0], tokens[1]
    if not (a.isalpha() and b.isalpha()):
        return False
    if len(a) < 3 or len(b) < 3:
        return False
    if a in _SLUG_STOPWORDS or b in _SLUG_STOPWORDS:
        return False
    return True


def _xml_locs(text: str) -> list[str]:
    return re.findall(r"<loc>\s*([^<\s]+)\s*</loc>", text)


def discover_sitemap_urls(site_root: str, info=lambda m: None) -> list[str]:
    """Find all post/page URLs by walking robots.txt + standard sitemap paths.

    Recursively expands sitemap-index documents.
    """
    p = urlparse(site_root)
    if not p.scheme:
        site_root = "https://" + site_root
        p = urlparse(site_root)
    base = f"{p.scheme}://{p.netloc}"
    seen_sitemaps: set[str] = set()
    sitemap_queue: list[str] = []

    try:
        robots = fetch(base + "/robots.txt", timeout=15)
        if robots.ok:
            for line in robots.text.splitlines():
                if line.lower().startswith("sitemap:"):
                    sm = line.split(":", 1)[1].strip()
                    if sm:
                        sitemap_queue.append(sm)
    except Exception:
        pass

    for cand in SITEMAP_CANDIDATES:
        sitemap_queue.append(base + cand)

    page_urls: set[str] = set()
    skip_sitemap_re = re.compile(r"taxonom|category|tag|author|user", re.I)
    while sitemap_queue:
        sm = sitemap_queue.pop(0)
        if sm in seen_sitemaps:
            continue
        seen_sitemaps.add(sm)
        if skip_sitemap_re.search(urlparse(sm).path):
            continue
        try:
            r = fetch(sm, timeout=20)
        except Exception as e:
            info(f"  sitemap fetch failed ({e}): {sm}")
            continue
        if not r.ok or "<" not in r.text:
            continue
        info(f"  sitemap: {sm}  ({len(r.text):,}b)")
        locs = _xml_locs(r.text)
        if "<sitemapindex" in r.text.lower():
            sitemap_queue.extend(locs)
        else:
            for u in locs:
                if urlparse(u).netloc == p.netloc:
                    page_urls.add(u.rstrip("/") + "/")
    return sorted(page_urls)


def process_url(url: str, args, info) -> dict:
    """Fetch one page, extract images, optionally download. Returns stats dict."""
    target = url if args.no_auto_params else ensure_cloaking_params(url)
    info(f"[*] GET {target}")
    try:
        r = fetch(target)
    except requests.RequestException as e:
        info(f"[!] Request failed: {e}")
        return {"url": url, "ok": False, "error": str(e), "images": 0, "downloaded": 0}

    info(f"[*] HTTP {r.status_code}, {len(r.text):,} bytes "
         f"(content-encoding: {r.headers.get('content-encoding','identity')})")

    urls = extract_image_urls(r.text, target)
    host_filter = list(args.host)
    if not args.all_hosts and not host_filter:
        host_filter = ["blogger.googleusercontent.com"]
    if host_filter:
        urls = [u for u in urls if any(h in urlparse(u).netloc.lower() for h in host_filter)]
    if args.exclude_host:
        urls = [u for u in urls
                if not any(h in urlparse(u).netloc.lower() for h in args.exclude_host)]

    grouped = group_by_host(urls)
    info(f"[*] {len(urls)} image(s) across {len(grouped)} host(s)")

    stats = {"url": url, "ok": True, "images": len(urls), "downloaded": 0,
             "failed": 0, "by_host": {h: len(us) for h, us in grouped.items()}}

    if args.print_urls or args.skip_download:
        for u in urls:
            print(u)

    if not args.skip_download and urls:
        slug = slug_from_url(target)
        if args.out_dir:
            dest = args.out_dir if args._single else os.path.join(args.out_dir, slug)
        else:
            dest = slug
        if (not args.overwrite and os.path.isdir(dest)
                and any(os.scandir(dest))):
            existing = sum(1 for e in os.scandir(dest) if e.is_file())
            info(f"[*] Skipping (already have {existing} file(s) in {dest}/; use --overwrite to re-download)")
            stats["skipped_page"] = True
            return stats
        info(f"[*] Downloading {len(urls)} image(s) -> {dest}/  (workers={args.workers})")
        d = download_all(urls, dest, workers=args.workers, info=info)
        stats["downloaded"] = d["ok"]
        stats["skipped"] = d["skipped"]
        stats["failed"] = d["failed"]
        stats["bytes"] = d["bytes"]

    return stats


_INVALID_FS_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]+')


def slug_from_url(url: str) -> str:
    """Derive a sensible folder name from the last non-empty path segment."""
    p = urlparse(url)
    parts = [seg for seg in p.path.split("/") if seg]
    slug = parts[-1] if parts else (p.netloc or "page")
    slug = unquote(slug)
    slug = _INVALID_FS_CHARS.sub("_", slug).strip(" .")
    return slug or "page"


def filename_from_url(url: str) -> str:
    p = urlparse(url)
    name = unquote(p.path.rsplit("/", 1)[-1]) or "image"
    name = _INVALID_FS_CHARS.sub("_", name).strip(" .")
    return name or "image"


def download_one(url: str, dest_dir: str, session: "requests.Session",
                 timeout: int = 60) -> tuple[str, str | None, int]:
    """Returns (url, error_or_None, bytes_written)."""
    import threading, uuid
    name = filename_from_url(url)
    path = os.path.join(dest_dir, name)
    if os.path.exists(path) and os.path.getsize(path) > 0:
        return (url, None, 0)
    base, ext = os.path.splitext(path)
    n = 1
    while os.path.exists(path):
        path = f"{base}_{n}{ext}"
        n += 1
    tmp = path + f".part-{uuid.uuid4().hex[:8]}"
    try:
        with session.get(url, headers=DEFAULT_HEADERS, timeout=timeout, stream=True) as r:
            if r.status_code != 200:
                return (url, f"HTTP {r.status_code}", 0)
            written = 0
            with open(tmp, "wb") as f:
                for chunk in r.iter_content(chunk_size=65536):
                    if chunk:
                        f.write(chunk)
                        written += len(chunk)
            try:
                os.replace(tmp, path)
            except OSError:
                final = f"{base}_{uuid.uuid4().hex[:8]}{ext}"
                os.replace(tmp, final)
            return (url, None, written)
    except Exception as e:
        try:
            if os.path.exists(tmp):
                os.remove(tmp)
        except Exception:
            pass
        return (url, str(e), 0)


def download_all(urls: list[str], dest_dir: str, workers: int = 8,
                 info=lambda m: None) -> dict[str, int]:
    os.makedirs(dest_dir, exist_ok=True)
    stats = {"ok": 0, "skipped": 0, "failed": 0, "bytes": 0}
    session = requests.Session()
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = {ex.submit(download_one, u, dest_dir, session): u for u in urls}
        for i, fut in enumerate(as_completed(futs), 1):
            url, err, written = fut.result()
            if err:
                stats["failed"] += 1
                info(f"[{i:4}/{len(urls)}] FAIL {err[:60]} <- {url[-60:]}")
            elif written == 0:
                stats["skipped"] += 1
            else:
                stats["ok"] += 1
                stats["bytes"] += written
            if i % 25 == 0 or i == len(urls):
                info(f"[{i:4}/{len(urls)}] ok={stats['ok']} skip={stats['skipped']} fail={stats['failed']}")
    info(f"[+] Downloaded {stats['ok']} new file(s), {stats['skipped']} already present, "
         f"{stats['failed']} failed, {stats['bytes']/1_048_576:.1f} MB in {time.time()-t0:.1f}s")
    return stats


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="cloak-extract",
        description="Extract / download images from cloaked Facebook-ad landing pages.",
    )
    ap.add_argument("url", help="Page URL, or site root if --site is used")
    ap.add_argument("--site", action="store_true",
                    help="Treat URL as a site root: discover sitemap, process every page.")
    ap.add_argument("--limit", type=int, default=0,
                    help="With --site: only process the first N pages (0 = all).")
    ap.add_argument("--filter", dest="url_filter",
                    help="With --site: only include URLs matching this regex.")
    ap.add_argument("--list-urls", action="store_true",
                    help="With --site: just print discovered page URLs and exit.")
    ap.add_argument("--all-pages", action="store_true",
                    help="With --site: process every sitemap URL (default skips pages "
                         "whose slug doesn't look like a person's name, since cloaked "
                         "posts always have name-style slugs like 'clara-whitman-...').")
    ap.add_argument("--host", action="append", default=[],
                    help="Only show images from this host (substring match). Repeatable. "
                         "Default behaviour filters to blogger.googleusercontent.com.")
    ap.add_argument("--all-hosts", action="store_true",
                    help="Don't filter to Blogger - include every image host found.")
    ap.add_argument("--exclude-host", action="append", default=[],
                    help="Exclude images from this host (substring match). Repeatable.")
    ap.add_argument("-o", "--out", help="Write unique image URLs to a text file (single-URL mode)")
    ap.add_argument("--csv", help="Write detailed CSV (url, host, guid, size, filename)")
    ap.add_argument("--json", action="store_true",
                    help="Output JSON to stdout instead of plain URLs")
    ap.add_argument("--no-auto-params", action="store_true",
                    help="Don't auto-add cloaking params (cs=vg04, fbclid=...)")
    ap.add_argument("--quiet", "-q", action="store_true", help="Suppress info on stderr")
    ap.add_argument("--summary", action="store_true",
                    help="Print only per-host counts, not URLs")
    ap.add_argument("--skip-download", action="store_true",
                    help="Don't download images, just list them")
    ap.add_argument("--print-urls", action="store_true",
                    help="Also print URLs to stdout while downloading (off by default when downloading)")
    ap.add_argument("--out-dir",
                    help="In single-URL mode: download folder. In --site mode: parent folder for per-page subfolders.")
    ap.add_argument("--workers", type=int, default=8,
                    help="Parallel image-download workers per page (default: 8)")
    ap.add_argument("--overwrite", action="store_true",
                    help="Re-download even if the page's output folder already exists "
                         "with files (default: skip already-processed pages).")
    ap.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    args = ap.parse_args(argv)

    def info(msg: str) -> None:
        if not args.quiet:
            sys.stderr.write(msg + "\n")

    if args.site:
        return run_site(args, info)
    args._single = True
    return run_single(args, info)


def run_single(args, info) -> int:
    target = args.url if args.no_auto_params else ensure_cloaking_params(args.url)
    info(f"[*] GET {target}")
    try:
        r = fetch(target)
    except requests.RequestException as e:
        sys.stderr.write(f"[!] Request failed: {e}\n")
        return 1

    info(f"[*] HTTP {r.status_code}, {len(r.text):,} bytes "
         f"(content-encoding: {r.headers.get('content-encoding','identity')})")

    urls = extract_image_urls(r.text, target)
    if not args.all_hosts and not args.host:
        args.host = ["blogger.googleusercontent.com"]
    if args.host:
        urls = [u for u in urls if any(h in urlparse(u).netloc.lower() for h in args.host)]
    if args.exclude_host:
        urls = [u for u in urls
                if not any(h in urlparse(u).netloc.lower() for h in args.exclude_host)]

    grouped = group_by_host(urls)
    info(f"[*] Found {len(urls)} unique image URL(s) across {len(grouped)} host(s):")
    for host, hurls in sorted(grouped.items(), key=lambda x: -len(x[1])):
        info(f"      {len(hurls):5}  {host}")

    will_download = not args.skip_download
    print_urls = args.print_urls or args.skip_download

    if args.json:
        payload = {
            "url": target,
            "status": r.status_code,
            "bytes": len(r.text),
            "total_unique": len(urls),
            "by_host": {h: us for h, us in grouped.items()},
        }
        print(json.dumps(payload, indent=2))
    elif print_urls and not args.summary:
        for u in urls:
            print(u)

    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write("\n".join(urls))
        info(f"[+] Wrote {len(urls)} URL(s) -> {args.out}")

    if args.csv:
        with open(args.csv, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["url", "host", "blogger_guid", "blogger_size", "blogger_filename"])
            for u in urls:
                bp = parse_blogger(u) or {}
                w.writerow([u, urlparse(u).netloc, bp.get("guid", ""),
                            bp.get("size", ""), bp.get("file", "")])
        info(f"[+] Wrote CSV -> {args.csv}")

    if will_download:
        if not urls:
            info("[!] Nothing to download (no images matched filters).")
        else:
            if args.out_dir:
                dest = args.out_dir
            else:
                netloc = urlparse(target).netloc.replace(":", "_") or "site"
                dest = os.path.join(DEFAULT_DOWNLOAD_ROOT, netloc, slug_from_url(target))
            if (not args.overwrite and os.path.isdir(dest)
                    and any(os.scandir(dest))):
                existing = sum(1 for e in os.scandir(dest) if e.is_file())
                info(f"[*] Skipping (already have {existing} file(s) in {dest}/; use --overwrite to re-download)")
            else:
                info(f"[*] Downloading {len(urls)} image(s) -> {dest}/  (workers={args.workers})")
                download_all(urls, dest, workers=args.workers, info=info)

    return 0


def run_site(args, info) -> int:
    info(f"[*] Discovering sitemap for {args.url}")
    pages = discover_sitemap_urls(args.url, info=info)
    info(f"[*] Discovered {len(pages)} page URL(s)")
    if not args.all_pages:
        before = len(pages)
        pages = [u for u in pages if looks_like_name_slug(u)]
        info(f"[*] After name-slug filter: {len(pages)} URL(s) (filtered out {before - len(pages)}; use --all-pages to disable)")
    if args.url_filter:
        rx = re.compile(args.url_filter)
        pages = [u for u in pages if rx.search(u)]
        info(f"[*] After --filter: {len(pages)} URL(s)")
    if args.limit > 0:
        pages = pages[: args.limit]
        info(f"[*] After --limit: {len(pages)} URL(s)")
    if not pages:
        info("[!] No pages found. Try --no-auto-params or check the site root.")
        return 1
    if args.list_urls:
        for u in pages:
            print(u)
        return 0

    parent_dir = args.out_dir
    if parent_dir:
        os.makedirs(parent_dir, exist_ok=True)
    else:
        netloc = urlparse(args.url).netloc.replace(":", "_") or "site"
        parent_dir = os.path.join(DEFAULT_DOWNLOAD_ROOT, netloc)
        os.makedirs(parent_dir, exist_ok=True)
        info(f"[*] Output parent: ./{parent_dir}/")

    total = {"pages": 0, "with_images": 0, "images": 0, "downloaded": 0,
             "failed": 0, "bytes": 0}
    csv_rows: list[list] = []

    args._single = False
    saved_out_dir = args.out_dir
    args.out_dir = parent_dir
    args.print_urls = False  # avoid huge stdout dump in site mode
    args.summary = True

    t0 = time.time()
    skipped_pages = 0
    for i, page in enumerate(pages, 1):
        if not args.overwrite:
            slug = slug_from_url(ensure_cloaking_params(page) if not args.no_auto_params else page)
            dest_check = os.path.join(parent_dir, slug)
            if os.path.isdir(dest_check) and any(os.scandir(dest_check)):
                existing = sum(1 for e in os.scandir(dest_check) if e.is_file())
                info(f"\n=== [{i}/{len(pages)}] {page} ===")
                info(f"[*] Skipping (already have {existing} file(s) in {dest_check}/; use --overwrite to re-download)")
                skipped_pages += 1
                csv_rows.append([page, True, 0, 0, existing, 0])
                continue
        info(f"\n=== [{i}/{len(pages)}] {page} ===")
        s = process_url(page, args, info)
        total["pages"] += 1
        if s.get("images"):
            total["with_images"] += 1
        total["images"] += s.get("images", 0)
        total["downloaded"] += s.get("downloaded", 0)
        total["failed"] += s.get("failed", 0)
        total["bytes"] += s.get("bytes", 0)
        csv_rows.append([
            s["url"], s.get("ok", False), s.get("images", 0),
            s.get("downloaded", 0), s.get("skipped", 0), s.get("failed", 0),
        ])

    args.out_dir = saved_out_dir

    summary_csv = os.path.join(parent_dir, "_site_summary.csv")
    with open(summary_csv, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["url", "ok", "images_found", "downloaded", "skipped", "failed"])
        w.writerows(csv_rows)

    info("\n=== SITE SUMMARY ===")
    info(f"  pages processed:    {total['pages']}")
    info(f"  pages skipped:      {skipped_pages} (already had files)")
    info(f"  pages with images:  {total['with_images']}")
    info(f"  images discovered:  {total['images']}")
    info(f"  images downloaded:  {total['downloaded']}")
    info(f"  images failed:      {total['failed']}")
    info(f"  bytes:              {total['bytes']/1_048_576:.1f} MB")
    info(f"  elapsed:            {time.time()-t0:.0f}s")
    info(f"  per-page summary -> {summary_csv}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
