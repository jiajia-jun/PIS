#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
全景图像拼接工具
支持两种启动方式：
  【命令行】python script.py --input ./images ...
  【交互式】直接运行脚本，弹出文件选择框手动选图
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
    """使用 OpenCV Stitcher 拼接"""
    stitcher = cv2.Stitcher.create(mode)
    if hasattr(stitcher, 'setPanoConfidenceThresh'):
        stitcher.setPanoConfidenceThresh(confidence)
        print(f"已设置匹配置信度阈值：{confidence}")
    status, pano = stitcher.stitch(images)
    if status != cv2.Stitcher_OK:
        err_msg = {
            cv2.Stitcher_ERR_NEED_MORE_IMGS: "需要更多图像（重叠区域不足）",
            cv2.Stitcher_ERR_HOMOGRAPHY_EST_FAIL: "单应矩阵估计失败",
            cv2.Stitcher_ERR_CAMERA_PARAMS_ADJUST_FAIL: "相机参数调整失败",
        }.get(status, f"未知错误 (code {status})")
        raise RuntimeError(f"拼接失败：{err_msg}")
    return pano



# ===================== 添加的新功能函数 =====================
def calc_feature_matches(img1, img2):
    """
    计算两张图片之间的有效特征匹配点数量（Lowe's Ratio Test 过滤后）
    """
    try:
        # 使用 SIFT 特征点提取（如果 cv2.SIFT_create() 报错，试试 cv2.ORB_create()）
        sift = cv2.SIFT_create()
        kp1, des1 = sift.detectAndCompute(img1, None)
        kp2, des2 = sift.detectAndCompute(img2, None)

        if des1 is None or des2 is None:
            print("⚠️ 警告：未能在其中一张图片上检测到任何特征点。")
            return 0

        # 使用暴力匹配器 (BFMatcher) 进行匹配
        bf = cv2.BFMatcher()
        matches = bf.knnMatch(des1, des2, k=2)

        # 应用 Lowe's 比例测试筛选好的匹配点
        good_matches = []
        for m, n in matches:
            if m.distance < 0.75 * n.distance:
                good_matches.append(m)

        return len(good_matches)
    except Exception as e:
        print(f"⚠️ 计算特征匹配数时出现异常: {e}")
        return -1
# ============================================================

# ===================== 主程序 =====================

def main():
    parser = argparse.ArgumentParser(
        description="全景图像拼接工具（支持命令行文件夹模式 & 交互式文件选择）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
    运行示例（命令行）：
      横向拼接：python stitch.py --input ./images --output result.jpg --max-size 1500 --crop
      竖向拼接：python stitch.py --input ./images --vertical --output vertical.jpg --crop
      平面拼接：python stitch.py --input ./images --scan --output scan_result.jpg

    交互式（不带任何参数）：
      直接运行 python stitch.py 会弹出文件选择框，手动选图拼接
            """
    )
    parser.add_argument("--input", help="待拼接图片所在文件夹路径（若不提供，则弹出文件选择对话框）")
    parser.add_argument("--output", default="panorama.jpg", help="输出全景图路径，默认 panorama.jpg")
    parser.add_argument("--max-size", type=int, default=2000,
                        help="预处理缩放最长边阈值（默认 2000）")
    parser.add_argument("--confidence", type=float, default=0.45,
                        help="匹配置信度阈值（0.4~0.6），默认 0.45，禁止低于 0.3")
    parser.add_argument("--crop", action="store_true", help="开启自动裁剪全景四周黑色空白区域")
    parser.add_argument("--no-display", action="store_true", help="关闭拼接完成后的图片弹窗显示")
    parser.add_argument("--vertical", action="store_true",
                        help="竖向上下拼接模式（禁用球面投影，仅使用平面单应矩阵）")
    # 👇 **必须加上这一行**
    parser.add_argument("--scan", action="store_true",
                        help="强制使用平面扫描拼接模式 (SCAN)，适合平移拍摄的近景图片")

    args = parser.parse_args()

    # 校验 confidence
    if args.confidence < 0.3:
        print("警告：confidence 低于 0.3，容易导致透视扭曲，已自动调整为 0.45")
        args.confidence = 0.45
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


        # ===== [修改处] 插入打印特征点数量的代码 =====
        if len(images) >= 2:
            print("正在计算相邻图片之间的特征匹配点数量...")
            for i in range(len(images) - 1):
                match_count = calc_feature_matches(images[i], images[i+1])
                if match_count >= 0:
                    print(f"📊 图片 {i+1} 与 图片 {i+2} 之间匹配的特征点数量为: {match_count} 个")
        # ============================================


        # ---------- 2. 竖向处理 ----------
        # ---------- 2. 竖向处理 ----------
        if args.vertical:
            print("竖向拼接模式：将图像旋转 90° 后水平拼接，再旋转回来")
            images = [cv2.rotate(img, cv2.ROTATE_90_CLOCKWISE) for img in images]
            stitch_mode = cv2.Stitcher_SCANS  # 注意这里SCAN没有S

        else:
            # 根据图片数量自动选择拼接模式
            if len(images) == 2:
                print("检测到图片数量为 2 张，自动调用平面扫描拼接模式 (SCAN)")
                stitch_mode = cv2.Stitcher_SCANS  # 注意这里SCAN没有S
            else:
                print("检测到图片数量大于 2 张，优先调用球面投影模式 (PANORAMA)")
                stitch_mode = cv2.Stitcher_PANORAMA

        # ---------- 3. 执行拼接 ----------
        try:
            # 第一轮：按照设定的模式尝试拼接
            pano = stitch_images(images, stitch_mode, args.confidence)
        except RuntimeError as e:
            # 如果报错，检查错误信息
            if "相机参数调整失败" in str(e):
                print("\n⚠️ 警告：球面投影模式(PANORAMA)无法处理此平移拍摄的图片！")
                print("🔄 正在自动切换到平面扫描模式(SCAN)重新尝试拼接...")

                # 确保模式是对的（避免之前写的 SCANS 错误）
                stitch_mode = cv2.Stitcher_SCANS
                # 第二张牌：用 SCAN 模式重新拼一遍
                pano = stitch_images(images, stitch_mode, args.confidence)
            else:
                # 如果不仅是相机参数问题，直接抛出原错误
                raise e

        # 竖向拼接模式的后续旋转（保持原样）
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