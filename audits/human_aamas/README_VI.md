# Hai việc gán nhãn tay cho bài AAMAS (tổng ~1–1,5 giờ)

> Bổ sung (vòng phản biện AAMAS 2027): các bộ kiểm tra **mù** mới (A: 140 so sánh tham chiếu,
> B: 30 trang ngẫu nhiên, C3: 18 run count tranh chấp, C4: loại thanh sai số) mô tả trong
> `README.md` (tiếng Anh). Trang `empty_pages/label.html` ở mục B dưới đây đã được làm lại: nhập
> mã người gán nhãn trước, tự lưu trong trình duyệt, có link mở PDF; cột CSV vẫn như cũ.

Sáu vòng phản biện đều nói cùng một điều: bài chưa có một nhãn nào do **người** gán.
Hai việc dưới đây là hai chỗ phản biện chỉ đích danh; xong việc nào thì chạy
`python aamas/human_score.py` rồi `sh run_all_aamas.sh`, số sẽ tự vào bảng.

## A. Kiểm tra cách đánh giá của 20 bài có "win/success rate" (~45–60 phút)

File: `audits/human_aamas/protocol_check.csv` (mở bằng Excel/LibreOffice, giữ định dạng CSV UTF-8 khi lưu).

Mỗi dòng là một bài; cột `pdf` là đường dẫn PDF trong `D:\iclr2027\`. Máy đã đọc sẵn
(`model_K`, `model_seeds`, `model_kind`, kèm câu trích dẫn). Việc của anh: mở PDF, tìm
phần thí nghiệm, điền 5 cột `human_*`:

| cột | điền gì |
|---|---|
| `human_K` | số **episode/rollout/ván/instance** mà một tỉ lệ (win rate, success rate) được tính trung bình trên đó, mỗi seed. Nếu bài không nói: `none`. Nếu máy đọc đúng: `same`. |
| `human_seeds` | số seed / số lần chạy độc lập. `none` nếu không nói, `same` nếu máy đúng. |
| `human_kind` | `sampled` (episode ngẫu nhiên, mỗi phương pháp gặp mẫu khác nhau) hoặc `fixed_instances` (một bộ đề/instance cố định, mỗi phương pháp chạy đúng bộ đó). `same` nếu máy đúng. |
| `human_shares_instances` | `yes` nếu các phương pháp được đánh giá trên **cùng** episode/instance/seed; `no` nếu độc lập; `unsure`. |
| `human_sd_over` | dấu ± trong bảng là độ lệch **qua seed** (`seeds`), **qua episode gộp** (`episodes`), sai số chuẩn (`se`), khoảng tin cậy (`ci`), hay không nói (`unsure`). |

`human_note`: ghi câu trong bài nếu anh sửa số của máy (không bắt buộc).
8 bài đầu (có `model_K`) quan trọng nhất — làm 8 bài đó trước cũng đã đủ cho một dòng trong Bảng 5.

## B. 35 trang máy đọc là "không có nhóm" (~20–30 phút)

Mở `audits/human_aamas/empty_pages/label.html` bằng trình duyệt. Mỗi trang một câu hỏi:
trang này có bảng kết quả nào mà **mỗi hàng (hoặc mỗi cột) có đúng một ô in đậm** không?

- **yes**: có ít nhất một bảng như vậy (bảng chia khối, mỗi khối một ô đậm mỗi cột, vẫn là yes). Ghi số hàng/cột như vậy vào ô `groups` (ước lượng được).
- **no**: mọi bảng đều có nhiều ô đậm trên một dòng, hoặc in đậm cả hàng của phương pháp tác giả, hoặc không phải bảng kết quả.
- **unclear**: không nhìn ra.

Bấm **Save labels** ở cuối trang → file `empty_pages_labels.csv` tải về; chép vào
`audits/human_aamas/empty_pages_labels.csv`.

5 trang đầu (`pilot_empty`) là 5 trang hai máy đọc khác nhau hoàn toàn; 30 trang sau là
mẫu ngẫu nhiên. Anh nhìn nhầm vài trang cũng không sao: kết quả được báo cáo là
"người đồng ý với máy X/35", không phải chân lý.

Sau khi có nhãn, em sẽ thêm hai dòng vào Bảng 5 (người–máy) và sửa Mục 6, 7 theo số thật.
