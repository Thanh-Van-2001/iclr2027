# Chấm 60 item — hướng dẫn nhanh (≈ 1 giờ, làm dở được, tự lưu)

Mở file **`D:\iclr2027\audits\human\label.html`** bằng Edge/Chrome (double-click). Hết.
Mọi thứ cần thiết (ảnh bảng, câu seed/run trích từ paper, form) nằm trong trang đó.

## Làm gì
1. Nhìn ảnh bên trái: bảng đã cắt, ô **khung đỏ** = ô mà máy cho là "winner".
2. Trả lời các câu bên phải theo thứ tự. **Enter** = câu tiếp; Enter ở câu cuối = lưu & sang item sau.
   Câu chọn: gõ chữ đầu rồi Enter (`y`/`n`, `c`olumn/`r`ow, `h`igher/`l`ower, `sd`/`se`/`ci`/`u`nlabelled).
3. Không đọc được số nào → gõ `unclear`. Không có ± → gõ `none`.
4. Số run/seed: xem caption bảng trước, không có thì xem hộp "Câu có seed/run/trial" (đã trích từ cả paper).
   Paper nói nhiều số khác nhau → lấy số áp dụng cho bảng này; không thấy → `none`.
5. Xong (hoặc nghỉ giữa chừng) bấm **Xuất labels.csv** → lưu đè vào `D:\iclr2027\audits\human\labels.csv`.
   Trang tự lưu trong trình duyệt sau mỗi phím, mở lại là tiếp tục; đổi máy thì "Nhập CSV cũ".

Thứ tự hiển thị: 20 item `no_bar` trước (mỗi cái ~30 giây: hai số + "có ± nào không"), rồi 40 item
`testable` (~1–2 phút: bốn số + loại ± + số run). Có thể làm 2–3 lần, không cần một mạch.

**Không mở** `audits/gold_d/labels.csv` hay `items.json` (kết quả máy — cần giữ mù để số có giá trị).

## Xong rồi thì
Nhắn "chấm xong" — em chạy:

    python study/gold_set.py score --items audits/gold_d/items.json --labels audits/human/labels.csv --out out/gold_set_human.json
    python study/gold_set.py agree --a audits/gold_d/labels.csv --b audits/human/labels.csv

rồi nối số vào paper qua macro (không gõ tay), thay câu "No human labelled any item".

## Ý nghĩa các cột (chỉ để tra khi lưỡng lự)
| cột | điền gì |
|---|---|
| results_table | `y` nếu là bảng kết quả thí nghiệm, `n` nếu không (bảng hyperparameter, thống kê dataset...) |
| bold_ok | `y` nếu ô khung **in đậm** và là ô đậm **duy nhất** trong nhóm của nó (cột hoặc hàng); `n` nếu không đậm, hoặc có ≥2 ô đậm trong nhóm |
| orientation | `column` nếu các method xếp theo hàng và so sánh dọc theo cột; `row` nếu ngược lại |
| direction | `higher` nếu cao hơn là tốt (accuracy, F1...), `lower` nếu thấp hơn là tốt (loss, FID, error...) — nhìn mũi tên ↑↓ hoặc tên metric |
| winner_mean / winner_disp | số trong ô khung, và phần sau ± (hoặc trong ngoặc); dán nguyên `85.2 ± 0.3` vào ô mean cũng được, trang tự tách |
| runner_mean / runner_disp | ô **tốt nhất trong các ô không đậm** cùng nhóm (theo direction), và phần ± của nó |
| disp_type | `sd` / `se` / `ci` nếu caption hoặc câu trích nói rõ; `unlabelled` nếu chỉ có ± mà không nói là gì |
| n_runs / n_source | số run/seed và tìm thấy ở đâu: `caption` (caption bảng), `page` (cùng trang), `paper` (chỗ khác trong paper), `none` |
| rival_copied | `y` nếu hàng/cột runner-up có trích dẫn [12], dấu †/*, hoặc chữ "from"/"reported in" (số chép từ paper khác); `n` nếu không; `unclear` nếu không rõ |
| error_bar_present | (chỉ item no_bar) `y` nếu bảng in **bất kỳ** ± / SD / CI nào cho ô khung hoặc runner-up — trong ô, cột riêng, hay chú thích; `n` nếu không |

Tạo lại trang (nếu cần): `python study/human_kit_html.py`.
