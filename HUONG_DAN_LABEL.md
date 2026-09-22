# Hướng dẫn gán nhãn (việc còn lại để nộp bài SWEVO)

Bài báo đã hoàn chỉnh, chỉ còn **một việc phải do người làm**: kiểm tra bằng mắt
xem máy đọc bảng có đúng không. Có 3 phần, tổng khoảng **10–12 giờ**, làm rải ra
được, không cần cài gì cả.

| Phần | File cần mở | Số mục | Thời gian |
|---|---|---|---|
| 1 | `audits/swevo_human/label.html` | 100 | ~4–5 giờ |
| 2 | `audits/swevo_human_rows/label.html` | 100 | ~4–5 giờ |
| 3 | `audits/swevo_markers/adjudicate.csv` | 17 bài | ~1,5 giờ |

**Quy tắc chung:** chỉ nhìn **ảnh trang giấy** rồi ghi lại đúng như in. Không mở
các file `labels_claude-sonnet-5.csv` (đó là câu trả lời của máy, xem trước sẽ
làm hỏng phép đo). Không cần suy luận, không cần sửa lỗi của tác giả — chỉ ghi
những gì trang giấy in ra.

---

## Phần 1 — `audits/swevo_human/label.html` (bảng có cột Mean và cột Std riêng)

1. Mở file bằng Chrome hoặc Edge (nháy đúp là được). Trang rất dài: 100 mục, mỗi
   mục có một ảnh trang giấy phía dưới.
2. Mỗi mục cho biết: **caption** (đầu chú thích bảng), **group label** (tên
   hàng hoặc cột cần xem), **direction** (lower = giá trị nhỏ tốt hơn, higher =
   lớn tốt hơn), và các câu trong bài nói về số lần chạy (run sentences).
3. Tìm bảng có caption đó trên ảnh, tìm hàng/cột có nhãn đó. Ô **in đậm** trong
   hàng/cột ấy là "winner". Ô tốt nhất **không in đậm** trong cùng hàng/cột (theo
   direction) là "runner".
4. Điền các ô:

| Ô | Ghi gì |
|---|---|
| `results_table` | `y` nếu là bảng kết quả thí nghiệm; `n` nếu là bảng tham số, ký hiệu, v.v. |
| `bold_ok` | `y` nếu hàng/cột đó có **đúng một** ô in đậm; `n` nếu không có, hoặc có nhiều hơn một, hoặc ô đậm là ô Std |
| `whole_row_bold` | `y` nếu **mọi** ô in đậm của cả bảng nằm trên **một hàng** (hoặc một cột) — kiểu tô đậm cả hàng của thuật toán đề xuất; `n` nếu bold đánh dấu từng ô tốt nhất |
| `winner_mean` | giá trị ô in đậm, chép **y nguyên** (kể cả dạng `1.23E-05`) |
| `winner_disp` | độ lệch chuẩn (Std/SD) thuộc về ô đậm đó — lấy ở cột Std hoặc hàng Std của **cùng thuật toán, cùng hàm**; nếu không in thì ghi `none` |
| `runner_mean` | giá trị ô tốt nhất không in đậm trong cùng nhóm |
| `runner_disp` | độ lệch chuẩn của ô runner; `none` nếu không có |
| `n_runs` | số lần chạy độc lập áp dụng cho bảng này (tìm trong caption, trên trang, hoặc trong run sentences); `none` nếu không đâu nói |
| `note` | ghi chú ngắn nếu có gì lạ (không bắt buộc) |

   Chữ số nào **không đọc được** thì ghi `unclear`.
5. Trang tự lưu vào trình duyệt khi gõ (góc phải trên có đếm "Items with an
   answer"). Có thể đóng máy, mở lại file sau, câu trả lời vẫn còn (miễn là cùng
   trình duyệt, cùng máy).
6. Làm xong (hoặc cuối mỗi buổi) bấm nút **Save labels** ở cuối trang → trình
   duyệt tải về file `labels.csv`. Chép file này vào đúng thư mục:
   `audits/swevo_human/labels.csv` (ghi đè bản cũ nếu có).
   Nếu đổi máy: mở file html, dùng ô **Load a saved labels.csv** ở góc phải để
   nạp lại rồi làm tiếp.

## Phần 2 — `audits/swevo_human_rows/label.html` (bảng có hàng Mean và hàng Std)

Giống hệt Phần 1, thêm một ô:

| Ô | Ghi gì |
|---|---|
| `std_printed` | `y` nếu **có** in độ lệch chuẩn cho ô đậm ở **bất kỳ đâu trong bảng** (trong ô, ở hàng Std bên dưới, hoặc cột Std bên cạnh); `n` nếu bảng chỉ có mean |

Nếu `std_printed` = `n` thì `winner_disp` và `runner_disp` đều ghi `none`.
Lưu thành `audits/swevo_human_rows/labels.csv`.

## Phần 3 — `audits/swevo_markers/adjudicate.csv` (17 bài, hai máy đọc bất đồng)

Mở file bằng Excel/LibreOffice. Với mỗi dòng:

1. Mở bài báo theo cột `url` (bài open access trên nature.com).
2. Câu hỏi duy nhất: **bài có in "verdict" từng ô không?** — tức là bên cạnh
   từng kết quả có ký hiệu `+ / = / −`, hoặc đếm `w/t/l` (win/tie/loss), hoặc
   một giá trị p (hay h) **cho từng hàm**. (Chỉ có một bảng Friedman rank tổng
   hợp hoặc một câu "p < 0.05" chung chung thì **không** tính.)
3. Điền `markers_human` = `y` hoặc `n`; `sentence_human` = chép một câu/chú
   thích bảng làm bằng chứng (ví dụ: "+/=/− denote…", "Table 5: p-values of the
   Wilcoxon test for each function"). Cột `first_sentence`, `second_sentence` là
   gợi ý của hai máy — được phép xem, nhưng quyết định theo bài báo.
4. Lưu lại đúng file đó (giữ nguyên tên, định dạng CSV, mã UTF-8).

---

## Gửi lại

Gửi lại 3 file (hoặc commit rồi push lên repo này):

```
audits/swevo_human/labels.csv
audits/swevo_human_rows/labels.csv
audits/swevo_markers/adjudicate.csv
```

Phần còn lại (chấm điểm, tạo lại số liệu, sửa câu chữ trong bài) là tự động:
`sh run_all_swevo.sh` rồi `python swevo/check_swevo.py`.

**Lưu ý trung thực:** kết quả thế nào thì bài in thế ấy. Nếu máy đọc sai nhiều,
bài sẽ nói máy đọc sai nhiều và điều chỉnh khoảng tin cậy — không được "sửa"
nhãn cho khớp với máy.

---

## In short (English)

Three tasks remain, all for a person, ~10–12 hours in total, no software needed.

1. Open `audits/swevo_human/label.html` in a browser. For each of the 100 items,
   find the table (caption) and the row/column (label) on the page image, then
   record exactly as printed: `results_table` (y/n), `bold_ok` (exactly one bold
   cell in the group), `whole_row_bold` (every bold cell of the table lies in one
   row or column), the bold cell's mean and deviation, the best non-bold cell's
   mean and deviation (`none` when not printed), and `n_runs` (`none` if nothing
   states one); `unclear` for a digit you cannot read. Answers autosave in the
   browser; press **Save labels** and put the downloaded file at
   `audits/swevo_human/labels.csv`.
2. Same for `audits/swevo_human_rows/label.html` (one extra field,
   `std_printed`: is a deviation printed for the bold cell anywhere in the
   table). Save as `audits/swevo_human_rows/labels.csv`.
3. `audits/swevo_markers/adjudicate.csv`: open each of the 17 papers by `url`
   and decide whether a per-cell test verdict is printed (`+/=/−` marks,
   win/tie/loss counts, or a p-value per function); fill `markers_human` (y/n)
   and `sentence_human` (a quoted sentence or caption).

Label from the page only; do not open the `labels_claude-sonnet-5.csv` files
(the model's answers) first. Send the three files back or push them here.
