#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
PIS-web 全景图像拼接脚本
接口规范见 docs/算法组接口文档.md

调用方式:
    python3 stitch.py {任务目录}

读取:
    {任务目录}/input/  -- Go 后端已创建，JPG/PNG 原图

产出:
    {任务目录}/result/result.jpg  -- 拼接结果（失败时不生成）
    {任务目录}/result/meta.json   -- 元信息（成功/失败都必须写）

容错:
    任何异常均 catch → 写 meta.json (status="error") → exit 0
    Go 后端通过解析 meta.json 判断成功/失败，不依赖 exit code
"""

import sys
import os
import glob
import time
import json
import traceback

import numpy as np
import cv2

# ===================== 常量 =====================

MAX_SIZE = 2000        # 预处理缩放最长边阈值
CONFIDENCE = 0.6       # 匹配置信度阈值
RESULT_MAX_EDGE = 4000 # 全景图最长边限制


# ===================== 文件 I/O =====================

def load_images(input_dir):
    """
    从 input/ 目录批量读取图片，按文件名升序排序.
    返回 (images, errors)：
      images  -- 成功加载的 cv2 图片列表
      errors  -- 跳过的文件及原因 [(filename, reason), ...]
    """
    if not os.path.isdir(input_dir):
        raise FileNotFoundError(f"输入目录不存在: {input_dir}")

    exts = ('*.jpg', '*.jpeg', '*.png', '*.JPG', '*.JPEG', '*.PNG')
    img_paths = []
    for ext in exts:
        img_paths.extend(glob.glob(os.path.join(input_dir, ext)))
    img_paths = sorted(img_paths)

    if not img_paths:
        raise ValueError(f"输入目录中未找到图片文件: {input_dir}")

    images = []
    errors = []

    for path in img_paths:
        filename = os.path.basename(path)
        try:
            img = cv2.imdecode(np.fromfile(path, dtype=np.uint8), cv2.IMREAD_COLOR)
            if img is None:
                errors.append((filename, "无法解码，文件可能已损坏"))
                continue

            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            if np.count_nonzero(gray > 10) < 500:
                errors.append((filename, "有效像素过少，疑似纯色/空白图"))
                continue

            # 预处理缩放
            h, w = img.shape[:2]
            if max(h, w) > MAX_SIZE:
                scale = MAX_SIZE / max(h, w)
                new_w, new_h = int(w * scale), int(h * scale)
                img = cv2.resize(img, (new_w, new_h), interpolation=cv2.INTER_AREA)

            images.append(img)
        except Exception as e:
            errors.append((filename, f"读取异常: {e}"))

    return images, errors


def write_result(result_dir, pano):
    """将全景图写入 result/result.jpg，失败时抛出 IOError"""
    result_path = os.path.join(result_dir, "result.jpg")
    success = cv2.imwrite(result_path, pano)
    if not success:
        raise IOError(f"写入拼接结果失败: {result_path}")
    return result_path


def write_meta(result_dir, status, keypoints, cost_ms, error):
    """
    写 meta.json 到 result/ 目录.
    status: "ok" | "error"
    失败时也确保写入 —— 这是 Go 后端判断任务结果的唯一依据.
    """
    meta = {
        "status": status,
        "keypoints": keypoints,
        "cost_ms": cost_ms,
        "error": error,
    }
    # 确保 result/ 存在（Go 后端正常会创建，此处兜底）
    os.makedirs(result_dir, exist_ok=True)
    meta_path = os.path.join(result_dir, "meta.json")
    try:
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False, indent=2)
    except Exception as e:
        # meta.json 写失败是最坏情况 —— Go 后端无法解析任务结果
        # 尽力写到 stderr 供运维排查
        print(f"严重: 写入 meta.json 失败: {e}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)


# ===================== 图像处理 =====================

def count_keypoints(images):
    """
    对每张图做 SIFT 特征检测，返回总特征点数.
    SIFT 不可用时回退到 ORB.
    仅用于前端展示，不影响拼接流程.
    """
    total = 0
    try:
        detector = cv2.SIFT_create()
    except AttributeError:
        # opencv-python-headless 可能不含 SIFT（non-free 模块）
        detector = cv2.ORB_create()

    for img in images:
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        kp = detector.detect(gray, None)
        total += len(kp)
    return total


def crop_black_border(img):
    """自动裁剪四周全黑区域"""
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    pts = cv2.findNonZero(gray)
    if pts is None:
        return img
    x, y, w, h = cv2.boundingRect(pts)
    return img[y:y + h, x:x + w]


def resize_if_needed(img, max_edge=RESULT_MAX_EDGE):
    """限制全景图最长边不超过 max_edge"""
    h, w = img.shape[:2]
    if max(h, w) > max_edge:
        scale = max_edge / max(h, w)
        new_w, new_h = int(w * scale), int(h * scale)
        return cv2.resize(img, (new_w, new_h), interpolation=cv2.INTER_AREA)
    return img


# ===================== 拼接核心 =====================

def stitch_images(images, confidence=CONFIDENCE):
    """
    使用 OpenCV Stitcher 拼接.
    球面模式(PANORAMA)失败后自动回退平面模式(SCAN).
    """
    # ---- 球面拼接 ----
    stitcher = cv2.Stitcher.create(cv2.Stitcher_PANORAMA)
    if hasattr(stitcher, 'setPanoConfidenceThresh'):
        stitcher.setPanoConfidenceThresh(confidence)
    status, pano = stitcher.stitch(images)

    # ---- 回退：平面拼接 ----
    if status != cv2.Stitcher_OK:
        stitcher2 = cv2.Stitcher.create(cv2.Stitcher_SCAN)
        if hasattr(stitcher2, 'setPanoConfidenceThresh'):
            stitcher2.setPanoConfidenceThresh(confidence)
        status, pano = stitcher2.stitch(images)

    # ---- 错误码映射 ----
    if status != cv2.Stitcher_OK:
        err_map = {
            cv2.Stitcher_ERR_NEED_MORE_IMGS:
                "需要更多图像（图片间重叠区域不足或特征点太少）",
            cv2.Stitcher_ERR_HOMOGRAPHY_EST_FAIL:
                "单应矩阵估计失败（图片间匹配关系不稳定）",
            cv2.Stitcher_ERR_CAMERA_PARAMS_ADJUST_FAIL:
                "相机参数调整失败（图片视角差异过大或排列不合理）",
        }
        reason = err_map.get(status, f"OpenCV 拼接失败 (错误码 {status})")
        raise RuntimeError(reason)

    return pano


# ===================== 主程序 =====================

def main():
    if len(sys.argv) != 2:
        print("用法: python3 stitch.py {任务目录}", file=sys.stderr)
        sys.exit(0)

    task_dir = sys.argv[1]
    input_dir = os.path.join(task_dir, "input")
    result_dir = os.path.join(task_dir, "result")

    start_time = time.time()
    keypoints = 0
    status = "ok"
    error = ""

    try:
        # ---- 1. 校验任务目录 ----
        if not os.path.isdir(task_dir):
            raise FileNotFoundError(f"任务目录不存在: {task_dir}")

        # ---- 2. 加载图片 ----
        images, load_errors = load_images(input_dir)

        if not images:
            if load_errors:
                reasons = "; ".join(f"{fn}: {r}" for fn, r in load_errors)
                raise ValueError(f"所有图片均无法读取: {reasons}")
            else:
                raise ValueError(f"输入目录中未找到图片文件: {input_dir}")

        if len(images) < 2:
            raise ValueError(
                f"有效图片不足（仅 {len(images)} 张），至少需要 2 张图片才能拼接"
            )

        # ---- 3. 统计特征点 ----
        keypoints = count_keypoints(images)

        # ---- 4. 执行拼接 ----
        pano = stitch_images(images)

        # ---- 5. 后处理 ----
        pano = resize_if_needed(pano)
        pano = crop_black_border(pano)

        # ---- 6. 写入结果 ----
        write_result(result_dir, pano)

    except Exception as e:
        status = "error"
        error = str(e)
        # 拼接失败时确保不残留半成品 result.jpg
        result_path = os.path.join(result_dir, "result.jpg")
        if os.path.exists(result_path):
            try:
                os.remove(result_path)
            except OSError:
                pass

    finally:
        cost_ms = int((time.time() - start_time) * 1000)
        write_meta(result_dir, status, keypoints, cost_ms, error)

    # 无论成功/失败，exit 0；Go 后端以 meta.json 为准
    sys.exit(0)


if __name__ == "__main__":
    main()
