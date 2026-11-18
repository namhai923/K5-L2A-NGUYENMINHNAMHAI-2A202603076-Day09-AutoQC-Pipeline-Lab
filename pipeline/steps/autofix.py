"""BƯỚC 2/4 — Sửa tự động những lỗi bắt buộc mà máy sửa được AN TOÀN.   ★★

Test:  pytest tests/test_autofix.py -q

`fix(ds, issues, cfg) -> list[dict]`: duyệt `issues` (chỉ lỗi severity ERROR), sửa thẳng vào thư mục `ds`,
và trả về danh sách thay đổi; mỗi phần tử có khoá: image, line, action, before, after
(đây chính là file `03_fixes.csv` — bằng chứng pipeline đã làm gì, người có thể kiểm lại).

| code lỗi                                       | cách sửa                                    | action           |
|------------------------------------------------|---------------------------------------------|------------------|
| BAD_FORMAT, BAD_CLASS_ID, BOX_ZERO, DUP_BOX    | xoá dòng đó khỏi file nhãn                  | "drop_line"      |
| BOX_OUT_OF_IMAGE                               | cắt box về trong [0,1] (giữ nguyên lớp)     | "clip_box"       |
| MISSING_LABEL_FILE                             | KHÔNG sửa file (máy không thể bịa nhãn): ghi 1 dòng fix, before="(không có file)", after="chuyển người gán" | "needs_label" |
| BAD_CLASS_NAME                                 | ghi lại `names` trong data.yaml đúng `cfg["classes"]` | "rename_classes" |
| DUP_IMAGE_*, LEAK_TEST, CORRUPT_IMAGE, BAD_SIZE| xoá ảnh + nhãn khỏi `ds`                    | "remove_image"   |

Bẫy cần nghĩ tới (có test cho từng cái)
- Một file có NHIỀU dòng lỗi: số dòng trong `issues` là số dòng GỐC. Nếu xoá từng dòng một thì số dòng lệch.
  Gom theo file, rồi ghi lại MỘT lần.
- Sau khi cắt, box có thể không còn diện tích (nằm hẳn ngoài ảnh): lúc đó xoá dòng thay vì ghi box rỗng.
- Một dòng có 2 lỗi (vd. BOX_OUT_OF_IMAGE + DUP_BOX): xoá dòng thắng, chỉ ghi 1 fix `drop_line`, không ghi thêm `clip_box`. Dòng trống ở giữa file vẫn đếm vào số dòng gốc.
- Ảnh vừa bị xoá (DUP_IMAGE_*...) mà còn issue dòng của chính nó: bỏ qua êm, không được báo lỗi/chết.
- Không động tới lỗi WARN (cảnh báo là việc của người). Không sửa file ở `data/raw/` — chỉ sửa `ds`.
- Chạy lần 2 trên dữ liệu đã sửa phải không làm gì thêm (idempotent) — NGOẠI LỆ duy nhất: `needs_label` được ghi lại mỗi lần còn lỗi `MISSING_LABEL_FILE` (vì ảnh vẫn chưa có nhãn).

- `needs_label` KHÔNG tạo file nhãn rỗng (rỗng = "ảnh nền", khác với "chưa gán"). `review_queue` sẽ đẩy ảnh này lên đầu hàng đợi cho người.

Gợi ý: `yaml.safe_load / safe_dump`.
"""
from collections import defaultdict  # noqa: F401

import yaml  # noqa: F401

from ..common import ERROR, parse_yolo_line  # noqa: F401


DROP_CODES = {"BAD_FORMAT", "BAD_CLASS_ID", "BOX_ZERO", "DUP_BOX"}
REMOVE_CODES = {"LEAK_TEST", "CORRUPT_IMAGE", "BAD_SIZE"}       # + mọi code bắt đầu bằng "DUP_IMAGE_"


def _is_remove(code):
    return code in REMOVE_CODES or code.startswith("DUP_IMAGE_")


def _fx(image, line, action, before, after):
    return {"image": image, "line": line, "action": action, "before": before, "after": after}


def _clip(text):
    """Cắt box về trong [0,1]. Trả về dòng mới, hoặc None nếu box không còn diện tích."""
    c, x, y, w, h = parse_yolo_line(text)
    x1, y1 = max(0.0, x - w / 2), max(0.0, y - h / 2)
    x2, y2 = min(1.0, x + w / 2), min(1.0, y + h / 2)
    if x2 <= x1 or y2 <= y1:                       # box nằm hẳn ngoài ảnh -> không cứu được
        return None
    return f"{c} {(x1 + x2) / 2:.6f} {(y1 + y2) / 2:.6f} {x2 - x1:.6f} {y2 - y1:.6f}"


def fix(ds, issues, cfg):
    errors = [i for i in issues if i.severity == ERROR]     # không bao giờ động tới WARN
    fixes = []

    # 1) Xoá ảnh + nhãn (làm TRƯỚC, để issue dòng của ảnh đã xoá được bỏ qua êm).
    removed = set()
    for i in errors:
        if not _is_remove(i.code) or i.image in removed:
            continue
        removed.add(i.image)
        files = [p for p in ds.image_files() if p.stem == i.image]
        lab = ds.label_path(i.image)
        if lab.exists():
            files.append(lab)
        if not files:                                       # đã xoá ở lần chạy trước -> idempotent
            continue
        for p in files:
            p.unlink()
        fixes.append(_fx(i.image, "", "remove_image", ", ".join(p.name for p in files), f"(đã xoá: {i.code})"))

    # 2) data.yaml: ghi lại names đúng cfg["classes"] (chỉ khi đang khác).
    if any(i.code == "BAD_CLASS_NAME" for i in errors) and ds.yaml_path.exists():
        before = ds.yaml_names()
        want = dict(enumerate(cfg["classes"]))
        if before != want:
            d = yaml.safe_load(ds.yaml_path.read_text(encoding="utf-8")) or {}
            d["names"] = want
            ds.yaml_path.write_text(yaml.safe_dump(d, allow_unicode=True, sort_keys=False), encoding="utf-8")
            fixes.append(_fx("data.yaml", "", "rename_classes",
                             str(list(before.values())), str(cfg["classes"])))

    # 3) Ảnh chưa có nhãn: KHÔNG tạo file, chỉ ghi lại để chuyển người gán.
    for i in errors:
        if i.code == "MISSING_LABEL_FILE" and i.image not in removed and not ds.label_path(i.image).exists():
            fixes.append(_fx(i.image, "", "needs_label", "(không có file)", "chuyển người gán"))

    # 4) Lỗi dòng: gom theo file -> {số dòng GỐC: {code}} rồi ghi lại file MỘT lần.
    by_file = defaultdict(lambda: defaultdict(set))
    for i in errors:
        if i.line is not None and (i.code in DROP_CODES or i.code == "BOX_OUT_OF_IMAGE"):
            by_file[i.image][i.line].add(i.code)

    for stem, by_line in sorted(by_file.items()):
        lab = ds.label_path(stem)
        if stem in removed or not lab.exists():             # ảnh đã bị xoá -> bỏ qua êm
            continue
        raw = lab.read_text(encoding="utf-8", errors="replace").splitlines()   # giữ dòng trống: số dòng = số gốc
        out, changed = [], False
        for no, text in enumerate(raw, 1):
            codes = by_line.get(no)
            if not codes or not text.strip():
                out.append(text)
                continue
            new = None
            if not codes & DROP_CODES:                      # chỉ BOX_OUT_OF_IMAGE -> thử cắt
                try:
                    new = _clip(text)
                except ValueError:
                    new = None
            if new is None:                                 # xoá dòng thắng (kể cả khi cắt xong không còn box)
                fixes.append(_fx(stem, no, "drop_line", text, ""))
            else:
                fixes.append(_fx(stem, no, "clip_box", text, new))
                out.append(new)
            changed = True
        if changed:
            lab.write_text("".join(l + "\n" for l in out), encoding="utf-8")

    return fixes
