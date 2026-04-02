"""
BM25 Indexer v2
===============
- Index khoản-level chunks (1 chunk = 1 khoản) thay vì dieu-level
- Output: indexer/indexes/bm25_{law_id}.pkl
- Backward compatible với dieu-level JSON (nếu không có khoan thì dùng dieu)

Usage:
    python indexer/bm25_index.py --input extractor/output/10.2012.QH13.json --law-id lao-dong-2012
    python indexer/bm25_index.py --input data/extracted/lao-dong/lao-dong.json
"""
from __future__ import annotations
import argparse, json, pickle
from pathlib import Path
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
        tokens = word_tokenize(text, format="text").split()
    else:
        tokens = text.split()
    return [t for t in tokens if len(t) >= 2]


def load_chunks(json_path: Path) -> list[dict]:
    """Load chunks from extractor JSON, prefer khoản-level."""
    with open(json_path, encoding="utf-8") as f:
        data = json.load(f)

    chunks = data.get("chunks", [])

    # Separate khoản and dieu chunks
    khoan_chunks = [c for c in chunks if c.get("type") == "khoan"]
    dieu_chunks  = [c for c in chunks if c.get("type") == "dieu"]

    if khoan_chunks:
        print(f"    Using khoản-level: {len(khoan_chunks)} khoản + {len(dieu_chunks)} dieu fallbacks")
        return khoan_chunks + dieu_chunks  # khoản first for scoring
    else:
        print(f"    Using điều-level: {len(dieu_chunks)} chunks")
        return dieu_chunks


def build_index(json_path: str, law_id: str | None = None, output_dir: str = "indexer/indexes"):
    json_path = Path(json_path)
    out_dir   = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    chunks = load_chunks(json_path)
    if not chunks:
        print(f"  ❌ No chunks found in {json_path}")
        return

    # Infer law_id from JSON if not provided
    if not law_id:
        with open(json_path, encoding="utf-8") as f:
            meta = json.load(f)
        law_id = meta.get("document", {}).get("law_id") or json_path.stem

    print(f"  Building BM25 index for law_id='{law_id}' ({len(chunks)} chunks)...")

    # Tokenize
    corpus: list[list[str]] = []
    for c in chunks:
        text = c.get("text_for_bm25") or c.get("noi_dung", "")
        corpus.append(tokenize(text))

    bm25 = BM25Okapi(corpus, k1=1.5, b=0.75)

    # Save
    out_file = out_dir / f"bm25_{law_id}.pkl"
    with open(out_file, "wb") as f:
        pickle.dump({"bm25": bm25, "chunks": chunks, "law_id": law_id}, f)

    print(f"  ✅ Saved: {out_file} ({len(chunks)} chunks)")
    return out_file


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, help="Path to extractor JSON")
    parser.add_argument("--law-id", default=None, help="Law ID slug (auto-detect if not set)")
    parser.add_argument("--output-dir", default="indexer/indexes")
    args = parser.parse_args()

    build_index(args.input, args.law_id, args.output_dir)


if __name__ == "__main__":
    main()
