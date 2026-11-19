# Nối mạch và chống lặp

Chỉ định hướng lại người nghe khi đổi diễn biến, thời gian, địa điểm hoặc tuyến kể.
Ranh giới event, unit hay batch không tự động là một diễn biến mới. Câu cùng
diễn biến được kể tiếp, không bắt buộc từ nối hoặc nhắc lại hoạt động trước.

`transition_contract.py` tách các chiều thời gian: thời đại, ngày tương đối,
buổi trong ngày. “Thế kỷ 21” và “ban ngày” không mâu thuẫn. Trạng thái cuối
hoạt động và trạng thái gần nhất của nhân vật ở tuyến đã rời được đưa vào
contract. Không tự suy ra đã hoàn thành hoặc đồng thời chỉ từ thứ tự cảnh.

Trước khi khóa hình/câu, `narration_novelty.py` gửi các fact đã xác nhận cho
model kiểm tra trùng nghĩa, theo nhóm 48 fact kèm 12 fact trước. Chỉ loại toàn
bộ fact khi kết quả xác nhận cùng một lần diễn ra và không thêm thông tin.
Backend kiểm tra thứ tự, khoảng nguồn, danh tính, loại bằng chứng và bối cảnh;
trùng một phần hoặc chưa rõ thì giữ. Lượt kiểm tra có checkpoint theo nội dung
và model, được tái sử dụng khi tiếp tục tác vụ. Đây là kiểm tra văn bản theo
fact, không phải kiểm chứng độc lập video gốc.

Sau đó bộ phân bổ hiện có chia lại đúng tổng số câu trên các fact còn lại.
Nguồn của fact bị bỏ không được chèn để bù thời lượng. Không đủ bằng chứng
thì báo `SENTENCE_EVIDENCE_SHORTAGE`, không hạ mục tiêu hoặc viết câu đệm.

Khi kiểm chứng lời kể cuối, model nhận ba cụm trước và tối đa ba cụm cũ có
nội dung tương tự để bắt lặp khác chữ. Cache phụ thuộc nội dung này, nên sửa
cụm trước sẽ kiểm tra lại cụm chịu ảnh hưởng. Câu trùng nguyên văn có cùng
bằng chứng bị backend bác bỏ trong pipeline câu đã khóa. Lỗi trùng nghĩa
được đưa vào cơ chế sửa có sẵn; lỗi chưa khắc phục bị chặn ở cổng xuất, kể cả
khi cho phép hình dự phòng. Không sửa riêng chuỗi lời kể sau khi đã khóa
bằng chứng vì sẽ làm lệch câu, hình và thời gian.

Giới hạn: phát hiện trùng nghĩa phụ thuộc model và phạm vi ngữ cảnh; không
khẳng định đã loại mọi trường hợp trùng. Bằng chứng quan sát sai vẫn cần xem
lại video. Thay đổi áp dụng cho lần phân tích mới, không tự sửa video đã xuất.
