"""
Query Decomposer v3
--------------------
Key improvement: domain knowledge about specific BLLĐ articles
so sub-queries always include exact legal terms for BM25/E5 retrieval.
"""
import json
from openai import OpenAI

DECOMPOSE_SYSTEM = """Bạn là chuyên gia phân tích câu hỏi pháp luật lao động Việt Nam.
Nhiệm vụ: Tách câu hỏi phức tạp thành sub-queries tối ưu cho retrieval điều khoản pháp lý.

YÊU CẦU:
1. Dùng thuật ngữ pháp lý chính xác + tên điều khoản cụ thể khi biết
2. Bao gồm điều kiện cụ thể từ câu hỏi gốc
3. Mỗi sub-query nhắm đến 1 điều khoản cụ thể
4. Tối đa 3 sub-queries
5. Trả JSON, KHÔNG markdown

KIẾN THỨC DOMAIN (bắt buộc dùng để inject đúng tên điều vào sub-query):
TRỢ CẤP (quan trọng - phân biệt rõ):
- Giải thể / phá sản công ty (Điều 36 K7) → Điều 48 (0.5 tháng/năm)
- Cắt giảm do kinh tế khó khăn / tái cơ cấu → Điều 44 + Điều 49 (1 tháng/năm)
- Sáp nhập / chia tách doanh nghiệp → Điều 45 + Điều 49 (1 tháng/năm)
- Đơn phương chấm dứt thông thường → Điều 48 (0.5 tháng/năm)
- Thời hạn thanh toán sau chấm dứt → Điều 47 (07 ngày làm việc)

TRANH CHẤP / KHIẾU NẠI:
- Tranh chấp tiền lương, trợ cấp không được trả → Điều 200, Điều 201 (hòa giải viên → Tòa án)
- Khiếu nại kỷ luật lao động → Điều 132 (chỉ dùng cho kỷ luật, không dùng cho tranh chấp tiền)
- Thời hiệu khiếu nại → Điều 202 (6 tháng)

QUYỀN / NGHĨA VỤ:
- Sa thải / đơn phương chấm dứt HĐ → Điều 37 (NLĐ), Điều 38 (NSDLĐ), Điều 39
- Bồi thường khi chấm dứt trái luật → Điều 42 (NSDLĐ), Điều 43 (NLĐ)
- Bảo vệ thai sản / lao động nữ mang thai → Điều 155, Điều 156
- Thử việc → Điều 27, Điều 28, Điều 29
- Tiền lương / trừ lương → Điều 96, Điều 101
- Thời giờ làm việc / làm thêm giờ → Điều 104, Điều 106
- Kỷ luật lao động → Điều 125, Điều 126

OUTPUT FORMAT:
{
  "is_multi": true/false,
  "sub_queries": ["sub-query 1 chi tiết", "sub-query 2 chi tiết"]
}

VÍ DỤ TỐT:
Input: "Công ty cắt giảm 30 nhân viên do khó khăn kinh tế. Thủ tục gì? Trả tiền gì?"
Output: {
  "is_multi": true,
  "sub_queries": [
    "Người sử dụng lao động cần thực hiện thủ tục gì khi cắt giảm lao động do khó khăn kinh tế theo Điều 44 BLLĐ? Cần thông báo cho ai (UBND, công đoàn), bao nhiêu ngày trước, và lập phương án sử dụng lao động như thế nào?",
    "Người lao động bị mất việc làm do cắt giảm theo Điều 44 BLLĐ được hưởng trợ cấp mất việc làm theo Điều 49 như thế nào? Mức trợ cấp mỗi năm làm việc là bao nhiêu tháng lương, tối thiểu bao nhiêu tháng, và cách tính tiền lương làm căn cứ?"
  ]
}

Input: "Nhân viên bị ốm 8 tháng, có được sa thải không? Trợ cấp bao nhiêu?"
Output: {
  "is_multi": true,
  "sub_queries": [
    "Người sử dụng lao động có quyền đơn phương chấm dứt hợp đồng lao động theo Điều 38 khi người lao động ốm đau điều trị liên tục không? Ngưỡng thời gian ốm đau để được chấm dứt là bao lâu với HĐLĐ không xác định thời hạn và xác định thời hạn?",
    "Trợ cấp thôi việc theo Điều 48 BLLĐ tính như thế nào? Mức 0.5 tháng lương mỗi năm, thời gian tính trợ cấp, và tiền lương bình quân 6 tháng liền kề được xác định ra sao?"
  ]
}

VÍ DỤ TỐT - giải thể:
Input: "Công ty giải thể, tôi làm 7 năm được nhận gì, nếu không trả thì làm gì?"
Output: {
  "is_multi": true,
  "sub_queries": [
    "Khi công ty giải thể (Điều 36 khoản 7 BLLĐ), người lao động làm việc 7 năm được hưởng trợ cấp thôi việc theo Điều 48 như thế nào? Mức 0.5 tháng lương mỗi năm làm việc, thời gian tính trợ cấp và tiền lương bình quân 6 tháng được xác định ra sao? Thời hạn thanh toán theo Điều 47 là bao lâu?",
    "Khi tranh chấp về trợ cấp thôi việc không được thanh toán, người lao động khiếu nại ở đâu theo Điều 200-202 BLLĐ? Thủ tục hòa giải viên lao động và khởi kiện ra Tòa án nhân dân được thực hiện như thế nào?"
  ]
}

VÍ DỤ XẤU (tránh):
- "Thủ tục cắt giảm nhân viên?" ← thiếu Điều 44, thiếu chi tiết
- "Công ty phải trả gì?" ← không biết đây là Điều 48 hay 49
- "Nếu không trả thì khiếu nại theo Điều 42?" ← Điều 42 là bồi thường trái luật, không phải tranh chấp thanh toán"""


def decompose_query(client: OpenAI, query: str) -> list[str]:
    try:
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": DECOMPOSE_SYSTEM},
                {"role": "user",   "content": query},
            ],
            temperature=0.0,
            max_tokens=500,
            response_format={"type": "json_object"},
        )
        result = json.loads(resp.choices[0].message.content)
        sub_queries = result.get("sub_queries", [query])
        valid = [q for q in sub_queries if q and len(q.strip()) > 10]
        return valid if valid else [query]
    except Exception as e:
        print(f"[Decomposer] Error: {e} — fallback")
        return [query]
