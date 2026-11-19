# Cách đọc tên cho Ngọc Huyền

`pronunciation_overrides.json` lưu cách đọc riêng, áp dụng chung cho nghe thử và xuất video. Thêm tên mới hoặc sửa phiên âm rồi lưu file, không cần sửa kịch bản. Ví dụ:

```json
{
  "Shizuka": "si du ca",
  "Harry Potter": "ha ri pót tơ"
}
```

Ưu tiên cụm tên dài nhất, khớp trọn từ, không phân biệt chữ hoa. Tên và phụ đề gốc được giữ qua bảng ánh xạ thời gian. Thay bảng cách đọc tự làm mới khóa cache giọng Ngọc Huyền.

Tên Latin chưa có trong bảng và không được bộ phân tích hỗ trợ sẽ được phiên âm bằng quy tắc gần âm; log ghi tên chưa nghe duyệt. Đây là cách đọc ước lượng theo chữ viết, không xác định được trọng âm/ngôn ngữ gốc và không bảo đảm phát âm chuẩn tiếng Anh. Nghe thử tên mới rồi thêm cách đọc phù hợp vào bảng. Từ vốn được bộ phân tích chấp nhận không tự bị đổi để tránh sửa nhầm tiếng Việt; muốn điều khiển cách đọc những tên như vậy, thêm tên vào bảng.

Cách đọc tùy chỉnh không hợp lệ hoặc chữ viết chưa hỗ trợ sẽ báo lỗi, không đổi thành “tên riêng” hoặc âm A. Phiên âm cần gồm các âm tiết tiếng Việt mà model hỗ trợ. Cơ chế này chỉ xử lý giọng đọc, không quyết định nhân vật chính/phụ hay đổi tên nhân vật trong kịch bản.

Kiểm tra: `local_tts\venv\Scripts\python.exe -m unittest tests.test_local_pronunciation`.
