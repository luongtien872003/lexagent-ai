#!/usr/bin/env python3
"""
CLI: Index tất cả extracted JSONs sang BM25 pkl.
Usage:
    python scripts/index_bm25.py                          # Index tất cả data/extracted/
    python scripts/index_bm25.py --input extractor/output/10.2012.QH13.json --law-id lao-dong-2012
"""
import argparse, json, pickle, sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from rank_bm25 import BM25Okapi
try:
    from underthesea import word_tokenize
    _USE_UNDERTHESEA = True
except ImportError:
    _USE_UNDERTHESEA = False
    print("⚠️  underthesea not found. Using whitespace tokenizer.")


def tokenize(text: str) -> list[str]:
    text = text.lower()
    if _USE_UNDERTHESEA:
        return [t for t in word_tokenize(text, format="text").split() if len(t) >= 2]
    return [t for t in text.split() if len(t) >= 2]


def index_file(json_path: Path, law_id: str, out_dir: Path):
    with open(json_path, encoding="utf-8") as f:
        data = json.load(f)

    chunks = data.get("chunks", [])
    if not chunks:
        print(f"  ❌ No chunks in {json_path}")
        return

    # Prefer khoản-level, fall back to dieu-level
    khoan = [c for c in chunks if c.get("type") == "khoan"]
    indexable = khoan if khoan else chunks
    indexable = [c for c in indexable if len(c.get("noi_dung", "")) >= 30]
    print(f"  📄 {law_id}: {len(indexable)} chunks ({('khoản' if khoan else 'điều')}-level)")

    corpus = [tokenize(c.get("text_for_bm25") or c.get("noi_dung", "")) for c in indexable]
    bm25   = BM25Okapi(corpus, k1=1.5, b=0.75)

    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / f"bm25_{law_id}.pkl"
    with open(out_file, "wb") as f:
        pickle.dump({"bm25": bm25, "chunks": indexable, "law_id": law_id}, f)
    print(f"  ✅ → {out_file}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input",      help="Single JSON file to index")
    parser.add_argument("--law-id",     help="Law ID (required with --input)")
    parser.add_argument("--output-dir", default="data/indexes")
    args = parser.parse_args()

    out_dir = ROOT / args.output_dir

    if args.input:
        if not args.law_id:
            parser.error("--law-id required with --input")
        index_file(ROOT / args.input, args.law_id, out_dir)
    else:
        # Index all extracted/
        extracted = ROOT / "data" / "extracted"
        if not extracted.exists():
            print(f"  ❌ {extracted} not found. Run crawler + extractor first.")
            sys.exit(1)

        jsons = list(extracted.rglob("*.json"))
        if not jsons:
            # Fallback: original extractor output
            orig = ROOT / "extractor" / "output" / "10.2012.QH13.json"
            if orig.exists():
                index_file(orig, "lao-dong-2012", out_dir)
            else:
                print("  ❌ No JSON files found.")
            return

        for json_file in sorted(jsons):
            law_id = json_file.parent.name or json_file.stem
            index_file(json_file, law_id, out_dir)

    print(f"\n  Done. Indexes in: {out_dir}/")


if __name__ == "__main__":
    main()
