import type { Citation } from "@/lib/types";
import { CITATIONS } from "./conversations";

export interface SimulatedResponse {
  text:       string;
  extra?:     string;   // optional — omit rather than empty string
  citations:  Citation[];
}

/**
 * Keyword-matched response lookup.
 * Replace with a real SSE fetch to the FastAPI backend.
 */
export function getSimulatedResponse(query: string): SimulatedResponse {
  const q = query.toLowerCase();

  if (q.includes("thử việc")) {
    return {
      text:      "Theo Điều 27 BLLĐ 2012, thời gian thử việc tối đa: 60 ngày với công việc yêu cầu cao đẳng trở lên; 30 ngày với trung cấp; 6 ngày làm việc với công việc khác. Chỉ được thỏa thuận một lần.",
      extra:     "Không áp dụng với hợp đồng mùa vụ dưới 3 tháng.",
      citations: [{ id: "d36", label: "Điều 27 — Thử việc", num: "1", color: "amber" }],
    };
  }

  if (q.includes("làm thêm") || q.includes("overtime")) {
    return {
      text:      "Điều 106 BLLĐ 2012: không quá 50% số giờ làm việc bình thường trong một ngày; không quá 30 giờ/tháng; tổng không quá 200 giờ/năm. Một số ngành đặc thù tối đa 300 giờ/năm.",
      citations: [{ id: "d36", label: "Điều 106 — Giới hạn làm thêm", num: "1", color: "amber" }],
    };
  }

  if (q.includes("thai sản") || q.includes("mang thai")) {
    return {
      text:      "Lao động nữ được nghỉ thai sản 6 tháng (Điều 157). Nghỉ trước sinh tối đa 2 tháng. Sinh đôi trở lên mỗi con thêm từ con thứ hai được cộng 1 tháng. Trong thời gian này và 12 tháng sau sinh không được sa thải.",
      citations: [CITATIONS.d155, CITATIONS.d39],
    };
  }

  return {
    text:      "Câu hỏi của bạn liên quan đến nhiều quy định trong BLLĐ 2012. Vui lòng cung cấp thêm chi tiết về tình huống — loại hợp đồng, thời gian làm việc, và bên nào đang xem xét chấm dứt hợp đồng — để tôi tra cứu điều khoản chính xác nhất.",
    citations: [CITATIONS.d38],
  };
}
