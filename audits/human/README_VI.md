# Bộ 60 item để anh tự chấm (human reference, set D — pipeline đã đóng băng)

Mục đích: reviewer nào cũng đòi **nhãn do người** chấm. Set D được rút *sau khi*
pipeline đóng băng (git tag `frozen-v1`), từ các paper mà set A/B/C chưa đụng tới,
và **không sửa bug nào theo nó**. 60 item này = 40 item `testable` đầu tiên
(001–040) + 20 item `no_bar` đầu tiên (101–120) của set D. Mỗi item ~1–3 phút.
Làm được nhiều hơn 60 (cả set D là 180 item trong `audits/gold_d/img`) thì càng tốt:
chỉ cần thêm dòng vào `labels.csv`.

## Cách làm
Mở lần lượt `img/NNN_testable.png` hoặc `img/NNN_no_bar.png` (bảng đã cắt, ô mà
pipeline chọn làm "winner" được đóng **khung đỏ**). Điền vào dòng tương ứng trong
`labels.csv`:

| cột | điền gì |
|---|---|
| results_table | `y` nếu đây là bảng kết quả thí nghiệm, `n` nếu không |
| bold_ok | `y` nếu ô trong khung **in đậm** và là ô đậm **duy nhất** trong nhóm của nó (cột hoặc hàng); `n` nếu không |
| orientation | `column` nếu nhóm so sánh là cột (các method xếp theo hàng), `row` nếu là hàng |
| direction | `higher` nếu giá trị cao hơn là tốt hơn, `lower` nếu ngược lại |
| winner_mean | số in trong ô khung (không có ±) |
| winner_disp | phần sau ± (hoặc trong ngoặc) của ô khung; `none` nếu không có |
| runner_mean | giá trị **tốt nhất trong các ô KHÔNG đậm** cùng nhóm |
| runner_disp | phần ± của ô đó; `none` nếu không có |
| disp_type | `sd` / `se` / `ci` / `unlabelled` theo caption hoặc `NNN_runs.txt` (các câu trong paper có chữ seed/run/trial) |
| n_runs | số lần chạy/seed áp dụng cho bảng này, tìm trong caption hoặc `NNN_runs.txt`; `none` nếu không có |
| n_source | `caption` / `page` / `paper` / `none` |
| rival_copied | `y` nếu hàng/cột của runner-up có trích dẫn, dấu †/*, hoặc chữ "from"/"reported in" (số chép từ paper khác); `n` nếu không; `unclear` nếu không rõ |
| error_bar_present | (chỉ item `no_bar`) `y` nếu bảng in **bất kỳ** độ lệch nào cho ô khung hoặc runner-up (trong ô, hoặc cột/hàng riêng, hoặc ± ở đâu đó trong bảng); `n` nếu không |
| note | ghi chú tuỳ ý |

Item `no_bar` chỉ cần: results_table, bold_ok, orientation, direction, winner_mean,
runner_mean, error_bar_present, note.

Không đọc được chữ số nào thì ghi `unclear` cho ô đó. **Không xem** `audits/gold_d/items.json`
hay `audits/gold_d/labels.csv` (kết quả pipeline và LLM, cần giữ mù).

## Khi xong
    python study/gold_set.py score --items audits/gold_d/items.json --labels audits/human/labels.csv --out out/gold_set_human.json
    python study/gold_set.py agree --a audits/gold_d/labels.csv --b audits/human/labels.csv
Lệnh thứ nhất chấm pipeline theo nhãn của anh; lệnh thứ hai in độ đồng thuận
giữa anh và LLM theo từng trường. Sau đó em nối số vào paper (macro), không gõ tay.
