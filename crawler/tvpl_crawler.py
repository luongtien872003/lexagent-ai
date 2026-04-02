"""
TVPL Crawler v2 — Async crawler cho thuvienphapluat.vn
========================================================
- Rate-limited (1 req/2s per domain)
- Cached HTML output, tự decompress gzip
- Auto-extract sau khi crawl xong
- Đọc config từ registry.yaml

Usage:
    python crawler/tvpl_crawler.py                   # Crawl tất cả
    python crawler/tvpl_crawler.py --law lao-dong    # Crawl 1 luật
    python crawler/tvpl_crawler.py --list            # Liệt kê
    python crawler/tvpl_crawler.py --force           # Re-crawl dù đã có cache
    python crawler/tvpl_crawler.py --extract         # Crawl + extract luôn
"""
from __future__ import annotations
import asyncio, argparse, re, yaml
from pathlib import Path
from typing import Any

try:
    import httpx
    _HAS_HTTPX = True
except ImportError:
    _HAS_HTTPX = False
    print("⚠️  httpx not installed. Run: pip install httpx")

ROOT     = Path(__file__).parent.parent
REGISTRY = Path(__file__).parent / "registry.yaml"

# Không gửi Accept-Encoding — để httpx tự handle decompress
# Tránh nhận raw gzip bytes mà không decompress được
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "vi-VN,vi;q=0.9,en;q=0.8",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

RATE_LIMIT_DELAY = 2.0    # seconds between requests
MIN_VALID_SIZE   = 10_000  # bytes — trang hợp lệ phải lớn hơn 10KB


def load_registry() -> list[dict]:
    with open(REGISTRY, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data.get("laws", [])


async def fetch_law(law: dict[str, Any], force: bool = False) -> bool:
    """Crawl 1 law entry, save UTF-8 HTML to output_dir."""
    if not _HAS_HTTPX:
        print("  ❌ httpx required. pip install httpx")
        return False

    law_id   = law["law_id"]
    url      = law["url"]
    out_dir  = ROOT / law.get("output_dir", f"data/raw/{law_id}")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / f"{law_id}.html"

    if out_file.exists() and not force:
        size = out_file.stat().st_size
        if size >= MIN_VALID_SIZE:
            print(f"  ⏭️  {law_id}: Already cached ({size:,} bytes)")
            return True
        else:
            print(f"  ⚠️  {law_id}: Cache too small ({size} bytes), re-crawling...")

    print(f"  🌐 Crawling {law_id}: {url}")
    try:
        async with httpx.AsyncClient(
            headers=HEADERS,
            follow_redirects=True,
            timeout=30.0,
        ) as client:
            resp = await client.get(url)
            resp.raise_for_status()

        # resp.text: httpx tự decompress gzip + decode đúng charset từ Content-Type header
        html = resp.text
        raw  = html.encode("utf-8")  # re-encode sang UTF-8 chuẩn để save

        if len(raw) < MIN_VALID_SIZE:
            preview = html[:200].replace("\n", " ")
            print(f"  ⚠️  {law_id}: Response quá nhỏ ({len(raw)} bytes) — có thể bị block")
            print(f"       Preview: {preview[:120]}")
            out_file.write_bytes(raw)
            return False

        # Verify có text luật thật không
        dieu_count = len(re.findall(r'[Đđ]i[eề]u\s+\d+', html))
        if dieu_count == 0:
            print(f"  ⚠️  {law_id}: Saved {len(raw):,} bytes nhưng không tìm thấy 'Điều X'")
            print(f"       Nội dung có thể được render qua JS — extract có thể ra 0 chunks")
        else:
            print(f"  ✅ {law_id}: Saved {len(raw):,} bytes | {dieu_count} Điều → {out_file}")

        out_file.write_bytes(raw)
        return True

    except Exception as e:
        print(f"  ❌ {law_id}: {type(e).__name__}: {e}")
        return False


async def crawl_all(law_filter: str | None = None, force: bool = False):
    laws = load_registry()
    if law_filter:
        laws = [l for l in laws if l["law_id"] == law_filter]
        if not laws:
            print(f"  ❌ Law '{law_filter}' not found in registry.")
            return

    print(f"\n  🔍 Crawling {len(laws)} law(s)...\n")
    ok_count = fail_count = 0

    for i, law in enumerate(laws):
        ok = await fetch_law(law, force=force)
        if ok:
            ok_count += 1
        else:
            fail_count += 1
        if i < len(laws) - 1:
            await asyncio.sleep(RATE_LIMIT_DELAY)

    print(f"\n  ✅ OK: {ok_count} | ❌ Failed/blocked: {fail_count}")
    if fail_count > 0:
        print(f"  💡 Với các luật bị block: mở URL trong browser → Ctrl+S → Webpage HTML Only")
        print(f"     → save vào data\\raw\\<law_id>\\<law_id>.html")
    print(f"  Next: chạy extractor để parse HTML → JSON")


def extract_after_crawl(law: dict):
    """Call Go extractor on crawled HTML."""
    import subprocess
    law_id    = law["law_id"]
    out_dir   = ROOT / law.get("output_dir", f"data/raw/{law_id}")
    html_file = out_dir / f"{law_id}.html"

    if not html_file.exists():
        print(f"  ❌ HTML not found: {html_file}")
        return

    if html_file.stat().st_size < MIN_VALID_SIZE:
        print(f"  ⏭️  {law_id}: HTML quá nhỏ, skip extract")
        return

    # Tìm extractor binary
    for name in ["extractor_v2.exe", "extractor_v2", "extractor.exe"]:
        extractor = ROOT / "extractor" / name
        if extractor.exists():
            break
    else:
        print(f"  ⚠️  Extractor không tìm thấy.")
        print(f"       Chạy: cd extractor && go build -o extractor_v2.exe .")
        return

    extracted_dir = ROOT / "data" / "extracted" / law_id
    extracted_dir.mkdir(parents=True, exist_ok=True)
    out_json = extracted_dir / f"{law_id}.json"

    cmd = [
        str(extractor),
        f"--file={html_file}",
        f"--output={out_json}",
        f"--law-id={law_id}",
        f"--hieu-luc={law.get('ngay_hieu_luc', '')}",
    ]

    print(f"  🔧 Extracting {law_id}...")
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode == 0:
        stderr = result.stderr.strip()
        print(f"  ✅ {law_id}: {stderr}" if stderr else f"  ✅ {law_id}: done")
    else:
        print(f"  ❌ {law_id} extraction failed: {result.stderr.strip()}")


# ── CLI ──────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="TVPL Crawler v2")
    parser.add_argument("--law",     help="Law ID to crawl (từ registry)")
    parser.add_argument("--list",    action="store_true", help="Liệt kê tất cả laws")
    parser.add_argument("--force",   action="store_true", help="Re-crawl dù đã có cache")
    parser.add_argument("--extract", action="store_true", help="Chạy extractor sau khi crawl")
    args = parser.parse_args()

    if args.list:
        laws = load_registry()
        print(f"\n  Registered laws ({len(laws)}):\n")
        for l in laws:
            html = ROOT / l.get("output_dir", f"data/raw/{l['law_id']}") / f"{l['law_id']}.html"
            if html.exists() and html.stat().st_size >= MIN_VALID_SIZE:
                status = f"✅ {html.stat().st_size:,}b"
            else:
                status = "  (not cached)"
            print(f"    {l['law_id']:25s} {status:20s} {l['ten']}")
        return

    asyncio.run(crawl_all(law_filter=args.law, force=args.force))

    if args.extract:
        laws = load_registry()
        if args.law:
            laws = [l for l in laws if l["law_id"] == args.law]
        for law in laws:
            extract_after_crawl(law)


if __name__ == "__main__":
    main()