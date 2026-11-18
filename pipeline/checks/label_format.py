"""CHECK 2 — Dòng nhãn YOLO: sai định dạng, ID lớp lạ, box tràn ảnh, box rỗng, box lặp.   (Script 2 trong slide)   ★★

Test:  pytest tests/test_label_format.py -q

Mỗi dòng nhãn: `id cx cy w h` (5 số, toạ độ 0–1). Trả về list[Issue]; `Issue.line` = số dòng (đếm từ 1).

| code             | severity | khi nào                                                                  |
|------------------|----------|--------------------------------------------------------------------------|
| BAD_FORMAT       | ERROR    | không đúng 5 cột số (dùng `parse_yolo_line`, bắt `ValueError`)           |
| BAD_CLASS_ID     | ERROR    | id lớp ngoài 0..len(ds.classes)-1                                        |
| BOX_ZERO         | ERROR    | w <= 0 hoặc h <= 0                                                       |
| BOX_OUT_OF_IMAGE | ERROR    | mép box vượt [0,1] quá `cfg["label_format"]["overflow_tol"]`; extra={"overflow": mức tràn} |
| DUP_BOX          | ERROR    | cùng lớp với một dòng TRƯỚC ĐÓ và IoU > `dup_box_iou`; báo ở dòng SAU    |
| BOX_TINY         | WARN     | cạnh ngắn của box (px) < `min_box_px`  (cần `ds.image_size(stem)`)       |
| BOX_HUGE         | WARN     | w*h > `max_box_frac`                                                     |

Gợi ý
- Mép trái = x - w/2, mép phải = x + w/2 (xem câu hỏi "dòng YOLO nào lỗi?" trong slide).
- Một dòng hỏng (BAD_FORMAT, BAD_CLASS_ID, BOX_ZERO) thì `continue`, đừng kiểm tiếp hình học của dòng đó.
- Dòng thiếu cột làm script của slide dừng giữa chừng: đây là lý do phải `try/except`.
- `iou_xywh(a, b)` có sẵn trong common.py.
- Ngưỡng nằm trong `cfg["label_format"]` — đừng viết cứng số vào code.
"""
from ..common import ERROR, WARN, Issue, iou_xywh, parse_yolo_line  # noqa: F401

NAME = "label_format"


def run(ds, cfg):
    c = cfg["label_format"]
    tol, min_px = c["overflow_tol"], c["min_box_px"]
    max_frac, dup_iou = c["max_box_frac"], c["dup_box_iou"]
    n_classes = len(ds.classes)
    issues = []

    for lab in ds.label_files():                       # mỗi file nhãn <stem>.txt
        stem = lab.stem
        size = ds.image_size(stem) if ds.image_path(stem) else None   # (rộng, cao) px; None nếu không có ảnh
        seen = []                                      # các box hợp lệ ở dòng trước, để tìm box lặp
        for no, text in ds.read_label_lines(stem) or []:   # số dòng gốc (đã bỏ dòng trống)

            def add(sev, code, msg, **extra):
                issues.append(Issue(NAME, sev, code, stem, msg, line=no, extra=extra))

            # 1) định dạng: đúng 5 cột số, id nguyên, không nan/inf
            try:
                cls, x, y, w, h = parse_yolo_line(text)
            except ValueError as e:
                add(ERROR, "BAD_FORMAT", f"dòng sai định dạng: {e}")
                continue

            # 2) id lớp phải nằm trong danh sách lớp
            if not 0 <= cls < n_classes:
                add(ERROR, "BAD_CLASS_ID", f"id lớp {cls} ngoài 0..{n_classes - 1}")
                continue

            # 3) box rỗng
            if w <= 0 or h <= 0:
                add(ERROR, "BOX_ZERO", f"box rỗng (w={w}, h={h})")
                continue

            # 4) tràn ảnh: mức vượt lớn nhất của 4 mép ra ngoài [0, 1]
            overflow = max(0 - (x - w / 2), (x + w / 2) - 1, 0 - (y - h / 2), (y + h / 2) - 1)
            if overflow > tol:
                add(ERROR, "BOX_OUT_OF_IMAGE", f"box tràn ảnh {overflow:.4f}", overflow=overflow)

            # 5) box lặp: cùng lớp với một dòng trước, IoU cao -> báo ở dòng sau
            box = (x, y, w, h)
            for prev_no, prev_cls, prev_box in seen:
                if prev_cls == cls and iou_xywh(box, prev_box) > dup_iou:
                    add(ERROR, "DUP_BOX", f"trùng box dòng {prev_no}", dup_of=prev_no)
                    break
            seen.append((no, cls, box))

            # 6) box quá nhỏ (theo px, cần kích thước ảnh)
            if size:
                short = min(w * size[0], h * size[1])
                if short < min_px:
                    add(WARN, "BOX_TINY", f"cạnh ngắn {short:.1f}px < {min_px}px", short_px=short)

            # 7) box quá lớn (theo tỉ lệ diện tích ảnh)
            if w * h > max_frac:
                add(WARN, "BOX_HUGE", f"box chiếm {w * h:.0%} ảnh", area=w * h)

    return issues
