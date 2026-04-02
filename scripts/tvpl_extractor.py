"""
TVPL Extractor v2 — Python
===========================
Parse thuvienphapluat.vn HTML → JSON chunks.

Usage:
    python tvpl_extractor.py \
        --file data/raw/bhxh/bhxh.html \
        --law-id bhxh \
        --hieu-luc 2016-01-01 \
        --so-hieu "58/2014/QH13" \
        --output data/extracted/bhxh/bhxh.json
"""
import re, json, argparse, sys
from pathlib import Path


# ── HTML utils ────────────────────────────────────────────────────────────────

def strip_tags(s: str) -> str:
    s = re.sub(r'<[^>]+>', ' ', s)
    for ent, rep in [('&nbsp;',' '),('&amp;','&'),('&lt;','<'),('&gt;','>'),
                     ('&ldquo;','"'),('&rdquo;','"'),('&apos;',"'"),('&quot;','"')]:
        s = s.replace(ent, rep)
    s = re.sub(r'&#\d+;', '', s)
    s = re.sub(r'[ \t]+', ' ', s)
    s = re.sub(r'\n\s*\n+', '\n', s)
    return s.strip()


def roman_to_int(s: str) -> int:
    roman = {
        'I':1,'II':2,'III':3,'IV':4,'V':5,'VI':6,'VII':7,'VIII':8,'IX':9,'X':10,
        'XI':11,'XII':12,'XIII':13,'XIV':14,'XV':15,'XVI':16,'XVII':17,'XVIII':18,
        'XIX':19,'XX':20,'XXI':21,'XXII':22,'XXIII':23,'XXIV':24,'XXV':25,
    }
    s = s.strip().upper()
    if s in roman: return roman[s]
    try: return int(s)
    except: return 0


# ── Content boundary ──────────────────────────────────────────────────────────

def find_vn_content(html: str) -> str:
    """
    tvpl.vn: VN text first, EN translation after.
    Boundary: first chuong_1 → second dieu_1 (EN starts).
    """
    chuong1 = [m.start() for m in re.finditer(r'<a\s+name=["\']chuong_1["\']', html, re.IGNORECASE)]
    dieu1   = [m.start() for m in re.finditer(r'<a\s+name=["\']dieu_1["\']',   html, re.IGNORECASE)]

    start = chuong1[0] if chuong1 else (dieu1[0] if dieu1 else 0)
    end   = dieu1[1]   if len(dieu1) > 1 else len(html)

    # Also cut at divRelatedDoc if present
    related = re.search(r'id=["\']divRelatedDoc["\']', html[start:end], re.IGNORECASE)
    if related:
        end = start + related.start()

    return html[start:end]


# ── Khoản parser ──────────────────────────────────────────────────────────────

def parse_khoans(text: str) -> list[dict]:
    khoans: list[dict] = []
    current_khoan: int | None = None
    current_lines: list[str]  = []

    for line in text.split('\n'):
        line = line.strip()
        if not line:
            continue
        m = re.match(r'^(\d+)\.\s+(.+)', line)
        if m:
            num = int(m.group(1))
            expected = (current_khoan or 0) + 1
            if num == 1 or num == expected:
                if current_khoan is not None and current_lines:
                    khoans.append({'so_khoan': current_khoan,
                                   'noi_dung': ' '.join(current_lines)})
                current_khoan = num
                current_lines = [m.group(2).strip()]
                continue
        if current_khoan is not None:
            current_lines.append(line)

    if current_khoan is not None and current_lines:
        khoans.append({'so_khoan': current_khoan, 'noi_dung': ' '.join(current_lines)})

    return khoans


# ── Main extractor ────────────────────────────────────────────────────────────

def extract(html: str, law_id: str, loai_van_ban: str = "luat",
            ngay_hieu_luc: str = "", so_hieu: str = "") -> tuple[list, dict]:

    # Page title
    title_m     = re.search(r'<title[^>]*>([^<]+)</title>', html, re.IGNORECASE)
    raw_title   = strip_tags(title_m.group(1)) if title_m else law_id
    ten_van_ban = re.split(r'\s*\|\s*', raw_title)[0].strip()
    ten_short   = re.sub(r'\s+số\s+[\d/A-Za-z.]+.*$', '', ten_van_ban).strip()

    vn_html = find_vn_content(html)

    # All anchors in VN content
    anchor_re = re.compile(
        r'<a\s+name=["\'](?:chuong_(\w+)|dieu_(\d+))["\']',
        re.IGNORECASE
    )
    anchors = []
    for m in anchor_re.finditer(vn_html):
        anchors.append({
            'pos':  m.start(),
            'type': 'chuong' if m.group(1) else 'dieu',
            'id':   m.group(1) if m.group(1) else m.group(2),
        })

    # ── Build chuong_map ──────────────────────────────────────────────────────
    # KEY FIX: only store FIRST valid occurrence of each chuong_id
    chuong_map: dict[str, dict] = {}
    for i, a in enumerate(anchors):
        if a['type'] != 'chuong' or a['id'].endswith('_name'):
            continue
        cid = a['id']
        if cid in chuong_map and chuong_map[cid]['so'] > 0:
            continue  # already have valid entry — skip duplicate

        # Segment: up to next non-_name anchor
        next_a  = next((aa for aa in anchors[i+1:]
                        if not (aa['type']=='chuong' and aa['id'].endswith('_name'))), None)
        seg_end = next_a['pos'] if next_a else min(a['pos'] + 2000, len(vn_html))
        seg     = vn_html[a['pos']:seg_end]

        num_m = re.search(r'[Cc]h[ươ][ươ]ng\s+([IVXivx\d]+)', seg)
        cso   = roman_to_int(num_m.group(1)) if num_m else 0

        name_m = re.search(
            r'<a\s+name=["\']chuong_' + re.escape(cid) + r'_name["\'][^>]*>(.*?)</a>',
            seg, re.IGNORECASE | re.DOTALL
        )
        cname = strip_tags(name_m.group(1)) if name_m else ""

        cname = re.sub(r'\s+', ' ', cname).strip()
        chuong_map[cid] = {'so': cso, 'name': cname}

    # ── Build dieu chunks ────────────────────────────────────────────────────
    loai_label = {"luat":"Luật","nghi-dinh":"Nghị định","thong-tu":"Thông tư"}.get(loai_van_ban,"Văn bản")
    thu_tu     = {"luat":1,"nghi-dinh":2,"thong-tu":3}.get(loai_van_ban, 1)

    chuong_so   = 0
    chuong_name = ""
    chunks: list[dict] = []

    # Track seen dieu to avoid duplicates from any repeat TOC anchors
    seen_dieu: set[int] = set()

    for i, anchor in enumerate(anchors):
        # ── Chương ──────────────────────────────────────────────────────────
        if anchor['type'] == 'chuong':
            if anchor['id'].endswith('_name'):
                continue
            cid = anchor['id']
            if cid in chuong_map and chuong_map[cid]['so'] > 0:
                chuong_so   = chuong_map[cid]['so']
                chuong_name = chuong_map[cid]['name']
            continue

        # ── Điều ─────────────────────────────────────────────────────────────
        if not anchor['id'].isdigit():
            continue
        so_dieu = int(anchor['id'])
        if so_dieu in seen_dieu:
            continue  # skip duplicate anchor
        seen_dieu.add(so_dieu)

        # Segment to next non-_name anchor
        next_anchor = next(
            (aa for aa in anchors[i+1:]
             if not (aa['type']=='chuong' and aa['id'].endswith('_name'))),
            None
        )
        seg_end = next_anchor['pos'] if next_anchor else len(vn_html)
        seg     = vn_html[anchor['pos']:seg_end]

        # ten_dieu from bold inside anchor tag
        td_m = re.search(
            r'<a\s+name=["\']dieu_\d+["\'][^>]*>\s*<b>(.*?)</b>\s*</a>',
            seg[:400], re.IGNORECASE | re.DOTALL
        )
        if not td_m:
            td_m = re.search(
                r'<a\s+name=["\']dieu_\d+["\'][^>]*>(.*?)</a>',
                seg[:400], re.IGNORECASE | re.DOTALL
            )
        ten_dieu_raw = strip_tags(td_m.group(1)) if td_m else f"Điều {so_dieu}"
        ten_dieu     = re.sub(rf'^[Đđ]i[eề]u\s*{so_dieu}[.\s]*', '', ten_dieu_raw).strip()
        # Normalize whitespace in title
        ten_dieu = re.sub(r'\s+', ' ', ten_dieu).strip()

        # Body = content after anchor's closing paragraph
        body_start = seg.find('</p>')
        body_html  = seg[body_start+4:] if body_start >= 0 else seg
        body_text  = strip_tags(body_html).strip()
        if not body_text:
            body_text = strip_tags(seg)

        # Clean noi_dung: remove title from start
        noi_dung = body_text
        noi_dung = re.sub(r'\s+', ' ', noi_dung).strip()

        if not noi_dung:
            continue

        khoans = parse_khoans(body_text)  # parse BEFORE whitespace collapse

        ctx = f"{ten_short} > Chương {chuong_so} > Điều {so_dieu}"
        did = f"{law_id}_dieu_{so_dieu:03d}"

        text_bm25  = f"{ten_short} Điều {so_dieu} {ten_dieu} Chương {chuong_so} {chuong_name} {noi_dung}"[:2000]
        text_embed = f"passage: {ten_short} - Chương {chuong_so}: {chuong_name} - Điều {so_dieu}. {ten_dieu}\n{noi_dung}"[:2000]

        base = dict(
            law_id=law_id, van_ban_id=law_id, so_hieu=so_hieu,
            loai_van_ban=loai_van_ban, thu_tu_uu_tien=thu_tu, ngay_hieu_luc=ngay_hieu_luc,
            chuong_so=chuong_so, ten_chuong=chuong_name,
            so_dieu=so_dieu, ten_dieu=ten_dieu,
        )

        chunks.append({**base,
            "id": did, "type": "dieu", "khoan_so": 0,
            "noi_dung": noi_dung, "parent_dieu_id": "",
            "context_header": ctx,
            "text_for_bm25": text_bm25,
            "text_for_embedding": text_embed,
        })

        for k in khoans:
            kid  = f"{did}_khoan_{k['so_khoan']}"
            kctx = f"{ten_short} > Chương {chuong_so} > Điều {so_dieu} > Khoản {k['so_khoan']}"
            ktb  = f"{ten_short} Điều {so_dieu} {ten_dieu} Khoản {k['so_khoan']} {k['noi_dung']}"[:2000]
            kte  = f"passage: {ten_short} - Chương {chuong_so}: {chuong_name} - Điều {so_dieu}. {ten_dieu} - Khoản {k['so_khoan']}\n{k['noi_dung']}"[:2000]
            chunks.append({**base,
                "id": kid, "type": "khoan", "khoan_so": k['so_khoan'],
                "noi_dung": k['noi_dung'], "parent_dieu_id": did,
                "context_header": kctx,
                "text_for_bm25": ktb,
                "text_for_embedding": kte,
            })

    doc = {
        "id": law_id, "ten_van_ban": ten_van_ban, "so_hieu": so_hieu,
        "loai_van_ban": loai_van_ban, "ngay_hieu_luc": ngay_hieu_luc,
        "law_id": law_id, "thu_tu_uu_tien": thu_tu,
        "tong_so_dieu": sum(1 for c in chunks if c['type'] == 'dieu'),
    }
    return chunks, doc


# ── CLI ───────────────────────────────────────────────────────────────────────

def main():
    p = argparse.ArgumentParser(description="TVPL Extractor v2")
    p.add_argument("--file",      required=True,  help="HTML input file")
    p.add_argument("--law-id",    required=True,  help="Law slug (e.g. bhxh)")
    p.add_argument("--output",    required=True,  help="JSON output file")
    p.add_argument("--hieu-luc",  default="",     help="Ngày hiệu lực (YYYY-MM-DD)")
    p.add_argument("--so-hieu",   default="",     help="Số hiệu văn bản")
    p.add_argument("--loai",      default="luat", help="luat | nghi-dinh | thong-tu")
    args = p.parse_args()

    html   = Path(args.file).read_text(encoding="utf-8", errors="replace")
    chunks, doc = extract(html, args.law_id, args.loai, args.hieu_luc, args.so_hieu)

    n_dieu  = sum(1 for c in chunks if c['type'] == 'dieu')
    n_khoan = sum(1 for c in chunks if c['type'] == 'khoan')

    out = {"document": doc, "chunks": chunks, "graph_edges": []}
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    Path(args.output).write_text(
        json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"✅ Extracted: {n_dieu} điều → {n_khoan} khoản chunks (law_id={args.law_id})", file=sys.stderr)


if __name__ == "__main__":
    main()