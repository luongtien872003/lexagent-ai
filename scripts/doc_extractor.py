"""
DOC Extractor v1 — Parse plain text từ LibreOffice-converted .doc
=================================================================
Input : .txt file (converted from .doc via LibreOffice)
Output: JSON chunks (điều + khoản level)

Usage:
    python doc_extractor.py \
        --file /tmp/doclaw/Bo-Luat-lao-dong-2012.txt \
        --law-id lao-dong-2012 \
        --so-hieu "10/2012/QH13" \
        --hieu-luc 2013-05-01 \
        --output data/extracted/lao-dong-2012/lao-dong-2012.json
"""
import re, json, argparse, sys
from pathlib import Path


# ── Roman numerals ──────────────────────────────────────────────────────────
ROMAN = {
    'I':1,'II':2,'III':3,'IV':4,'V':5,'VI':6,'VII':7,'VIII':8,'IX':9,'X':10,
    'XI':11,'XII':12,'XIII':13,'XIV':14,'XV':15,'XVI':16,'XVII':17,'XVIII':18,
    'XIX':19,'XX':20,'XXI':21,'XXII':22,'XXIII':23,'XXIV':24,'XXV':25,
}

def roman_to_int(s):
    s = s.strip().upper()
    return ROMAN.get(s, 0) or (int(s) if s.isdigit() else 0)


# ── Clean text ────────────────────────────────────────────────────────────────
def clean(s):
    s = re.sub(r'\s+', ' ', s)
    return s.strip()


# ── Khoản parser ─────────────────────────────────────────────────────────────
def parse_khoans(lines):
    """Extract khoản from list of body lines."""
    khoans, cur_k, cur_lines = [], None, []

    for line in lines:
        m = re.match(r'^(\d+)\.\s+(.+)', line)
        if m:
            num = int(m.group(1))
            expected = (cur_k or 0) + 1
            if num == 1 or num == expected:
                if cur_k is not None and cur_lines:
                    khoans.append({'so_khoan': cur_k,
                                   'noi_dung': ' '.join(cur_lines)})
                cur_k, cur_lines = num, [m.group(2).strip()]
                continue
        if cur_k is not None:
            cur_lines.append(line)

    if cur_k is not None and cur_lines:
        khoans.append({'so_khoan': cur_k, 'noi_dung': ' '.join(cur_lines)})
    return khoans


# ── Main extractor ────────────────────────────────────────────────────────────
def extract(text, law_id, loai_van_ban="luat", ngay_hieu_luc="", so_hieu=""):
    lines = [l.rstrip() for l in text.splitlines()]

    # Detect ten_van_ban — look for BỘ LUẬT / LUẬT line near top
    ten_van_ban = law_id
    for line in lines[:30]:
        if re.search(r'(BỘ LUẬT|LUẬT)\s+', line, re.IGNORECASE) and len(line) < 120:
            ten_van_ban = clean(line)
            break

    # Make short version
    ten_short = re.sub(r'\s+số\s+[\d/A-Za-z.]+.*$', '', ten_van_ban, flags=re.IGNORECASE).strip()
    if not ten_short:
        ten_short = ten_van_ban

    thu_tu = {"luat": 1, "nghi-dinh": 2, "thong-tu": 3}.get(loai_van_ban, 1)

    # ── State machine ──────────────────────────────────────────────────────────
    chunks = []
    chuong_so   = 0
    chuong_name = ""
    so_dieu     = None
    ten_dieu    = ""
    dieu_lines  = []
    seen_dieu   = set()

    # Regex patterns
    RE_CHUONG = re.compile(
        r'^Ch[ươ][ươ]ng\s+([IVXivx\d]+)\s*$', re.IGNORECASE
    )
    RE_DIEU = re.compile(
        r'^Điều\s+(\d+)[.\-\s]\s*(.*)', re.IGNORECASE
    )
    RE_CHUONG_NAME = re.compile(
        r'^[A-ZĐẮĂÂÊÔƯÁÀẢÃẠÉÈẺẼẸÍÌỈĨỊÓÒỎÕỌÚÙỦŨỤỨỪỬỮỰẤẦẨẪẬẮẰẲẴẶẾỀỂỄỆỐỒỔỖỘỚỜỞỠỢ\s,]+$'
    )

    def flush_dieu():
        nonlocal so_dieu, ten_dieu, dieu_lines
        if so_dieu is None or so_dieu in seen_dieu:
            so_dieu, ten_dieu, dieu_lines = None, "", []
            return
        seen_dieu.add(so_dieu)

        noi_dung = ' '.join(dieu_lines).strip()
        if not noi_dung:
            so_dieu, ten_dieu, dieu_lines = None, "", []
            return

        khoans = parse_khoans(dieu_lines)
        ctx = f"{ten_short} > Chương {chuong_so} > Điều {so_dieu}"
        did = f"{law_id}_dieu_{so_dieu:03d}"
        base = dict(
            law_id=law_id, van_ban_id=law_id, so_hieu=so_hieu,
            loai_van_ban=loai_van_ban, thu_tu_uu_tien=thu_tu,
            ngay_hieu_luc=ngay_hieu_luc,
            chuong_so=chuong_so, ten_chuong=chuong_name,
            so_dieu=so_dieu, ten_dieu=ten_dieu,
        )
        tb  = f"{ten_short} Điều {so_dieu} {ten_dieu} Chương {chuong_so} {chuong_name} {noi_dung}"[:2000]
        te  = f"passage: {ten_short} - Chương {chuong_so}: {chuong_name} - Điều {so_dieu}. {ten_dieu}\n{noi_dung}"[:2000]
        chunks.append({**base,
            "id": did, "type": "dieu", "khoan_so": 0,
            "noi_dung": noi_dung, "parent_dieu_id": "",
            "context_header": ctx,
            "text_for_bm25": tb, "text_for_embedding": te,
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
                "text_for_bm25": ktb, "text_for_embedding": kte,
            })
        so_dieu, ten_dieu, dieu_lines = None, "", []

    pending_chuong_num = None  # chuong number found, waiting for name

    for raw_line in lines:
        line = raw_line.strip()
        if not line or line.startswith('--------') or line.startswith('-------'):
            continue

        # Check Chương
        mc = RE_CHUONG.match(line)
        if mc:
            flush_dieu()
            pending_chuong_num = roman_to_int(mc.group(1))
            chuong_name = ""
            continue

        # If we have a pending chuong number, next non-empty UPPERCASE line = name
        if pending_chuong_num is not None:
            if RE_CHUONG_NAME.match(line) and len(line) > 3:
                chuong_so   = pending_chuong_num
                chuong_name = clean(line)
                pending_chuong_num = None
                continue
            elif not RE_DIEU.match(line):
                # Still accumulating chuong name (multi-line)
                chuong_so   = pending_chuong_num
                chuong_name = (chuong_name + " " + clean(line)).strip() if chuong_name else clean(line)
                continue
            else:
                # Hit a Điều before finding chuong name - accept empty name
                chuong_so   = pending_chuong_num
                pending_chuong_num = None

        # Check Điều
        md = RE_DIEU.match(line)
        if md:
            flush_dieu()
            so_dieu  = int(md.group(1))
            ten_dieu = clean(md.group(2))
            dieu_lines = []
            continue

        # Body lines
        if so_dieu is not None:
            dieu_lines.append(line)

    flush_dieu()  # last điều

    doc = {
        "id": law_id, "ten_van_ban": ten_van_ban, "so_hieu": so_hieu,
        "loai_van_ban": loai_van_ban, "ngay_hieu_luc": ngay_hieu_luc,
        "law_id": law_id, "thu_tu_uu_tien": thu_tu,
        "tong_so_dieu": sum(1 for c in chunks if c['type'] == 'dieu'),
    }
    return chunks, doc


# ── CLI ───────────────────────────────────────────────────────────────────────
def main():
    p = argparse.ArgumentParser(description="DOC Extractor v1")
    p.add_argument("--file",     required=True)
    p.add_argument("--law-id",   required=True)
    p.add_argument("--output",   required=True)
    p.add_argument("--hieu-luc", default="")
    p.add_argument("--so-hieu",  default="")
    p.add_argument("--loai",     default="luat")
    args = p.parse_args()

    text   = Path(args.file).read_text(encoding="utf-8", errors="replace")
    chunks, doc = extract(text, args.law_id, args.loai, args.hieu_luc, args.so_hieu)

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