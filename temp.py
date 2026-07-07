import numpy as np
import cv2
import tkinter as tk
from tkinter import filedialog, messagebox
import os


def imread_unicode(path):
    img = cv2.imdecode(np.fromfile(path, dtype=np.uint8), cv2.IMREAD_COLOR)
    return img


def imwrite_unicode(path, img):
    ext = os.path.splitext(path)[1]
    cv2.imencode(ext, img)[1].tofile(path)


def load_images(file_paths):
    images = []
    for path in file_paths:
        img = imread_unicode(path)
        if img is None:
            print(f"警告：无法读取图片 {os.path.basename(path)}，已跳过")
            continue
        images.append(img)
        print(f"已加载：{os.path.basename(path)} | 尺寸：{img.shape[1]}×{img.shape[0]}")
    return images


def resize_if_needed(img, max_dim=4000):
    h, w = img.shape[:2]
    if max(w, h) <= max_dim:
        return img
    scale = max_dim / max(w, h)
    new_w = int(w * scale)
    new_h = int(h * scale)
    print(f"图片过大，已缩放到 {new_w}×{new_h}")
    return cv2.resize(img, (new_w, new_h), interpolation=cv2.INTER_AREA)


def show_image_in_window(img, title="Result"):
    """
    自动弹窗显示结果图。
    """
    display = img.copy()
    max_w = 1920
    if display.shape[1] > max_w:
        scale = max_w / display.shape[1]
        display = cv2.resize(display, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)

    cv2.namedWindow(title, cv2.WINDOW_NORMAL)
    cv2.imshow(title, display)
    cv2.waitKey(0)
    cv2.destroyAllWindows()


def ask_user_mode():
    """
    如果自动识别不确定，弹框让用户选择。
    """
    root = tk.Tk()
    root.withdraw()

    result = messagebox.askyesno(
        "选择拼接模式",
        "检测到两张图片。\n\n"
        "是室内/文档/小视差合成吗？\n\n"
        "是 = 平面拼接\n"
        "否 = 全景拼接"
    )

    return "planar" if result else "panorama"


def detect_mode_auto(images):
    """
    自动判断拼接模式。

    2张图：优先平面拼接
    3张及以上：全景拼接
    """
    n = len(images)

    if n == 2:
        return "planar"
    else:
        return "panorama"


def remove_black_border_safe(img, max_crop_ratio=0.35):
    """
    安全裁黑边，不允许切掉主体。
    """
    if img is None:
        return None

    h, w = img.shape[:2]
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    mask = gray > 15

    if not np.any(mask):
        print("警告：未检测到有效内容，不裁边")
        return img

    rows = np.any(mask, axis=1)
    cols = np.any(mask, axis=0)

    top = np.argmax(rows)
    bottom = h - np.argmax(rows[::-1])
    left = np.argmax(cols)
    right = w - np.argmax(cols[::-1])

    crop_h = bottom - top
    crop_w = right - left

    if crop_w < max_crop_ratio * w or crop_h < max_crop_ratio * h:
        print("警告：裁边范围过大，可能切掉主体，已取消自动裁边")
        return img

    return img[top:bottom, left:right]


def stitch_planar_two_images(img1, img2, lowe_ratio=0.75, ransac_thresh=2.0):
    """
    双图平面单应拼接。
    适合室内、文档、白板、墙面、小视差合成。
    """
    print("[平面拼接] 正在提取SIFT特征...")
    sift = cv2.SIFT_create()

    kp1, des1 = sift.detectAndCompute(img1, None)
    kp2, des2 = sift.detectAndCompute(img2, None)

    if des1 is None or des2 is None:
        return None, "无法提取有效特征"

    print("[平面拼接] 正在特征匹配...")
    matcher = cv2.BFMatcher(cv2.NORM_L2)
    matches = matcher.knnMatch(des1, des2, k=2)

    good_matches = []
    for m, n in matches:
        if m.distance < lowe_ratio * n.distance:
            good_matches.append(m)

    if len(good_matches) < 10:
        return None, f"有效匹配点不足，仅 {len(good_matches)} 个"

    print(f"[平面拼接] 优质匹配点 {len(good_matches)} 个")

    pts1 = np.float32([kp1[m.queryIdx].pt for m in good_matches])
    pts2 = np.float32([kp2[m.trainIdx].pt for m in good_matches])

    print("[平面拼接] 正在求解单应矩阵...")
    H, mask = cv2.findHomography(pts2, pts1, cv2.RANSAC, ransac_thresh)

    if H is None:
        return None, "单应矩阵估计失败"

    inlier_count = int(np.sum(mask))
    print(f"[平面拼接] 单应矩阵求解完成，内点数量 {inlier_count}")

    h1, w1 = img1.shape[:2]
    h2, w2 = img2.shape[:2]

    corners = np.float32([
        [0, 0],
        [0, h2 - 1],
        [w2 - 1, h2 - 1],
        [w2 - 1, 0]
    ]).reshape(-1, 1, 2)

    warped_corners = cv2.perspectiveTransform(corners, H)

    x_min = min(0, np.min(warped_corners[:, 0, 0]))
    x_max = max(w1, np.max(warped_corners[:, 0, 0]))
    y_min = min(0, np.min(warped_corners[:, 0, 1]))
    y_max = max(h1, np.max(warped_corners[:, 0, 1]))

    out_w = int(np.ceil(x_max - x_min))
    out_h = int(np.ceil(y_max - y_min))

    shift = np.array([
        [1, 0, -x_min],
        [0, 1, -y_min],
        [0, 0, 1]
    ], dtype=np.float64)

    H_shifted = shift @ H

    print("[平面拼接] 正在投影变换...")
    warped_img2 = cv2.warpPerspective(
        img2, H_shifted, (out_w, out_h),
        flags=cv2.INTER_LINEAR,
        borderMode=cv2.BORDER_CONSTANT,
        borderValue=(0, 0, 0)
    )

    canvas = np.zeros((out_h, out_w, 3), dtype=np.uint8)
    offset_y, offset_x = int(-y_min), int(-x_min)
    canvas[offset_y:offset_y + h1, offset_x:offset_x + w1] = img1

    print("[平面拼接] 正在融合...")

    mask1 = cv2.cvtColor(canvas, cv2.COLOR_BGR2GRAY) > 15
    mask2 = cv2.cvtColor(warped_img2, cv2.COLOR_BGR2GRAY) > 15

    overlap = mask1 & mask2

    result = canvas.astype(np.float32)

    result[mask2 & ~mask1] = warped_img2[mask2 & ~mask1].astype(np.float32)

    if np.any(overlap):
        alpha = np.zeros((out_h, out_w), dtype=np.float32)

        for i in range(out_h):
            cols = np.where(overlap[i])[0]
            if len(cols) < 2:
                continue
            l, r = cols[0], cols[-1]
            alpha[i, l:r+1] = np.linspace(1, 0, r - l + 1)

        for c in range(3):
            result[:, :, c] = np.where(
                overlap,
                alpha * result[:, :, c] + (1 - alpha) * warped_img2[:, :, c],
                result[:, :, c]
            )

    result = np.clip(result, 0, 255).astype(np.uint8)

    print("[平面拼接] 融合完成")

    return result, "拼接成功"


def stitch_panorama_images(images):
    """
    OpenCV 原生全景拼接。
    适合铁轨、建筑、风景、连续旋转拍摄。
    """
    print("[全景拼接] 正在启动全景拼接...")

    stitcher = cv2.Stitcher.create(mode=cv2.Stitcher_PANORAMA)

    status, pano = stitcher.stitch(images)

    if status != cv2.Stitcher_OK:
        error_map = {
            cv2.Stitcher_ERR_NEED_MORE_IMGS: "图片重叠不足，无法拼接",
            cv2.Stitcher_ERR_HOMOGRAPHY_EST_FAIL: "特征匹配失败，单应矩阵估计错误",
            cv2.Stitcher_ERR_CAMERA_PARAMS_ADJUST_FAIL: "相机参数调整失败，图片差异过大"
        }
        return None, error_map.get(status, f"拼接失败，状态码 {status}")

    pano = remove_black_border_safe(pano)

    print("[全景拼接] 拼接完成")

    return pano, "拼接成功"


def main():
    root = tk.Tk()
    root.withdraw()

    print("=== 智能拼接工具 ===")
    print("请选择图片...")

    file_paths = filedialog.askopenfilenames(
        title="选择图片进行拼接",
        filetypes=[
            ("图片文件", "*.jpg *.jpeg *.png *.bmp *.tiff"),
            ("所有文件", "*.*")
        ]
    )

    if not file_paths:
        print("未选择图片，程序退出")
        return

    if len(file_paths) > 20:
        print("提示：最多处理 20 张，已截取前 20 张")
        file_paths = file_paths[:20]

    images = load_images(file_paths)

    if len(images) < 2:
        print("错误：有效图片不足 2 张")
        return

    images = [resize_if_needed(img) for img in images]

    mode = detect_mode_auto(images)

    if mode == "planar" and len(images) == 2:
        print("\n自动识别：双图平面拼接")
        panorama, msg = stitch_planar_two_images(images[0], images[1])
    else:
        print("\n自动识别：全景拼接")
        panorama, msg = stitch_panorama_images(images)

    if panorama is None:
        print(f"\n拼接失败：{msg}")
        messagebox.showerror("拼接失败", msg)
        return

    output_path = "panorama_result.jpg"
    imwrite_unicode(output_path, panorama)

    print(f"\n{msg}")
    print(f"最终尺寸：{panorama.shape[1]}×{panorama.shape[0]}")
    print(f"结果已保存为 {output_path}")

    messagebox.showinfo("拼接完成", f"拼接完成！\n尺寸：{panorama.shape[1]}×{panorama.shape[0]}\n已保存为 panorama_result.jpg")

    show_image_in_window(panorama, title="Panorama Result")


if __name__ == "__main__":
    main()