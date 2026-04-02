#!/usr/bin/env python3
"""
extract_doc.py — Convert .doc → extracted JSON chunks
=======================================================
Bước 1: LibreOffice convert .doc → .txt (UTF-8)
Bước 2: doc_extractor.py parse .txt → JSON

Usage:
    python scripts/extract_doc.py --file "data/raw/lao-dong-2012/Bo-Luat-lao-dong-2012.doc" --law-id lao-dong-2012 --so-hieu "10/2012/QH13" --hieu-luc 2013-05-01
    python scripts/extract_doc.py --all
"""
import argparse, subprocess, sys, tempfile
from pathlib import Path

ROOT = Path(__file__).parent.parent


def find_soffice() -> str | None:
    """Tìm LibreOffice executable trên Windows/Linux/Mac."""
    candidates = [
        # Windows
        r"C:\Program Files\LibreOffice\program\soffice.exe",
        r"C:\Program Files (x86)\LibreOffice\program\soffice.exe",
        r"C:\Program Files\LibreOffice 7\program\soffice.exe",
        r"C:\Program Files\LibreOffice 6\program\soffice.exe",
        # Linux skill wrapper
        "/mnt/skills/public/docx/scripts/office/soffice.py",
        # PATH fallback
        "soffice",
        "libreoffice",
    ]
    for c in candidates:
        p = Path(c)
        if p.exists():
            return str(p)
    # Try soffice in PATH
    try:
        subprocess.run(["soffice", "--version"], capture_output=True, timeout=5)
        return "soffice"
    except Exception:
        pass
    try:
        subprocess.run(["libreoffice", "--version"], capture_output=True, timeout=5)
        return "libreoffice"
    except Exception:
        pass
    return None


def convert_doc_to_txt(doc_path: Path, out_dir: Path) -> Path | None:
    """Convert .doc → .txt via LibreOffice."""
    out_dir.mkdir(parents=True, exist_ok=True)

    soffice = find_soffice()
    if not soffice:
        print("  ❌ LibreOffice không tìm thấy.", file=sys.stderr)
        print("     Cài tại: https://www.libreoffice.org/download/download/", file=sys.stderr)
        return None

    # Linux skill wrapper needs python3
    if soffice.endswith(".py"):
        cmd = ["python3", soffice, "--headless",
               "--convert-to", "txt:Text (encoded):UTF8",
               str(doc_path), "--outdir", str(out_dir)]
    else:
        cmd = [soffice, "--headless",
               "--convert-to", "txt:Text (encoded):UTF8",
               "--outdir", str(out_dir),
               str(doc_path)]

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    txt_path = out_dir / (doc_path.stem + ".txt")
    if not txt_path.exists():
        print(f"  ❌ Conversion failed.", file=sys.stderr)
        if result.stderr:
            print(f"     {result.stderr[:300]}", file=sys.stderr)
        return None
    return txt_path


def find_python() -> str:
    """Dùng python executable hiện tại."""
    return sys.executable


def extract_one(law_id: str, doc_path, so_hieu: str, hieu_luc: str, loai: str = "luat") -> bool:
    doc_path = Path(doc_path)
    if not doc_path.exists():
        print(f"  ❌ {law_id}: File không tồn tại: {doc_path}", file=sys.stderr)
        return False

    print(f"  🔧 {law_id}: Converting {doc_path.name}...", file=sys.stderr)

    with tempfile.TemporaryDirectory() as tmpdir:
        txt_path = convert_doc_to_txt(doc_path, Path(tmpdir))
        if not txt_path:
            return False

        out_dir  = ROOT / "data" / "extracted" / law_id
        out_dir.mkdir(parents=True, exist_ok=True)
        out_json = out_dir / f"{law_id}.json"

        cmd = [
            find_python(),
            str(ROOT / "scripts" / "doc_extractor.py"),
            "--file",     str(txt_path),
            "--law-id",   law_id,
            "--output",   str(out_json),
            "--hieu-luc", hieu_luc,
            "--so-hieu",  so_hieu,
            "--loai",     loai,
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode == 0:
            print(f"  {result.stderr.strip()}", file=sys.stderr)
            return True
        else:
            print(f"  ❌ {law_id}: {result.stderr[:400]}", file=sys.stderr)
            return False


def main():
    p = argparse.ArgumentParser(description="Extract .doc law files → JSON chunks")
    p.add_argument("--file",     help="Path to .doc file")
    p.add_argument("--law-id",   help="Law ID slug (e.g. lao-dong-2012)")
    p.add_argument("--so-hieu",  default="", help="Số hiệu văn bản")
    p.add_argument("--hieu-luc", default="", help="Ngày hiệu lực (YYYY-MM-DD)")
    p.add_argument("--loai",     default="luat", help="luat | nghi-dinh | thong-tu")
    p.add_argument("--all",      action="store_true", help="Extract tất cả từ registry.yaml")
    args = p.parse_args()

    if args.all:
        try:
            import yaml
        except ImportError:
            print("  ❌ Thiếu pyyaml. Chạy: pip install pyyaml", file=sys.stderr)
            sys.exit(1)

        reg_path = ROOT / "crawler" / "registry.yaml"
        with open(reg_path, encoding="utf-8") as f:
            laws = yaml.safe_load(f)["laws"]

        print(f"\n  📦 Extracting {len(laws)} laws...\n", file=sys.stderr)
        ok = fail = 0
        for law in laws:
            law_id  = law["law_id"]
            doc_dir = ROOT / law.get("output_dir", f"data/raw/{law_id}")
            docs = list(doc_dir.glob("*.doc")) + list(doc_dir.glob("*.docx"))
            if not docs:
                print(f"  ⏭️  {law_id}: Không tìm thấy .doc trong {doc_dir}", file=sys.stderr)
                continue
            success = extract_one(
                law_id, docs[0],
                law.get("so_hieu", ""),
                law.get("ngay_hieu_luc", ""),
                law.get("loai_van_ban", "luat"),
            )
            if success: ok += 1
            else:        fail += 1

        print(f"\n  ✅ {ok} OK | ❌ {fail} failed", file=sys.stderr)

    else:
        if not args.file or not args.law_id:
            p.error("--file và --law-id bắt buộc (hoặc dùng --all)")
        extract_one(args.law_id, args.file, args.so_hieu, args.hieu_luc, args.loai)


if __name__ == "__main__":
    main()