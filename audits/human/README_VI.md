# Kiểm tra 60 item — cách đơn giản nhất (≈ 10–15 phút)

Mở **`D:\iclr2027\audits\human\label_simple.html`** (double-click, mở bằng Edge/Chrome).

Mỗi item: bên trái là **dải phóng to** đúng nhóm ô mà máy so sánh (một hàng hoặc một cột, thường 3–8 số),
ô đỏ = winner máy chọn, ô xanh = đối thủ máy chọn. Bên phải là 3 ý máy khẳng định:
① số đỏ đúng và in đậm duy nhất, ② số xanh đúng và tốt nhất trong số không đậm, ③ ± / số run đúng. Nhìn dải:

- đúng hết → bấm phím **1**
- sai bất kỳ điểm nào → bấm **2** (ghi chú sai gì vào ô ghi chú nếu tiện, không bắt buộc)
- không nhìn rõ → bấm **3**

Bấm số là tự sang item tiếp. 20 item đầu không có ± (chỉ cần nhìn hai ô), 40 item sau có ±
và số run (số run: xem caption bảng, hoặc hộp câu trích bên dưới, chữ liên quan đã bôi vàng).
Trang tự lưu, nghỉ giữa chừng được. Xong bấm **Xuất verify.csv** → lưu vào `D:\iclr2027\audits\human\`
rồi nhắn "xong".

Paper sẽ ghi đúng thiết kế này: một người kiểm tra cách đọc của máy trên 60 item đã biết
kết quả máy (verification, không phải chấm mù) — đây là kiểu kiểm tra được chấp nhận
khi khai báo rõ.

---
Hai trang khác trong thư mục, nếu muốn kỹ hơn (không bắt buộc):
- `label_quick.html`: máy điền sẵn từng ô, anh sửa ô nào sai (~20 phút).
- `label.html`: chấm mù từng ô, không thấy số máy (~1 giờ) — giá trị nhất, tốn nhất.

Tạo lại: `python study/human_verify_kit.py` (trang 1 câu), `python study/human_kit_html.py [--quick]` (hai trang kia).
Chấm điểm: `python study/human_verify_score.py` (verify.csv) hoặc `python study/gold_set.py score --labels audits/human/labels.csv ...`.
