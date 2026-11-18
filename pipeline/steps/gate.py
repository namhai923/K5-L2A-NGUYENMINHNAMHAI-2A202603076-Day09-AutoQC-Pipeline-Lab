"""BƯỚC 4 — Cửa chặn: quyết định Release / Hold / Rework.   ★

Test:  pytest tests/test_gate.py -q

Cây quyết định Day 07 (slide Day 09: "Lỗi bắt buộc chặn pipeline; lỗi cảnh báo chuyển người xem"):

  còn ≥ 1 lỗi bắt buộc (severity ERROR)                          -> "Rework"
  không còn lỗi bắt buộc, nhưng tỉ lệ ẢNH còn cảnh báo
      >= cfg["gate"]["warn_ratio_hold"]                          -> "Hold"
  còn lại                                                        -> "Release"

Tỉ lệ cảnh báo = (số ẢNH khác nhau có ≥ 1 cảnh báo) / (tổng số ảnh).  Chú ý:
- chỉ đếm issue có `image` nằm trong `image_stems` (bỏ "<dataset>", "data.yaml");
- bỏ qua ảnh nằm trong `reviewed` (người đã xem, cảnh báo của ảnh đó coi như đã xử lý) — nhưng LỖI BẮT BUỘC thì không bao giờ được bỏ qua;
- mẫu số là số ảnh, không phải số issue.

Trả về dict: decision, n_errors, n_warn_images, n_images, warn_ratio (làm tròn 4 chữ số), reasons (list[str], giải thích bằng tiếng Việt, có số liệu).
"""
from ..common import ERROR, WARN  # noqa: F401


def decide(issues, image_stems, cfg, reviewed=frozenset()):
    stems = set(image_stems)
    reviewed = set(reviewed)
    threshold = cfg["gate"]["warn_ratio_hold"]

    # Lỗi bắt buộc: đếm TẤT CẢ (cả lỗi cấp dataset, cả ảnh đã review) — không bao giờ bỏ qua.
    n_errors = sum(1 for i in issues if i.severity == ERROR)

    # Ảnh còn cảnh báo: chỉ ảnh có thật trong dataset và chưa được người xem.
    warn_images = {i.image for i in issues
                   if i.severity == WARN and i.image in stems and i.image not in reviewed}

    n_images = len(stems)
    ratio = len(warn_images) / n_images if n_images else 0.0   # dataset rỗng: không chia cho 0

    if n_errors:
        decision = "Rework"
        reasons = [f"còn {n_errors} lỗi bắt buộc (error) chưa sửa"]
    elif ratio >= threshold:
        decision = "Hold"
        reasons = [f"{len(warn_images)}/{n_images} ảnh ({ratio:.1%}) còn cảnh báo chưa duyệt, "
                   f">= ngưỡng {threshold:.0%}"]
    else:
        decision = "Release"
        reasons = [f"không còn lỗi bắt buộc; {len(warn_images)}/{n_images} ảnh ({ratio:.1%}) "
                   f"còn cảnh báo, < ngưỡng {threshold:.0%}"]

    return {
        "decision": decision,
        "n_errors": n_errors,
        "n_warn_images": len(warn_images),
        "n_images": n_images,
        "warn_ratio": round(ratio, 4),
        "reasons": reasons,
    }
