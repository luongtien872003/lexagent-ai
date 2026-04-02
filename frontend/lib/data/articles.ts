import type { DieuRecord } from "@/lib/types";

/**
 * Flat lookup table of legal articles (BLLĐ 10/2012/QH13).
 * Key is the article ID (e.g. "d38").
 */
export const DIEU_DB: Record<string, DieuRecord> = {
  d38: {
    id:     "d38",
    num:    "Điều 38",
    title:  "Quyền đơn phương chấm dứt hợp đồng lao động của người sử dụng lao động",
    chuong: "Chương IV",
    khoans: [
      {
        num:  "Khoản 1",
        text: "Người sử dụng lao động có quyền đơn phương chấm dứt hợp đồng lao động trong những trường hợp sau: người lao động thường xuyên không hoàn thành công việc; bị ốm đau, tai nạn đã điều trị 12 tháng liên tục (hợp đồng không xác định thời hạn) hoặc 06 tháng (hợp đồng xác định thời hạn) mà khả năng lao động chưa hồi phục; thiên tai, hỏa hoạn hoặc lý do bất khả kháng mà người sử dụng lao động đã tìm mọi biện pháp khắc phục nhưng vẫn buộc phải giảm chỗ làm việc.",
      },
      {
        num:  "Khoản 2",
        text: "Khi đơn phương chấm dứt hợp đồng, người sử dụng lao động phải báo trước: ít nhất 45 ngày với hợp đồng không xác định thời hạn; ít nhất 30 ngày với hợp đồng xác định thời hạn; ít nhất 03 ngày làm việc đối với trường hợp ốm đau, tai nạn kéo dài.",
      },
      {
        num:  "Khoản 3",
        text: "Người sử dụng lao động không được đơn phương chấm dứt hợp đồng khi người lao động đang ốm đau hoặc bị tai nạn lao động, bệnh nghề nghiệp đang điều trị theo quyết định của cơ sở khám, chữa bệnh có thẩm quyền, trừ trường hợp quy định tại điểm b và c khoản 1 Điều này.",
      },
    ],
    related: ["d36", "d37", "d39", "d41"],
  },

  d39: {
    id:     "d39",
    num:    "Điều 39",
    title:  "Trường hợp người sử dụng lao động không được thực hiện quyền đơn phương chấm dứt hợp đồng",
    chuong: "Chương IV",
    khoans: [
      {
        num:  "Khoản 1",
        text: "Người lao động ốm đau hoặc bị tai nạn lao động, bệnh nghề nghiệp đang điều trị, điều dưỡng theo quyết định của cơ sở khám bệnh, chữa bệnh có thẩm quyền.",
      },
      {
        num:  "Khoản 2",
        text: "Người lao động đang nghỉ hàng năm, nghỉ về việc riêng và những trường hợp nghỉ khác được người sử dụng lao động đồng ý.",
      },
      {
        num:  "Khoản 3",
        text: "Lao động nữ vì lý do kết hôn, mang thai, nghỉ thai sản, nuôi con dưới 12 tháng tuổi.",
      },
    ],
    related: ["d38", "d155", "d37", "d41"],
  },

  d155: {
    id:     "d155",
    num:    "Điều 155",
    title:  "Bảo vệ thai sản đối với lao động nữ",
    chuong: "Chương X",
    khoans: [
      {
        num:  "Khoản 1",
        text: "Người sử dụng lao động không được sử dụng lao động nữ làm việc ban đêm, làm thêm giờ và đi công tác xa trong trường hợp mang thai từ tháng thứ 07 (hoặc tháng thứ 06 nếu làm việc ở vùng cao, vùng sâu, biên giới, hải đảo) hoặc đang nuôi con dưới 12 tháng tuổi.",
      },
      {
        num:  "Khoản 3",
        text: "Người sử dụng lao động không được sa thải hoặc đơn phương chấm dứt hợp đồng đối với lao động nữ vì lý do kết hôn, mang thai, nghỉ thai sản, nuôi con dưới 12 tháng tuổi, trừ trường hợp người sử dụng lao động là cá nhân chết hoặc bị Tòa án tuyên bố mất năng lực hành vi dân sự, mất tích hoặc đã chết.",
      },
    ],
    related: ["d39", "d157", "d38", "d161"],
  },

  d36: {
    id:     "d36",
    num:    "Điều 36",
    title:  "Các trường hợp chấm dứt hợp đồng lao động",
    chuong: "Chương IV",
    khoans: [
      {
        num:  "Điểm a",
        text: "Hết hạn hợp đồng lao động, trừ trường hợp quy định tại khoản 6 Điều 192 của Bộ luật này.",
      },
      {
        num:  "Điểm c",
        text: "Hai bên thoả thuận chấm dứt hợp đồng lao động.",
      },
      {
        num:  "Điểm g",
        text: "Người sử dụng lao động đơn phương chấm dứt hợp đồng theo quy định tại Điều 38; hoặc cho người lao động thôi việc do thay đổi cơ cấu, công nghệ, lý do kinh tế hoặc do sáp nhật, hợp nhất, chia tách doanh nghiệp.",
      },
    ],
    related: ["d38", "d41", "d42", "d43"],
  },
};
