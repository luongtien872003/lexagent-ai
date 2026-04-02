import type { Conversation, Citation, ContentBlock, AnswerSection } from "@/lib/types";

// DEMO TELLS REMOVED:
//
// 1. Empty placeholder conversations (conv-5, conv-6, conv-7) — "Trợ cấp thôi việc",
//    "Đình công hợp pháp", "Bảo hiểm xã hội". These were pure filler. Clicking them
//    shows a blank chat. This is what demos do. Removed.
//
// 2. Seed conversations now include `structured: StructuredAnswer` on assistant
//    messages. Previously, ALL seed messages used the legacy ContentBlock[] format
//    with `structured: undefined`. This meant the StructuredAnswer component — the
//    entire point of the new UI — was NEVER rendered on initial page load. The user
//    had to send a message and get a backend response to see it. Unacceptable.

function makeCitation(
  id:    string,
  label: string,
  num:   string,
  color: Citation["color"],
): Citation {
  return { id, label, num, color };
}

const T = (text: string): ContentBlock => ({ type: "text", text });
const B = (text: string): ContentBlock => ({ type: "bold", text });
const P = (): ContentBlock              => ({ type: "break" });
const C = (citation: Citation): ContentBlock => ({ type: "cite", citation });

export const CITATIONS = {
  d38:  makeCitation("d38",  "Điều 38 — Quyền đơn phương chấm dứt HĐLĐ", "1", "amber"),
  d39:  makeCitation("d39",  "Điều 39 — Trường hợp không được đơn phương", "2", "green"),
  d155: makeCitation("d155", "Điều 155 — Bảo vệ thai sản lao động nữ",    "3", "blue"),
} as const;

const now = new Date();
const minutesAgo = (n: number) => new Date(now.getTime() - n * 60_000).toISOString();
const hoursAgo   = (n: number) => new Date(now.getTime() - n * 3_600_000).toISOString();
const daysAgo    = (n: number) => new Date(now.getTime() - n * 86_400_000).toISOString();

export const SEED_CONVERSATIONS: Conversation[] = [
  {
    id:        "conv-1",
    title:     "Điều kiện sa thải đơn phương",
    createdAt: minutesAgo(14),
    messages:  [
      {
        role: "user",
        id:   "u1",
        text: "Người sử dụng lao động có thể đơn phương sa thải nhân viên trong những trường hợp nào theo BLLĐ 2012? Và cần báo trước bao nhiêu ngày?",
      },
      {
        role:       "assistant",
        id:         "a1",
        // Legacy content blocks kept for ContentRenderer fallback
        content: [
          T("Người sử dụng lao động có thể đơn phương chấm dứt hợp đồng trong 3 nhóm trường hợp quy định tại "),
          C(CITATIONS.d38),
          T(". Thời hạn báo trước theo khoản 2: ít nhất 45 ngày (hợp đồng không thời hạn), 30 ngày (có thời hạn), hoặc 3 ngày làm việc (ốm đau/tai nạn). Cấm sa thải trong các trường hợp liệt kê tại "),
          C(CITATIONS.d39),
          T(", bao gồm lao động nữ mang thai — bảo vệ thêm tại "),
          C(CITATIONS.d155),
          T("."),
        ],
        citations: [CITATIONS.d38, CITATIONS.d39, CITATIONS.d155],
        // Structured answer — the component that was previously never shown
        structured: {
          summary: "Người sử dụng lao động có quyền đơn phương chấm dứt hợp đồng trong ba nhóm trường hợp theo Điều 38, với thời hạn báo trước từ 3 đến 45 ngày tùy loại hợp đồng.",
          sections: [
            {
              title:        "Các trường hợp được phép",
              bullets: [
                "Được phép khi người lao động thường xuyên không hoàn thành công việc",
                "Được phép khi người lao động ốm đau, điều trị 6–12 tháng liên tục tùy loại hợp đồng",
                "Được phép khi thiên tai, hỏa hoạn hoặc bất khả kháng buộc phải giảm chỗ làm việc",
              ],
              citation_ids: [38],
            },
            {
              title:        "Thời hạn báo trước bắt buộc",
              bullets: [
                "Phải báo trước ít nhất 45 ngày — hợp đồng không xác định thời hạn",
                "Phải báo trước ít nhất 30 ngày — hợp đồng xác định thời hạn",
                "Phải báo trước ít nhất 3 ngày làm việc — trường hợp ốm đau, tai nạn kéo dài",
              ],
              citation_ids: [38],
            },
            {
              title:        "Các trường hợp bị cấm",
              bullets: [
                "Không được sa thải lao động nữ mang thai, nghỉ thai sản hoặc nuôi con dưới 12 tháng",
                "Không được sa thải khi người lao động đang ốm đau, điều trị theo quyết định y tế",
                "Không được sa thải khi người lao động đang nghỉ hàng năm hoặc nghỉ được chấp thuận",
              ],
              citation_ids: [39, 155],
            },
          ],
        },
      },
      {
        role: "user",
        id:   "u2",
        text: "Nếu nhân viên đang mang thai thì sao?",
      },
      {
        role:       "assistant",
        id:         "a2",
        content: [
          T("Không được. Người sử dụng lao động không được sa thải lao động nữ đang mang thai — được bảo vệ bởi "),
          C(CITATIONS.d155),
          T(" và "),
          C(CITATIONS.d39),
          T(". Bảo vệ kéo dài đến khi con đủ 12 tháng tuổi. Vi phạm dẫn đến phải nhận lại người lao động và bồi thường ít nhất 2 tháng lương."),
        ],
        citations: [CITATIONS.d155, CITATIONS.d39],
        structured: {
          summary: "Tuyệt đối không được sa thải lao động nữ đang mang thai — bảo vệ kéo dài suốt thai kỳ, nghỉ thai sản và 12 tháng nuôi con.",
          sections: [
            {
              title:        "Phạm vi bảo vệ",
              bullets: [
                "Không được sa thải từ khi mang thai đến khi con đủ 12 tháng tuổi",
                "Không được đơn phương chấm dứt vì lý do kết hôn, mang thai hoặc nuôi con nhỏ",
                "Bảo vệ áp dụng với cả hợp đồng có thời hạn và không thời hạn",
              ],
              citation_ids: [155, 39],
            },
            {
              title:        "Hậu quả pháp lý khi vi phạm",
              bullets: [
                "Phải nhận lại người lao động và trả lương trong thời gian không được làm việc",
                "Phải bồi thường thêm ít nhất 2 tháng tiền lương",
                "Người lao động có quyền không quay lại và vẫn nhận bồi thường đầy đủ",
              ],
              citation_ids: [155],
            },
          ],
        },
      },
    ],
  },
  {
    id:        "conv-2",
    title:     "Chế độ thai sản và nghỉ phép",
    createdAt: hoursAgo(1),
    messages:  [
      {
        role: "user",
        id:   "u3",
        text: "Lao động nữ được nghỉ thai sản bao nhiêu tháng theo BLLĐ 2012?",
      },
      {
        role:       "assistant",
        id:         "a3",
        content: [
          T("Lao động nữ được nghỉ thai sản "),
          B("6 tháng"),
          T(" theo Điều 157 BLLĐ 2012. Nghỉ trước sinh tối đa 2 tháng. Sinh đôi trở lên: mỗi con từ con thứ hai cộng thêm 1 tháng. Trong thời gian nghỉ và 12 tháng sau sinh, "),
          C(CITATIONS.d155),
          T(" cấm sa thải."),
        ],
        citations: [CITATIONS.d155],
        structured: {
          summary: "Lao động nữ được nghỉ thai sản 6 tháng, trong đó nghỉ trước sinh tối đa 2 tháng. Sinh đôi trở lên được cộng thêm 1 tháng cho mỗi con từ con thứ hai.",
          sections: [
            {
              title:        "Thời gian nghỉ",
              bullets: [
                "Được nghỉ tổng cộng 6 tháng trước và sau khi sinh con",
                "Được nghỉ trước sinh tối đa 2 tháng trong tổng số 6 tháng",
                "Được cộng thêm 1 tháng cho mỗi con từ con thứ hai khi sinh đôi trở lên",
              ],
              citation_ids: [155],
            },
          ],
        },
      },
    ],
  },
  {
    id:        "conv-3",
    title:     "Hợp đồng thử việc tối đa",
    createdAt: hoursAgo(3),
    messages:  [
      {
        role: "user",
        id:   "u4",
        text: "Thời gian thử việc tối đa là bao lâu?",
      },
      {
        role:       "assistant",
        id:         "a4",
        content: [
          T("Điều 27 BLLĐ 2012: "),
          B("60 ngày"),
          T(" — trình độ cao đẳng trở lên; "),
          B("30 ngày"),
          T(" — trung cấp; "),
          B("6 ngày làm việc"),
          T(" — các công việc khác. Chỉ được thử việc một lần, không áp dụng với hợp đồng mùa vụ dưới 3 tháng."),
        ],
        citations: [],
        structured: {
          summary: "Thời gian thử việc tối đa từ 6 ngày đến 60 ngày tùy trình độ chuyên môn, và chỉ được áp dụng một lần cho mỗi công việc.",
          sections: [
            {
              title:        "Thời hạn theo trình độ",
              bullets: [
                "Tối đa 60 ngày — công việc yêu cầu cao đẳng, đại học trở lên",
                "Tối đa 30 ngày — công việc yêu cầu trình độ trung cấp",
                "Tối đa 6 ngày làm việc — các công việc còn lại",
              ],
              citation_ids: [],
            },
            {
              title:        "Giới hạn áp dụng",
              bullets: [
                "Chỉ được thỏa thuận thử việc một lần cho một công việc",
                "Không áp dụng với hợp đồng lao động mùa vụ dưới 3 tháng",
              ],
              citation_ids: [],
            },
          ],
        },
      },
    ],
  },
  {
    id:        "conv-4",
    title:     "Thời giờ làm thêm tối đa",
    createdAt: daysAgo(4),
    messages:  [
      {
        role: "user",
        id:   "u5",
        text: "Giới hạn làm thêm giờ hàng năm là bao nhiêu theo luật?",
      },
      {
        role:       "assistant",
        id:         "a5",
        content: [
          T("Điều 106 BLLĐ 2012: không quá "),
          B("50%"),
          T(" số giờ bình thường/ngày; không quá "),
          B("30 giờ/tháng"),
          T("; tổng không quá "),
          B("200 giờ/năm"),
          T(". Ngành đặc thù được phép tối đa 300 giờ/năm."),
        ],
        citations: [],
        structured: {
          summary: "Giới hạn làm thêm giờ là không quá 50% số giờ bình thường trong ngày, 30 giờ trong tháng và tổng 200 giờ trong năm.",
          sections: [
            {
              title:        "Giới hạn theo chu kỳ",
              bullets: [
                "Không được vượt quá 50% số giờ làm việc bình thường trong một ngày",
                "Không được vượt quá 30 giờ làm thêm trong một tháng",
                "Tổng cộng không được vượt quá 200 giờ trong một năm",
                "Áp dụng 300 giờ/năm cho một số ngành đặc thù theo quy định Chính phủ",
              ],
              citation_ids: [],
            },
          ],
        },
      },
    ],
  },
];
