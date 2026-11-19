# Danh tính và nhật ký kiểm chứng

Danh tính dùng ID `Pxx` xuyên suốt phim. ID `Cxx` hoặc `Pxx` do một clip trả về
được xử lý trong phạm vi clip đó; không dùng mã cục bộ để suy ra người ở clip khác.
Hồ sơ có `identity_group` (main/supporting), `entity_kind`
(person/animal/creature/unknown), tên hiển thị và nguồn đặt tên. Quan hệ gia đình
cần `relationship_evidence` có nội dung và shot nguồn; chưa đủ bằng chứng thì dùng
mô tả trung tính. Gemini được đề xuất mô tả, không được suy ra quan hệ hay loài.

Mỗi scene có `identity_contract`: người có mặt, người chỉ được lời thoại nhắc tới,
roster và fact/shot hỗ trợ. Việc cho phép nhắc một tên không chứng minh người đó
đang hành động trong hình; kiểm chứng nội dung vẫn phải đối chiếu mệnh đề đó.
Từ thông thường như “gian khổ”, “thời gian” không được tính là tên Gian.

Kết quả kiểm chứng gắn với scene, câu, facts, quan hệ chuyển cảnh, hợp đồng danh
tính và nguồn video. Sửa dữ liệu nào trong số đó thì kết quả cũ hết hiệu lực.
Sửa chọn lọc không được khôi phục câu lỗi cũ chỉ vì câu đó từng đạt kiểm chứng hình.
Checkpoint danh tính cũ được dựng lại từ phản hồi gốc đã lưu khi có thể.

Nhật ký đầy đủ nằm trong `logs/task_<task_id>.log`; nhật ký tác vụ trên giao diện
giữ bản rút gọn theo cơ chế hiện có. Dò theo scene_id và audit_id:

| Mã | Nội dung |
| --- | --- |
| `AUDIT_EVIDENCE_SENT` | Câu, facts và danh tính thực tế truyền vào verifier; chữ ký phiên bản |
| `AUDIT_TEXT_REQUEST` | Prompt thực tế của request text và request_id |
| `AUDIT_RESPONSE_RAW` | Phản hồi gốc của Gemini, cả text và video |
| `AUDIT_VERIFIER_RESPONSE` | Phản hồi đã parse trước khi backend xét ID/schema |
| `AUDIT_SCENE_DECISION` | Verdict, quyết định pass/reject/pending, phiên bản, facts, shot và phương pháp |
| `IDENTITY_SCENE_REJECTED` | Tên ngoài bằng chứng, tên cho phép, câu hiện tại, phiên bản và shot |

`AUDIT_SCENE_DECISION` còn có `source_window_seconds` và `review_url` khi scene có
khoảng shot hợp lệ. Mở URL đó trên địa chỉ tool để xem đúng đoạn nguồn trong trình duyệt.

`VERIFIER_FACT_CONFLICT` chỉ là dấu hiệu mâu thuẫn, không tự chứng minh lỗi code
hay cho câu đạt. Khi lý do bác cho rằng cụm từ được trích dẫn không có trong facts,
nhưng chính facts có cụm đó, tool xem lại đúng clip của scene. Nếu thiếu verdict
video thì giữ pending; nếu video bác thì đi vào luồng xem lại fact/sửa riêng có giới hạn.
Các lỗi nội dung khác vẫn bị bác theo kiểm chứng bình thường.

Test offline kiểm tra ánh xạ, cache, giới hạn danh tính, luồng mâu thuẫn và nhật ký.
Muốn kết luận một lời kể khớp video thực tế vẫn cần xem đoạn nguồn tương ứng.
