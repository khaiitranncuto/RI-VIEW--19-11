# Kho bằng chứng và retry lời kể

- Giữ video nguồn, SHOT ID và checkpoint; không tạo hàng nghìn ảnh riêng.
- Sau lượt trích chính, kiểm kê fact/shot và xem bù tối đa ba cửa sổ
  60 giây có sự kiện nhưng thưa dữ kiện nếu chưa đủ mục tiêu.
- Dùng lại hàm xem clip 2 FPS và cache phản hồi đã có. Chỉ nhận dữ kiện
  mới có nguồn; không bảo đảm mọi khung hình đều chứa sự kiện mới.
- Kế hoạch tình huống dùng số fact hợp lệ làm giới hạn số đơn vị kể.
  Nếu sau xem bù vẫn thiếu, ghi requested/effective budget và hạ quota
  thay vì ép lặp lời kể. Đây là ước tính, chưa phải thời lượng TTS thực.
- Chia facts cho các đơn vị kể khác nhau; vẫn cho phép chung hình nguồn.
- Một bản đầu và tối đa ba lượt sửa có mục tiêu. Giữ bản tốt nhất với
  ưu tiên lỗi nhân vật/nội dung trước lỗi hình, rồi lặp ý và độ dài.
- Hình fallback vẫn chưa xác minh và có nhật ký. Timestamp/nguồn hỏng
  hoặc video mất vẫn là lỗi bắt buộc xử lý trước khi render.
- Vùng xem bù thưa fact là heuristic: có thể là cảnh dài ít diễn biến;
  không tạo facts hoặc khẳng định đủ thời lượng chỉ để đạt ngân sách.
