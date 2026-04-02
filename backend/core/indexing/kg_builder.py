"""
Knowledge Graph Builder v2 — GPT-4o-mini
------------------------------------------
Improvements vs v1:
  1. Few-shot examples trong prompt → accuracy cao hơn
  2. Batch 3 điều/call → giảm 66% số API calls và chi phí
  3. Auto evaluation step → sample 20 triples, print để manual check

Chi phí thực tế:
  242 điều / 3 = ~81 API calls
  ~81 × 600 tokens input + 400 tokens output = ~81K tokens
  GPT-4o-mini: $0.15/1M input + $0.60/1M output
  → ~$0.012 + $0.020 = ~$0.032 tổng cộng

Chạy:
    python kg_builder.py --input ../extractor/output/10.2012.QH13.json --dry-run
    python kg_builder.py --input ../extractor/output/10.2012.QH13.json
"""

import os, json, time, argparse, random
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

try:
    from openai import OpenAI
except ImportError:
    raise SystemExit("Thiếu openai. Chạy: pip install openai")

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    raise SystemExit("Thiếu OPENAI_API_KEY trong .env")

INDEXES_DIR = Path(__file__).parent / "indexes"
INDEXES_DIR.mkdir(exist_ok=True)

MODEL        = "gpt-4o-mini"
BATCH_SIZE   = 3      # 3 điều/call — balance giữa cost và quality
RETRY_TIMES  = 3
RETRY_DELAY  = 2
EVAL_SAMPLES = 20     # số triple random sample để manual check

RELATION_TYPES = [
    "co_quyen",       # A có quyền làm B
    "co_nghia_vu",    # A có nghĩa vụ phải làm B
    "bi_cam",         # A bị cấm / không được làm B
    "dan_den",        # hành vi A dẫn đến hệ quả B
    "dieu_kien_de",   # A là điều kiện để B xảy ra
    "duoc_huong",     # A được nhận/hưởng B
    "ap_dung_cho",    # quy định A áp dụng cho đối tượng B
]

ENTITY_TYPES = ["chu_the", "hanh_vi", "quyen_loi", "dieu_kien", "hau_qua"]

# ── System prompt với few-shot examples ─────────────────────
SYSTEM_PROMPT = """Bạn là chuyên gia phân tích văn bản pháp luật lao động Việt Nam.
Nhiệm vụ: extract các quan hệ pháp lý từ điều luật thành triple có cấu trúc JSON.

ENTITY TYPES:
- chu_the: người lao động, người sử dụng lao động, nhà nước, công đoàn, người học nghề
- hanh_vi: hành động pháp lý (sa thải, đình công, chấm dứt hợp đồng, thử việc, kỷ luật...)
- quyen_loi: quyền lợi (trợ cấp, lương, nghỉ phép, bảo hiểm, thai sản...)
- dieu_kien: ràng buộc (thời hạn, số năm, tuổi, thời gian báo trước, tỷ lệ...)
- hau_qua: hệ quả pháp lý (bồi thường, vô hiệu hợp đồng, xử phạt...)

RELATION TYPES:
- co_quyen: chủ thể có quyền thực hiện
- co_nghia_vu: chủ thể có nghĩa vụ phải làm
- bi_cam: bị nghiêm cấm / không được phép
- dan_den: hành vi này dẫn đến hệ quả kia
- dieu_kien_de: điều kiện cần để thực hiện
- duoc_huong: được nhận quyền lợi
- ap_dung_cho: quy định áp dụng cho đối tượng nào

QUY TẮC BẮT BUỘC:
1. Chỉ extract quan hệ được nói RÕ RÀNG trong điều luật, KHÔNG suy diễn
2. subject và object: cụm từ ngắn gọn ≤8 từ, dùng tiếng Việt pháp lý chính thức
3. condition: điều kiện/ràng buộc kèm theo nếu có (ví dụ: "báo trước 30 ngày"), để "" nếu không có
4. negation: true nếu là điều CẤM hoặc KHÔNG ĐƯỢC
5. Mỗi điều extract 3-8 triples, ưu tiên quan hệ quan trọng nhất
6. Khi nhận NHIỀU điều cùng lúc, trả về object với key là số điều
7. Relation 'ap_dung_cho': subject LUÔN là văn bản/quy định, object là đối tượng áp dụng.
   Ví dụ ĐÚNG: Bộ luật --ap_dung_cho--> người lao động.
   SAI: người lao động --ap_dung_cho--> Bộ luật

--- FEW-SHOT EXAMPLES ---

INPUT:
Điều 37. Quyền đơn phương chấm dứt hợp đồng lao động của người lao động
Chương: HỢP ĐỒNG LAO ĐỘNG
Nội dung: Người lao động có quyền đơn phương chấm dứt hợp đồng lao động nhưng phải báo trước cho người sử dụng lao động biết trước ít nhất 30 ngày nếu là hợp đồng lao động xác định thời hạn; ít nhất 03 ngày làm việc nếu là hợp đồng lao động theo mùa vụ hoặc theo một công việc nhất định có thời hạn dưới 12 tháng. Người lao động bị ốm đau, tai nạn đã điều trị 06 tháng liên tục đối với người làm theo hợp đồng lao động xác định thời hạn và một phần tư thời hạn hợp đồng đối với người làm theo hợp đồng lao động theo mùa vụ thì có quyền đơn phương chấm dứt hợp đồng mà không cần báo trước.

OUTPUT cho Điều 37:
[
  {"subject": "người lao động", "subject_type": "chu_the", "relation": "co_quyen", "object": "đơn phương chấm dứt hợp đồng lao động", "object_type": "hanh_vi", "condition": "báo trước ít nhất 30 ngày (HĐXĐTH)", "negation": false},
  {"subject": "người lao động", "subject_type": "chu_the", "relation": "co_nghia_vu", "object": "báo trước người sử dụng lao động", "object_type": "hanh_vi", "condition": "khi đơn phương chấm dứt hợp đồng", "negation": false},
  {"subject": "người lao động bị ốm đau 6 tháng", "subject_type": "chu_the", "relation": "co_quyen", "object": "chấm dứt hợp đồng không cần báo trước", "object_type": "hanh_vi", "condition": "", "negation": false}
]

INPUT:
Điều 8. Các hành vi bị nghiêm cấm
Chương: NHỮNG QUY ĐỊNH CHUNG
Nội dung: Phân biệt đối xử về giới tính, dân tộc, màu da, thành phần xã hội, tình trạng hôn nhân, tín ngưỡng, tôn giáo, nhiễm HIV, khuyết tật hoặc vì lý do thành lập, gia nhập và hoạt động công đoàn. Ngược đãi người lao động, cưỡng bức lao động. Quấy rối tình dục tại nơi làm việc.

OUTPUT cho Điều 8:
[
  {"subject": "người sử dụng lao động", "subject_type": "chu_the", "relation": "bi_cam", "object": "phân biệt đối xử về giới tính, dân tộc", "object_type": "hanh_vi", "condition": "", "negation": true},
  {"subject": "người sử dụng lao động", "subject_type": "chu_the", "relation": "bi_cam", "object": "ngược đãi người lao động", "object_type": "hanh_vi", "condition": "", "negation": true},
  {"subject": "bất kỳ ai", "subject_type": "chu_the", "relation": "bi_cam", "object": "quấy rối tình dục tại nơi làm việc", "object_type": "hanh_vi", "condition": "", "negation": true}
]

--- END EXAMPLES ---

Khi nhận nhiều điều, trả về JSON object với format:
{
  "37": [...triples của Điều 37...],
  "38": [...triples của Điều 38...],
  "39": [...triples của Điều 39...]
}
KHÔNG có markdown, KHÔNG có giải thích."""


def format_batch(chunks: list[dict]) -> str:
    """Format 3 điều thành 1 prompt."""
    parts = []
    for c in chunks:
        body = c["noi_dung"][:800]  # giới hạn để tiết kiệm token
        parts.append(
            f"Điều {c['so_dieu']}. {c['ten_dieu']}\n"
            f"Chương: {c['ten_chuong']}\n"
            f"Nội dung: {body}"
        )
    return "\n\n---\n\n".join(parts)


def extract_batch(client: OpenAI, chunks: list[dict]) -> dict[int, list[dict]]:
    """
    Gọi GPT-4o-mini extract triples cho 1 batch (3 điều).
    Returns: {so_dieu: [triples]}
    """
    prompt = format_batch(chunks)

    for attempt in range(RETRY_TIMES):
        try:
            resp = client.chat.completions.create(
                model=MODEL,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user",   "content": prompt},
                ],
                temperature=0.0,
                max_tokens=1200,
                response_format={"type": "json_object"},
            )
            raw = resp.choices[0].message.content.strip()
            parsed = json.loads(raw)

            results: dict[int, list[dict]] = {}
            for chunk in chunks:
                key     = str(chunk["so_dieu"])
                triples = parsed.get(key, [])
                if isinstance(triples, list):
                    valid = []
                    for t in triples:
                        if not all(k in t for k in ["subject", "relation", "object"]):
                            continue
                        if t["relation"] not in RELATION_TYPES:
                            continue
                        t.setdefault("subject_type", "chu_the")
                        t.setdefault("object_type",  "hanh_vi")
                        t.setdefault("condition",    "")
                        t.setdefault("negation",     False)
                        # Metadata
                        t["dieu_so"]   = chunk["so_dieu"]
                        t["dieu_id"]   = chunk["id"]
                        t["chuong_so"] = chunk["chuong_so"]
                        t["van_ban_id"] = chunk["van_ban_id"]
                        valid.append(t)
                    results[chunk["so_dieu"]] = valid
                else:
                    results[chunk["so_dieu"]] = []

            return results

        except json.JSONDecodeError as e:
            print(f"  [WARN] JSON error batch {[c['so_dieu'] for c in chunks]}: {e}")
            if attempt < RETRY_TIMES - 1:
                time.sleep(RETRY_DELAY)
        except Exception as e:
            print(f"  [WARN] API error attempt {attempt+1}: {e}")
            if attempt < RETRY_TIMES - 1:
                time.sleep(RETRY_DELAY * (attempt + 1))

    return {c["so_dieu"]: [] for c in chunks}


def evaluate_sample(all_triples: list[dict], n: int = EVAL_SAMPLES):
    """In sample triples để manual check precision."""
    print(f"\n{'='*65}")
    print(f"EVALUATION SAMPLE — {n} triples ngẫu nhiên (manual check)")
    print(f"{'='*65}")
    sample = random.sample(all_triples, min(n, len(all_triples)))

    correct = 0
    for i, t in enumerate(sample, 1):
        neg  = " [CẤM]" if t.get("negation") else ""
        cond = f" | if: {t['condition']}" if t.get("condition") else ""
        print(f"\n[{i:2d}] Điều {t['dieu_so']} — {t.get('dieu_id','')}")
        print(f"     {t['subject']} --{t['relation']}--> {t['object']}{neg}{cond}")

    print(f"\n{'='*65}")
    print(f"Đếm bao nhiêu triple đúng trong {n} sample trên")
    print(f"→ KG Precision ≈ đúng/{n} × 100%")
    print(f"{'='*65}")


def build_kg(json_path: str, dry_run: bool = False) -> dict:
    json_path = Path(json_path)
    with open(json_path, encoding="utf-8") as f:
        data = json.load(f)

    doc    = data["document"]
    chunks = [c for c in data["chunks"] if c["type"] == "dieu"]

    if dry_run:
        chunks = chunks[:6]  # 6 điều = 2 batches
        print(f"[KG] DRY RUN — {len(chunks)} điều ({len(chunks)//BATCH_SIZE} batches)")
    else:
        n_batches = (len(chunks) + BATCH_SIZE - 1) // BATCH_SIZE
        print(f"[KG] {len(chunks)} điều → {n_batches} batches (batch_size={BATCH_SIZE})")
        print(f"[KG] Model: {MODEL} | Est. cost: ~$0.03-0.05")

    client      = OpenAI(api_key=OPENAI_API_KEY)
    all_triples = []
    entity_index: dict[str, list[int]] = {}
    errors      = 0
    t0          = time.time()

    # Chia thành batches
    batches = [chunks[i:i+BATCH_SIZE] for i in range(0, len(chunks), BATCH_SIZE)]

    for bi, batch in enumerate(batches):
        batch_result = extract_batch(client, batch)

        batch_triples = 0
        for chunk in batch:
            triples = batch_result.get(chunk["so_dieu"], [])
            if triples:
                all_triples.extend(triples)
                batch_triples += len(triples)
                # Build entity index
                for t in triples:
                    for field in ("subject", "object"):
                        ent = t[field].lower().strip()
                        entity_index.setdefault(ent, [])
                        if chunk["so_dieu"] not in entity_index[ent]:
                            entity_index[ent].append(chunk["so_dieu"])
            else:
                errors += 1

        elapsed = time.time() - t0
        avg     = elapsed / (bi + 1)
        remain  = avg * (len(batches) - bi - 1)
        dieu_list = [c["so_dieu"] for c in batch]
        print(f"  Batch [{bi+1:3d}/{len(batches)}] Điều {dieu_list} "
              f"→ {batch_triples} triples | total={len(all_triples)} | ETA {remain/60:.1f}min")

        # Rate limit safety
        time.sleep(0.5)

    elapsed_total = time.time() - t0

    # Cost estimate
    n_calls = len(batches)
    est_input  = n_calls * 600
    est_output = len(all_triples) * 35
    est_cost   = est_input / 1e6 * 0.15 + est_output / 1e6 * 0.60

    print(f"\n[KG] Done in {elapsed_total/60:.1f}min | "
          f"triples={len(all_triples)} | errors={errors} | "
          f"entities={len(entity_index)} | est_cost=~${est_cost:.3f}")

    kg = {
        "van_ban_id":    doc["id"],
        "so_hieu":       doc["so_hieu"],
        "ten_van_ban":   doc["ten_van_ban"],
        "model":         MODEL,
        "batch_size":    BATCH_SIZE,
        "total_triples": len(all_triples),
        "triples":       all_triples,
        "entity_index":  entity_index,
    }

    suffix   = "_dryrun" if dry_run else ""
    out_path = INDEXES_DIR / f"kg_{doc['id']}{suffix}.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(kg, f, ensure_ascii=False, indent=2)
    print(f"[KG] Saved → {out_path}")

    # Evaluation sample
    if all_triples:
        evaluate_sample(all_triples, n=min(EVAL_SAMPLES, len(all_triples)))

    return kg


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--input",   required=True)
    parser.add_argument("--dry-run", action="store_true",
                        help="Test 6 điều đầu (~2 batches) trước khi chạy full")
    args = parser.parse_args()
    build_kg(args.input, dry_run=args.dry_run)
