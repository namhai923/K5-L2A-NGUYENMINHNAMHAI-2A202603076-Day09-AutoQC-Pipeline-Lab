# Day 09 Lab — Nguyễn Minh Nam Hải: 2A202603076 - Nguyễn Minh Nam Hải

## 1. Kết luận trước
pipeline kết luận **Hold**. 224 ảnh vào, 202 ảnh ra, 38/202 ảnh (18.8%) còn cảnh báo chưa duyệt, trên ngưỡng 10%. Lý do chính:
 - Không còn lỗi bắt buộc, nên không phải Rework.
 - Hàng đợi 125 ảnh lớn hơn ngân sách 80, nên còn 18.8% ảnh mang cảnh báo chưa duyệt, trên ngưỡng 10%, dẫn tới Hold.
 - Hạ cảnh báo bằng conf 0.8 sẽ ra Release giả.

## 2. Lỗi và phân việc
Lấy từ `02_error_list_v1` (gom theo mã lỗi). Cột "ai sửa": **máy** (autofix) hay **người** (hàng đợi); chỉ ghi những mã có mặt trong lô của bạn.

| Mã lỗi | Số ảnh/dòng | Ai sửa (máy/người) | Vì sao |
|---|---:|---|---|
| `DUP_IMAGE_EXACT` | 8 | máy | Trùng từng byte: xoá không mất gì. |
| `DUP_IMAGE_NEAR` | 4 | máy | Trùng gần đúng (phash ≤ 12): làm lệch dữ liệu. |
| `LEAK_TEST` | 5 | máy | Trùng ảnh test: thổi phồng mAP test. |
| `BAD_SIZE` | 3 | máy | Cạnh ngắn < 250 px. |
| `CORRUPT_IMAGE` | 2 | máy | Không mở được ảnh. |
| `BAD_CLASS_NAME` | 2 | máy | Tên đúng có sẵn trong `cfg["classes"]`. |
| `BAD_CLASS_ID` | 6 | máy | Id lạ: không đoán lớp thật. |
| `BAD_FORMAT` | 3 | máy | Không đủ 5 cột số: không phục hồi được. |
| `BOX_ZERO` | 4 | máy | Box rỗng: không có vật. |
| `DUP_BOX` | 7 | máy | Box lặp: bản đầu vẫn còn. |
| `BOX_OUT_OF_IMAGE` | 8 | máy | Cắt về [0,1], giữ lớp. |
| `MISSING_LABEL_FILE` | 6 | người | Máy không bịa nhãn; cả 6 đã được gán. |
| `POSSIBLE_MISSING` | 53 | người | Model thấy vật thiếu box; model có thể sai. |
| `POSSIBLE_FALSE_POS` | 29 | người | Box nhãn không khớp vật nào model thấy. |
| `POSSIBLE_LOOSE_BOX` | 28 | người | Box lỏng/lệch: người mới biết box đúng. |
| `POSSIBLE_WRONG_CLASS` | 18 | người | Lớp nào đúng là câu hỏi ngữ nghĩa. |
| `EMPTY_LABEL` | 12 | người | Ảnh nền hay chưa gán? |
| `BOX_TINY` | 6 | người | Có thể là vật xa thật. |
| `BOX_HUGE` | 3 | người | Có thể là vật chụp cận. |
| `CLASS_RARE` | 4 | máy | Là id lạ của `BAD_CLASS_ID`, tự hết sau `drop_line`. |

vì sao `05_review_queue.csv` xếp ảnh đầu hàng như vậy? Với ngân sách 80 ảnh, người xem được bao nhiêu lỗi ngữ nghĩa?

 - Vì hàng đợi xếp theo điểm = tổng trọng số × (1+conf) của cảnh báo + điểm sửa tự động; NEEDS_LABEL +10
 - Với 80 ảnh, người xem được 94 lỗi ngữ nghĩa (WRONG_CLASS 18/18, MISSING 51/53, FALSE_POS 13/24, LOOSE_BOX 12/28)

## 3. Calibration (2 ngưỡng)
| Tham số | Khởi đầu | Đã chọn | Precision / Recall (trước → sau) | Lý do (đánh đổi) |
|---|---|---|---|---|
| `duplicates.phash_dist` | 2 | **12** | NEAR 1.00 / 0.50 → 1.00 / 0.67 | Cờ trùng = **xoá ảnh tự động** → ưu tiên precision. Trên raw, ảnh trùng thật cách ≤ 10, ảnh khác nhau gần nhất cách 16 → chọn 12 ở giữa. |
| `second_opinion.conf` | 0.25 | **0.6** | MISSING 0.50 / 1.00 → 0.57 / 1.00; WRONG_CLASS 0.56 / 0.83 → 0.62 / 0.83 | Chỉ là **cảnh báo cho người** → ưu tiên recall. 0.6 là conf cao nhất giữ recall MISSING 1.00 (0.7 tụt 0.88); hàng đợi 143 → 125 ảnh. Mất 1/5 LOOSE_BOX. |

**Không chọn conf 0.8** dù ra Release (7.9% so với Hold 18.8%): recall MISSING tụt còn 0.75. Hàng đợi nhỏ vì checker bỏ sót, không phải vì dữ liệu sạch → Release giả.

**Calibration đánh lừa: precision 1.00 của `phash_dist` = 16 là ảo.** Calib chỉ 39 ảnh; hai ảnh khác nhau gần nhất cách 20 bit, nên không ngưỡng ≤ 16 nào gộp nhầm được. Trên raw (nhiều cặp hơn hàng chục lần), ngưỡng 16 cờ 26 ảnh thay vì 17. Mở xem: `img_0008` (trượt tuyết) / `img_0011` (tennis) và `img_0013` / `test_087` bị coi là trùng dù khác hẳn. Ảnh trùng biến đổi mạnh (≥ 16, vd. `img_0074`/`img_0084`) là điểm mù của ngưỡng 12.

## 4. Cửa chặn và điều pipeline KHÔNG bắt được
**(a) Gate chặn đúng.** Chạy `python -m pipeline.run --budget 0 --reports work/rep_nb --export-dir work/exp_nb`:
- Kết luận **Rework**, mã thoát **20**. `08_summary.json`: `n_errors: 6`, `reviewed: 0`.
- **Không xuất**: `"exported": null`, thư mục `work/exp_nb/` không được tạo.

**(b) Điểm mù** (calib):
- **Box lỏng:** `LOOSE_BOX` bắt 1/5. Model không chắc về vật (conf < 0.6) nên không có gì để so.
- **Nhầm lớp model cũng nhầm:** `calib_009` truck → bus bị sót; model nói car.
- **Ảnh trùng biến đổi mạnh:** `DUP_IMAGE_NEAR` 4/6; sót `calib_037`, `calib_038` (phash 16, 18 > 12).

## 5. Train: raw vs clean (tùy chọn, chấm riêng)
yolo26n, 20 epoch, seed 0 và 1, cùng val (gold_val) và test (100 ảnh). Nguồn: `submission/results/comparison.md`.

| biến thể | #ảnh train | số seed | map50 (TB ± độ lệch) | map50_95 (TB ± độ lệch) | precision (TB ± độ lệch) | recall (TB ± độ lệch) |
|---|---|---|---|---|---|---|
| raw | 224 | 2 | 0.726 ± 0.000 | 0.512 ± 0.004 | 0.764 ± 0.061 | 0.649 ± 0.028 |
| clean | 202 | 2 | 0.701 ± 0.025 | 0.487 ± 0.008 | 0.759 ± 0.003 | 0.625 ± 0.019 |

- **Chênh mAP50 −0.025** = độ lệch seed (0.025) → chưa kết luận được.
- **raw thật train 213/224**: Ultralytics bỏ 11 ảnh nhãn/ảnh hỏng.
- **raw rò rỉ 5 ảnh test** → điểm raw có thể bị thổi phồng; kiểm bằng cách đo lại trên test bỏ 5 ảnh đó.
- **Không lớp nào lợi rõ**: bus +0.008 (nhiễu), truck −0.111 (ít box, người đổi car → truck). Lỗi dồn vào person nhưng person nhiều box nên AP không đổi.
- **clean chưa sạch**: 38/202 ảnh còn cảnh báo (hàng đợi 125 > 80) → chưa phải chặn trên.

## 6. Quyết định và ghi chú AI
**(a) Quyết định: Hold.** Không còn lỗi bắt buộc, nhưng 38/202 ảnh (18.8%) còn cảnh báo chưa duyệt (ngưỡng 10%). Để thành Release: người duyệt thêm ít nhất 18 ảnh còn cảnh báo (xuống < 20/202) bằng `--no-review` rồi `--resume-after-review`. Không hạ `conf` lên 0.8 hay đổi ngân sách/ngưỡng gate để "đạt": đó là Release giả.

**(b) Ghi chú AI** (dùng Claude Code):
- **Prompt chính:** dán docstring đề (bảng mã lỗi, ngưỡng trong `cfg`, ca biên) của từng module, yêu cầu viết `run`/`fix`/`decide` cho qua `tests/`.
- **Cách kiểm:** `pytest` (79/79), thêm 3 ca tự thử (dòng dính 2 lỗi, dòng trống giữa file, ảnh nhiều dự đoán), chạy `make run` và xem ảnh bằng `viz_labels.py`.
- **1 lần AI sai:** giải thích điểm mù `LOOSE_BOX` là "IoU vẫn cao"; kiểm lại dự đoán thì thật ra model có conf < 0.6 (hoặc không có dự đoán) cho các vật đó, nên đã sửa.
