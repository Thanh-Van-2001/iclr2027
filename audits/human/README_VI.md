# Bộ 30 item để anh tự chấm (human reference)

Mục đích: reviewer yêu cầu có **nhãn do người** chấm, không chỉ LLM. 30 item này
là 30 comparison đầu tiên của held-out set (gold_b). Mỗi item ~1 phút.

## Cách làm
Mở lần lượt `img/NNN_testable.png` (bảng đã cắt, ô mà pipeline chọn làm "winner"
được đóng khung đỏ). Với mỗi item điền vào dòng tương ứng trong `labels.csv`:

| cột | điền gì |
|---|---|
| results_table | `y` nếu đây là bảng kết quả, `n` nếu không |
| bold_ok | `y` nếu ô trong khung **in đậm** và là ô đậm **duy nhất** trong nhóm của nó (cột hoặc hàng); `n` nếu không |
| orientation | `column` nếu nhóm so sánh là cột (các method xếp theo hàng), `row` nếu là hàng |
| direction | `higher` nếu giá trị cao hơn là tốt hơn, `lower` nếu ngược lại |
| winner_mean | số in trong ô khung (không có ±) |
| winner_disp | phần sau ± (hoặc trong ngoặc) của ô khung; `none` nếu không có |
| runner_mean | giá trị **tốt nhất trong các ô KHÔNG đậm** cùng nhóm |
| runner_disp | phần ± của ô đó; `none` nếu không có |
| disp_type | `sd` / `se` / `ci` / `unlabelled` theo caption hoặc `NNN_runs.txt` (câu trong paper) |
| n_runs | số lần chạy/seed áp dụng cho bảng này, tìm trong caption hoặc `NNN_runs.txt`; `none` nếu không có |
| n_source | `caption` / `page` / `paper` / `none` |
| note | ghi chú tuỳ ý |

Không đọc được chữ số nào thì ghi `unclear` cho ô đó. Không xem `items.json`
(đó là kết quả của pipeline, cần giữ mù).

## Khi xong
    python study/gold_set.py score --items audits/gold_b/items.json --labels audits/human/labels.csv --out out/gold_set_human.json
    python study/gold_set.py agree --a audits/gold_b/labels.csv --b audits/human/labels.csv
Lệnh thứ hai in ra độ đồng thuận giữa anh và LLM theo từng trường.
