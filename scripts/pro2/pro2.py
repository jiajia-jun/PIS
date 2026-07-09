#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
全景图像拼接工具（增强稳定性版）
支持两种启动方式：
  【命令行】python script.py --input ./images ...
  【交互式】直接运行脚本，弹出文件选择框手动选图
改进点：
  - 自动适配：2张图自动平面拼接，3张及以上自动球面全景
  - 自动重试：球面拼接失败时自动尝试平面拼接（SCAN）
  - 默认置信度提升至 0.6，减少误匹配
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
    """从文件夹批量读取图片，按文件名升序排序，自动跳过损坏文件"""
    if not os.path.isdir(folder_path):
        raise FileNotFoundError(f"错误：文件夹 '{folder_path}' 不存在！")

    extensions = ('*.jpg', '*.jpeg', '*.png', '*.JPG', '*.JPEG', '*.PNG')
    img_paths = []
    for ext in extensions:
        img_paths.extend(glob.glob(os.path.join(folder_path, ext)))
    img_paths = sorted(img_paths)

    if not img_paths:
        raise ValueError(f"错误：文件夹 '{folder_path}' 中未找到任何 jpg/png 图片！")

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
            # 预处理缩放
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
    """弹出文件选择对话框，让用户手动选择多张图片，按文件名升序排序"""
    root = tk.Tk()
    root.withdraw()  # 隐藏主窗口
    paths = filedialog.askopenfilenames(
        title="选择拼接图片（按住 Ctrl 可多选）",
        filetypes=[("图片文件", "*.jpg *.jpeg *.png *.JPG *.JPEG *.PNG"), ("所有文件", "*.*")]
    )
    if not paths:
        raise ValueError("未选择任何图片！")

    # 将路径元组转为列表并按文件名排序
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
    return img[y:y+h, x:x+w]


def resize_if_needed(img, max_edge=4000):
    """限制全景图最长边不超过 max_edge"""
    h, w = img.shape[:2]
    if max(h, w) > max_edge:
        scale = max_edge / max(h, w)
        new_w, new_h = int(w * scale), int(h * scale)
        return cv2.resize(img, (new_w, new_h), interpolation=cv2.INTER_AREA)
    return img


def stitch_images(images, mode, confidence):
    """
    使用 OpenCV Stitcher 拼接，若球面模式失败则自动重试平面模式
    """
    # 第一次尝试
    stitcher = cv2.Stitcher.create(mode)
    if hasattr(stitcher, 'setPanoConfidenceThresh'):
        stitcher.setPanoConfidenceThresh(confidence)
        print(f"已设置匹配置信度阈值：{confidence}")
    status, pano = stitcher.stitch(images)

    # 如果失败且当前是球面模式，则自动重试平面模式
    if status != cv2.Stitcher_OK and mode == 0:
        print("球面拼接失败，自动尝试平面拼接（SCAN）模式...")
        stitcher2 = cv2.Stitcher.create(1)
        if hasattr(stitcher2, 'setPanoConfidenceThresh'):
            stitcher2.setPanoConfidenceThresh(confidence)
        status2, pano2 = stitcher2.stitch(images)
        if status2 == cv2.Stitcher_OK:
            print("平面拼接成功！")
            return pano2
        else:
            # 如果平面也失败，则抛出原始错误（球面的错误）
            pass

    if status != cv2.Stitcher_OK:
        err_msg = {
            cv2.Stitcher_ERR_NEED_MORE_IMGS: "需要更多图像（重叠区域不足）",
            cv2.Stitcher_ERR_HOMOGRAPHY_EST_FAIL: "单应矩阵估计失败",
            cv2.Stitcher_ERR_CAMERA_PARAMS_ADJUST_FAIL: "相机参数调整失败",
        }.get(status, f"未知错误 (code {status})")
        raise RuntimeError(f"拼接失败：{err_msg}")

    return pano


# ===================== 主程序 =====================

def main():
    parser = argparse.ArgumentParser(
        description="全景图像拼接工具（支持命令行文件夹模式 & 交互式文件选择）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
运行示例（命令行）：
  横向拼接：python stitch.py --input ./images --output result.jpg --max-size 1500 --crop
  竖向拼接：python stitch.py --input ./images --vertical --output vertical.jpg --crop

交互式（不带任何参数）：
  直接运行 python stitch.py 会弹出文件选择框，手动选图拼接
        """
    )
    parser.add_argument("--input", help="待拼接图片所在文件夹路径（若不提供，则弹出文件选择对话框）")
    parser.add_argument("--output", default="panorama.jpg", help="输出全景图路径，默认 panorama.jpg")
    parser.add_argument("--max-size", type=int, default=2000,
                        help="预处理缩放最长边阈值（默认 2000）")
    parser.add_argument("--confidence", type=float, default=0.6,
                        help="匹配置信度阈值（推荐 0.4~0.6），默认 0.6，禁止低于 0.3")
    parser.add_argument("--crop", action="store_true", help="开启自动裁剪全景四周黑色空白区域")
    parser.add_argument("--no-display", action="store_true", help="关闭拼接完成后的图片弹窗显示")
    parser.add_argument("--vertical", action="store_true",
                        help="竖向上下拼接模式（禁用球面投影，仅使用平面单应矩阵）")

    args = parser.parse_args()

    # 校验 confidence
    if args.confidence < 0.3:
        print("警告：confidence 低于 0.3，容易导致透视扭曲，已自动调整为 0.6")
        args.confidence = 0.6
    elif args.confidence < 0.4 or args.confidence > 0.6:
        print(f"警告：confidence 推荐范围 0.4~0.6，当前 {args.confidence}，继续执行可能效果不佳")

    try:
        # ---------- 1. 加载图像 ----------
        if args.input:
            print(f"命令行模式：从文件夹加载图片：{args.input}")
            images = load_images_from_folder(args.input, args.max_size)
        else:
            print("交互模式：请在弹出的文件对话框中选择图片")
            images = load_images_from_dialog(args.max_size)

        print(f"共加载 {len(images)} 张有效图片")

        # ---------- 2. 模式选择（修改点：按图片数量自动适配） ----------
        if args.vertical:
            print("竖向拼接模式：将图像旋转 90° 后水平拼接，再旋转回来")
            images = [cv2.rotate(img, cv2.ROTATE_90_CLOCKWISE) for img in images]
            stitch_mode = 1
        else:
            if len(images) == 2:
                print("检测到2张图片，自动使用平面拼接模式（画面平直无变形）")
                stitch_mode = cv2.Stitcher_SCANS
            else:
                print(f"检测到{len(images)}张图片，使用球面全景投影（若失败将自动尝试平面拼接）")
                stitch_mode = cv2.Stitcher_PANORAMA

        # ---------- 3. 执行拼接 ----------
        pano = stitch_images(images, stitch_mode, args.confidence)

        if args.vertical:
            pano = cv2.rotate(pano, cv2.ROTATE_90_COUNTERCLOCKWISE)

        # ---------- 4. 后处理 ----------
        pano = resize_if_needed(pano, max_edge=4000)
        print(f"拼接完成，全景图尺寸：{pano.shape[1]}x{pano.shape[0]}")

        if args.crop:
            pano = crop_black_border(pano)
            print("已执行黑边裁剪")

        # ---------- 5. 保存 & 显示 ----------
        cv2.imwrite(args.output, pano)
        print(f"全景图已保存至：{args.output}")

        if not args.no_display:
            display_img = resize_if_needed(pano, max_edge=1200)
            cv2.imshow("全景拼接结果 (按任意键关闭)", display_img)
            cv2.waitKey(0)
            cv2.destroyAllWindows()

    except Exception as e:
        print(f"\n程序异常终止：{e}")
        return 1

    return 0


if __name__ == "__main__":
    exit(main())