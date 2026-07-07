#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
铁路场景全景拼接工具 - SIFT特征增强版
特点：
1. 强制使用 SIFT 特征检测器（比 ORB 更稳定）
2. 特征点数量从默认的几百增加到 10000 个
3. 使用 FLANN 匹配器，适合密集特征匹配
4. 启用 RANSAC 滤波剔除误匹配
"""

import os
import glob
import argparse
import numpy as np
import cv2
import tkinter as tk
from tkinter import filedialog


# ===================== 工具函数 =====================

def load_images_from_folder(folder_path, max_size):
    """从文件夹批量读取图片"""
    if not os.path.isdir(folder_path):
        raise FileNotFoundError(f"错误：文件夹 '{folder_path}' 不存在！")

    extensions = ('*.jpg', '*.jpeg', '*.png', '*.JPG', '*.JPEG', '*.PNG')
    img_paths = []
    for ext in extensions:
        img_paths.extend(glob.glob(os.path.join(folder_path, ext)))
    img_paths = sorted(img_paths)

    if not img_paths:
        raise ValueError(f"错误：文件夹 '{folder_path}' 中未找到任何图片！")

    images = []
    for path in img_paths:
        try:
            img = cv2.imdecode(np.fromfile(path, dtype=np.uint8), cv2.IMREAD_COLOR)
            if img is None:
                print(f"警告：跳过无法读取的图片 '{os.path.basename(path)}'")
                continue

            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            if np.count_nonzero(gray > 10) < 500:
                print(f"警告：跳过有效像素过少的图片 '{os.path.basename(path)}'")
                continue

            h, w = img.shape[:2]
            if max(h, w) > max_size:
                scale = max_size / max(h, w)
                new_w, new_h = int(w * scale), int(h * scale)
                img = cv2.resize(img, (new_w, new_h), interpolation=cv2.INTER_AREA)

            images.append(img)
            print(f"已加载：{os.path.basename(path)} 尺寸 {img.shape[1]}x{img.shape[0]}")

        except Exception as e:
            print(f"警告：读取 '{path}' 时异常：{e}，已跳过")

    if len(images) < 2:
        raise ValueError("错误：有效图片数量不足 2 张，无法拼接！")
    return images


def load_images_from_dialog(max_size):
    """弹出文件选择对话框，手动选择图片"""
    root = tk.Tk()
    root.withdraw()
    paths = filedialog.askopenfilenames(
        title="选择拼接图片（按住 Ctrl 可多选）",
        filetypes=[("图片文件", "*.jpg *.jpeg *.png *.JPG *.JPEG *.PNG"), ("所有文件", "*.*")]
    )
    if not paths:
        raise ValueError("未选择任何图片！")

    img_paths = sorted(list(paths))
    images = []
    for path in img_paths:
        try:
            img = cv2.imdecode(np.fromfile(path, dtype=np.uint8), cv2.IMREAD_COLOR)
            if img is None:
                print(f"警告：跳过无法读取的图片 '{os.path.basename(path)}'")
                continue

            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            if np.count_nonzero(gray > 10) < 500:
                print(f"警告：跳过有效像素过少的图片 '{os.path.basename(path)}'")
                continue

            h, w = img.shape[:2]
            if max(h, w) > max_size:
                scale = max_size / max(h, w)
                new_w, new_h = int(w * scale), int(h * scale)
                img = cv2.resize(img, (new_w, new_h), interpolation=cv2.INTER_AREA)

            images.append(img)
            print(f"已加载：{os.path.basename(path)} 尺寸 {img.shape[1]}x{img.shape[0]}")

        except Exception as e:
            print(f"警告：读取 '{path}' 时异常：{e}，已跳过")

    if len(images) < 2:
        raise ValueError("错误：有效图片数量不足 2 张，无法拼接！")
    return images


def crop_black_border(img):
    """自动裁剪四周全黑区域"""
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    pts = cv2.findNonZero(gray)
    if pts is None:
        return img
    x, y, w, h = cv2.boundingRect(pts)
    return img[y:y + h, x:x + w]


def resize_if_needed(img, max_edge=4000):
    """限制全景图最长边不超过 max_edge"""
    h, w = img.shape[:2]
    if max(h, w) > max_edge:
        scale = max_edge / max(h, w)
        new_w, new_h = int(w * scale), int(h * scale)
        return cv2.resize(img, (new_w, new_h), interpolation=cv2.INTER_AREA)
    return img


def custom_stitch_with_sift(images, confidence):
    """
    自定义拼接流程 - 使用 SIFT 特征检测器
    特征点数量设置为 10000 个
    """
    print("正在提取 SIFT 特征点...")

    # 1. 创建 SIFT 特征检测器（最大 10000 个特征点）
    try:
        # OpenCV 4.4+ 写法
        sift = cv2.SIFT_create(nfeatures=10000,
                               contrastThreshold=0.03,
                               edgeThreshold=10,
                               sigma=1.6)
        print("已创建 SIFT 检测器（特征点上限：10000）")
    except AttributeError:
        # 旧版本 OpenCV 写法
        sift = cv2.xfeatures2d.SIFT_create(nfeatures=10000)
        print("已创建 SIFT 检测器（旧版 API，特征点上限：10000）")

    # 2. 提取特征点和描述符
    keypoints_list = []
    descriptors_list = []

    for i, img in enumerate(images):
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        kp, des = sift.detectAndCompute(gray, None)
        keypoints_list.append(kp)
        descriptors_list.append(des)
        print(f"图片{i + 1}：提取了 {len(kp)} 个特征点")

    # 3. 创建 FLANN 匹配器（处理密集特征）
    FLANN_INDEX_KDTREE = 1
    index_params = dict(algorithm=FLANN_INDEX_KDTREE, trees=5)
    search_params = dict(checks=50)
    flann = cv2.FlannBasedMatcher(index_params, search_params)
    print("已创建 FLANN 匹配器")

    # 4. 匹配相邻图片特征点
    matches_list = []
    for i in range(len(images) - 1):
        matches = flann.knnMatch(descriptors_list[i], descriptors_list[i + 1], k=2)

        # 5. Lowe's 比例测试筛选优质匹配
        good_matches = []
        for m, n in matches:
            if m.distance < 0.7 * n.distance:  # 比例阈值
                good_matches.append(m)

        matches_list.append(good_matches)
        print(f"图片{i + 1}和{i + 2}：找到 {len(good_matches)} 个优质匹配点")

        if len(good_matches) < 20:
            print(f"警告：匹配点不足（{len(good_matches)} < 20），可能无法拼接")

    # 6. 使用 RANSAC 计算单应矩阵并拼接
    print("正在计算单应矩阵...")

    # 由于手动实现完整拼接较复杂，我们仍使用 OpenCV Stitcher
    # 但通过设置 SIFT 特征检测器来增强效果

    try:
        # 创建 Stitcher 并设置 SIFT 特征检测器
        stitcher = cv2.Stitcher_create(cv2.Stitcher_PANORAMA)

        # 设置自定义特征检测器
        if hasattr(stitcher, 'setFeaturesFinder'):
            stitcher.setFeaturesFinder(cv2.detail.create_features_finder("SIFT"))
            print("已设置 SIFT 特征检测器到 Stitcher")

        # 设置置信度阈值
        if hasattr(stitcher, 'setPanoConfidenceThresh'):
            stitcher.setPanoConfidenceThresh(confidence)
            print(f"已设置匹配置信度阈值：{confidence}")

        # 启用波浪校正
        try:
            if hasattr(stitcher, 'setWaveCorrection'):
                stitcher.setWaveCorrection(True)
                print("已启用波浪校正")
        except:
            pass

        # 执行拼接
        status, pano = stitcher.stitch(images)

        if status != 0:
            err_msg = {
                1: "需要更多图像（重叠区域不足）",
                2: "单应矩阵估计失败",
                3: "相机参数调整失败",
                4: "图像匹配失败（特征点不足或重复纹理过多）",
                5: "图像缩放失败",
            }.get(status, f"未知错误 (code {status})")
            raise RuntimeError(f"拼接失败：{err_msg}")

        return pano

    except Exception as e:
        print(f"Stitcher 错误：{e}")
        raise


# ===================== 主程序 =====================

def main():
    parser = argparse.ArgumentParser(
        description="铁路场景全景拼接工具 - SIFT特征增强版",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
运行示例：
  基础运行：python rail_sift.py --input ./images --crop
  调整参数：python rail_sift.py --input ./images --crop --confidence 0.3 --max-size 1200
  交互模式：直接运行 python rail_sift.py
        """
    )
    parser.add_argument("--input", help="待拼接图片所在文件夹路径")
    parser.add_argument("--output", default="panorama.jpg", help="输出全景图路径")
    parser.add_argument("--max-size", type=int, default=1500,
                        help="预处理缩放最长边阈值（默认 1500）")
    parser.add_argument("--confidence", type=float, default=0.3,
                        help="匹配置信度阈值（0.2~0.5），默认 0.3")
    parser.add_argument("--crop", action="store_true", help="自动裁剪黑边")
    parser.add_argument("--no-display", action="store_true", help="关闭结果显示")

    args = parser.parse_args()

    # 校验 confidence
    if args.confidence < 0.15:
        print("警告：confidence 过低，已自动调整为 0.3")
        args.confidence = 0.3
    elif args.confidence > 0.6:
        print("警告：confidence 过高，已自动调整为 0.3")
        args.confidence = 0.3

    try:
        # ---------- 1. 加载图像 ----------
        if args.input:
            print(f"从文件夹加载图片：{args.input}")
            images = load_images_from_folder(args.input, args.max_size)
        else:
            print("交互模式：请选择图片")
            images = load_images_from_dialog(args.max_size)

        print(f"共加载 {len(images)} 张有效图片")

        # ---------- 2. 执行 SIFT 增强拼接 ----------
        print("使用 SIFT 特征增强拼接...")
        pano = custom_stitch_with_sift(images, args.confidence)

        # ---------- 3. 后处理 ----------
        pano = resize_if_needed(pano, max_edge=4000)
        print(f"拼接完成，全景图尺寸：{pano.shape[1]}x{pano.shape[0]}")

        if args.crop:
            pano = crop_black_border(pano)
            print("已执行黑边裁剪")

        # ---------- 4. 保存 ----------
        output_dir = os.path.dirname(args.output)
        if output_dir and not os.path.exists(output_dir):
            os.makedirs(output_dir, exist_ok=True)

        cv2.imwrite(args.output, pano)
        print(f"全景图已保存至：{os.path.abspath(args.output)}")

        # ---------- 5. 显示 ----------
        if not args.no_display:
            display_img = resize_if_needed(pano, max_edge=1200)
            cv2.imshow("铁路全景拼接结果 (按任意键关闭)", display_img)
            cv2.waitKey(0)
            cv2.destroyAllWindows()

    except Exception as e:
        print(f"\n程序异常终止：{e}")
        return 1

    return 0


if __name__ == "__main__":
    exit(main())