# -*- coding: utf-8 -*-
import cv2
import numpy as np
import os
import json
import csv
import argparse
import sys
import signal
import base64
import io
import pickle
from datetime import datetime
from typing import List, Dict, Tuple, Optional, Any, Union
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from skimage.metrics import structural_similarity

# ===================== Configuration =====================
CONFIG = {
    "result_img": "result.jpg",
    "result_img_fallback": "panorama.jpg",
    "result_json": "result_info.json",
    "h_file": "H.npy",
    "inliers_file": "inliers.npy",
    "input_dir": "input",
    "result_dir": "result",
    "default_csv": "\u5168\u666f\u62fc\u63a5\u8bc4\u4f30\u7ed3\u679c.csv",
    "default_chart_dir": "\u8bc4\u4f30\u56fe\u8868",
    "default_report": "\u8bc4\u4f30\u6458\u8981\u62a5\u544a.md",
    "image_extensions": ('.jpg', '.jpeg', '.png', '.bmp', '.tiff'),
    "chart_colors": {
        "inlier_ratio": "#4e79a7",
        "rmse": "#e15759",
        "ssim": "#59a14f",
        "time": "#f28e2b",
        "sharpness": "#76b7b2",
        "canvas": "#edc948"
    },
    "chart_dpi": 300,
    "chart_figsize": (10, 6),
    "font_family": ["SimHei", "Microsoft YaHei", "WenQuanYi Micro Hei", "DejaVu Sans"],
    "radar_dimensions": [
        "\u5339\u914d\u8d28\u91cf",
        "\u5bf9\u9f50\u7cbe\u5ea6",
        "\u91cd\u53e0\u4e00\u81f4\u6027",
        "\u753b\u5e03\u5229\u7528\u7387",
        "\u6e05\u6670\u5ea6",
        "\u8fd0\u884c\u6548\u7387"
    ],
    "color_enabled": True,
}


def _color_text(text, color):
    if not CONFIG["color_enabled"]:
        return text
    colors = {
        "red": "\033[91m",
        "green": "\033[92m",
        "yellow": "\033[93m",
        "blue": "\033[94m",
        "cyan": "\033[96m",
        "reset": "\033[0m"
    }
    return colors.get(color, '') + text + colors['reset']


def _ensure_absolute_path(path):
    return str(Path(path).resolve())


def _safe_imread(path):
    try:
        if not os.path.exists(path):
            return None
        img = cv2.imdecode(np.fromfile(path, dtype=np.uint8), cv2.IMREAD_COLOR)
        return img
    except Exception:
        return None


def _safe_float(val, default=None):
    if val == "-" or val is None:
        return default
    try:
        return float(val)
    except (ValueError, TypeError):
        return default


def _is_missing(val):
    return val == "-" or val is None


def _fmt_pct(val, decimals=0, missing_display="-"):
    f = _safe_float(val)
    if f is None:
        return missing_display
    return f"{f:.{decimals}%}"


def _fmt_float(val, decimals=2, missing_display="-"):
    f = _safe_float(val)
    if f is None:
        return missing_display
    return f"{f:.{decimals}f}"


_METRIC_FIELD_ORDER = [
    "\u7528\u4f8b\u540d\u79f0", "\u72b6\u6001",
    "\u603b\u5339\u914d\u5bf9\u6570", "RANSAC\u5185\u70b9\u6570", "\u5185\u70b9\u7387",
    "\u91cd\u6295\u5f71RMSE(\u50cf\u7d20)", "\u91cd\u6295\u5f71\u4e2d\u4f4d\u6570(\u50cf\u7d20)", "\u91cd\u6295\u5f71P95(\u50cf\u7d20)",
    "\u5168\u666fSSIM", "\u91cd\u53e0\u533aPSNR", "\u91cd\u53e0\u533aMAE",
    "\u6709\u6548\u753b\u5e03\u5360\u6bd4", "\u5168\u666f\u56fe\u5bbd\u9ad8\u6bd4",
    "\u6e05\u6670\u5ea6\u4fdd\u6301\u7387", "\u5e73\u5747\u68af\u5ea6\u6bd4",
    "\u603b\u8017\u65f6(\u79d2)",
    "\u5206\u6570_\u5339\u914d\u8d28\u91cf", "\u5206\u6570_\u51e0\u4f55\u7cbe\u5ea6", "\u5206\u6570_\u91cd\u53e0\u4e00\u81f4\u6027",
    "\u5206\u6570_\u753b\u5e03\u5229\u7528\u7387", "\u5206\u6570_\u6e05\u6670\u5ea6", "\u5206\u6570_\u8fd0\u884c\u901f\u5ea6", "\u5206\u6570_\u7efc\u5408\u5f97\u5206",
    "\u9519\u8bef\u4fe1\u606f", "\u8b66\u544a"
]


def _metrics_to_table_json(results_list, title="\u5168\u666f\u62fc\u63a5\u8bc4\u4f30\u7ed3\u679c"):
    """
    将metrics字典列表转换为表格形式JSON：{title, headers, rows}
    :param results_list: metrics字典列表
    :param title: 表格标题
    :return: 表格格式字典
    """
    if not results_list:
        return {"title": title, "headers": [], "rows": []}

    ordered_fields = []
    field_set = set()
    for f in _METRIC_FIELD_ORDER:
        for r in results_list:
            if f in r and f not in field_set:
                ordered_fields.append(f)
                field_set.add(f)
                break
    for r in results_list:
        for k in r.keys():
            if k not in field_set:
                ordered_fields.append(k)
                field_set.add(k)

    rows = []
    for r in results_list:
        row = []
        for f in ordered_fields:
            val = r.get(f, "-")
            if isinstance(val, float):
                val = round(val, 6)
            row.append(val)
        rows.append(row)

    return {
        "title": title,
        "headers": ordered_fields,
        "rows": rows
    }


def _validate_case_structure(case_path):
    missing = []
    guidance_parts = []

    input_dir = os.path.join(case_path, CONFIG["input_dir"])
    result_dir = os.path.join(case_path, CONFIG["result_dir"])

    if not os.path.isdir(case_path):
        return False, [], "\u7528\u4f8b\u76ee\u5f55\u4e0d\u5b58\u5728\uff1a" + case_path

    if not os.path.isdir(input_dir):
        missing.append(CONFIG["input_dir"] + "/")
        guidance_parts.append("\u7f3a\u5c11\u8f93\u5165\u56fe\u7247\u76ee\u5f55")
    else:
        imgs = [f for f in os.listdir(input_dir)
                if f.lower().endswith(CONFIG["image_extensions"])]
        if len(imgs) < 2:
            missing.append(CONFIG["input_dir"] + "/")
            guidance_parts.append("\u8f93\u5165\u56fe\u7247\u6570\u91cf\u4e0d\u8db3\uff0c\u81f3\u5c11\u9700\u89812\u5f20")

    if not os.path.isdir(result_dir):
        missing.append(CONFIG["result_dir"] + "/")
        guidance_parts.append("\u7f3a\u5c11\u7ed3\u679c\u76ee\u5f55")
    else:
        result_img_path = os.path.join(result_dir, CONFIG["result_img"])
        result_img_fallback_path = os.path.join(result_dir, CONFIG["result_img_fallback"])
        if not os.path.exists(result_img_path) and not os.path.exists(result_img_fallback_path):
            missing.append(CONFIG["result_dir"] + "/" + CONFIG["result_img"])
            guidance_parts.append("\u7f3a\u5c11\u5168\u666f\u62fc\u63a5\u7ed3\u679c\u56fe")

        optional_files = [CONFIG["result_json"], CONFIG["h_file"], CONFIG["inliers_file"]]
        for f in optional_files:
            if not os.path.exists(os.path.join(result_dir, f)):
                guidance_parts.append(f"\u53ef\u9009\u6587\u4ef6 {f} \u7f3a\u5931\uff0c\u5bf9\u5e94\u6307\u6807\u5c06\u8df3\u8fc7")

    is_valid = len(missing) == 0
    guidance = ""
    if guidance_parts:
        guidance = "\u4fee\u590d\u6307\u5f15\uff1a\n" + "\n".join("  - " + g for g in guidance_parts)

    return is_valid, missing, guidance


def _validate_result_json(info):
    required_fields = ["total_matches", "inlier_num"]
    missing = [f for f in required_fields if f not in info]
    return len(missing) == 0, missing


class PanoramaEvaluator:
    """
    \u5355\u4e2a\u6d4b\u8bd5\u7528\u4f8b\u8bc4\u4f30\u5668
    \u8ba1\u7b97\u4e94\u5927\u7c7b\u5ba2\u89c2\u8bc4\u4ef7\u6307\u6807\uff1a
    1. \u5339\u914d\u8d28\u91cf\u6307\u6807
    2. \u51e0\u4f55\u914d\u51c6\u6307\u6807
    3. \u91cd\u53e0\u533a\u4e00\u81f4\u6027\u6307\u6807
    4. \u753b\u5e03\u5229\u7528\u7387\u6307\u6807
    5. \u6e05\u6670\u5ea6\u6307\u6807
    """

    def __init__(self, case_path, quick_mode=False):
        self.case_path = _ensure_absolute_path(case_path)
        self.quick_mode = quick_mode
        self.input_path = os.path.join(self.case_path, CONFIG["input_dir"])
        self.result_path = os.path.join(self.case_path, CONFIG["result_dir"])

        is_valid, missing, guidance = _validate_case_structure(self.case_path)
        if not is_valid:
            err_msg = "\u7528\u4f8b\u76ee\u5f55\u7ed3\u6784\u4e0d\u5b8c\u6574\uff1a" + self.case_path + "\n"
            if missing:
                err_msg += "\u7f3a\u5931\u9879\uff1a" + ", ".join(missing) + "\n"
            err_msg += guidance
            raise FileNotFoundError(err_msg)

        self._load_data()

    def _load_data(self):
        json_path = os.path.join(self.result_path, CONFIG["result_json"])
        self.info = {}
        try:
            if os.path.exists(json_path):
                with open(json_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                # 新格式：有 pairs 数组（stitch.py 产出）；旧格式：顶层 total_matches+inlier_num
                if "pairs" in data:
                    self.info = data
                else:
                    json_valid, _ = _validate_result_json(data)
                    if json_valid:
                        self.info = data
        except Exception:
            self.info = {}

        h_path = os.path.join(self.result_path, CONFIG["h_file"])
        inliers_path = os.path.join(self.result_path, CONFIG["inliers_file"])

        # 优先读取多对格式（stitch.py 新产出），兼容旧单对格式
        h_list_path = os.path.join(self.result_path, "H_list.npy")
        self.H_list = []
        self.H = None
        try:
            if os.path.exists(h_list_path):
                h_data = np.load(h_list_path, allow_pickle=True)
                if h_data.ndim == 3 and h_data.shape[1:] == (3, 3):
                    self.H_list = [h_data[i] for i in range(h_data.shape[0])]
            elif os.path.exists(h_path):
                h_data = np.load(h_path, allow_pickle=True)
                if h_data.shape == (3, 3):
                    self.H_list = [h_data]
        except Exception:
            self.H_list = []
        if self.H_list:
            self.H = self.H_list[0]

        inl_pkl = os.path.join(self.result_path, "inliers_list.pkl")
        self.inliers_list = []
        self.inliers = None
        try:
            if os.path.exists(inl_pkl):
                with open(inl_pkl, "rb") as f:
                    inliers_data = pickle.load(f)
                if isinstance(inliers_data, list):
                    self.inliers_list = [arr for arr in inliers_data
                                         if isinstance(arr, np.ndarray)
                                         and arr.ndim == 2 and arr.shape[1] == 4 and len(arr) > 0]
            elif os.path.exists(inliers_path):
                inlier_data = np.load(inliers_path, allow_pickle=True)
                if inlier_data.ndim == 2 and inlier_data.shape[1] == 4 and len(inlier_data) > 0:
                    self.inliers_list = [inlier_data]
        except Exception:
            self.inliers_list = []
        if self.inliers_list:
            self.inliers = self.inliers_list[0]

        try:
            img_list = sorted([
                f for f in os.listdir(self.input_path)
                if f.lower().endswith(CONFIG["image_extensions"])
            ])
            self.img_paths = [os.path.join(self.input_path, f) for f in img_list]
        except Exception as e:
            raise IOError("\u626b\u63cf\u8f93\u5165\u56fe\u7247\u76ee\u5f55\u5931\u8d25\uff1a" + str(e))

        if len(self.img_paths) < 2:
            raise ValueError("\u8f93\u5165\u56fe\u7247\u6570\u91cf\u4e0d\u8db3\uff0c\u81f3\u5c11\u9700\u89812\u5f20")

        # 加载所有源图片（支持 N>=2 张），向后兼容保留 img1/img2
        self.images = []
        for p in self.img_paths:
            img = _safe_imread(p)
            if img is None:
                raise IOError("读取图片失败：" + p)
            self.images.append(img)
        self.img1 = self.images[0]
        self.img2 = self.images[1]
        pano_path = os.path.join(self.result_path, CONFIG["result_img"])
        if not os.path.exists(pano_path):
            pano_path = os.path.join(self.result_path, CONFIG["result_img_fallback"])
        self.panorama = _safe_imread(pano_path)

        if self.panorama is None:
            raise IOError("读取全景结果图失败")

    def calc_match_metrics(self):
        # \u591a\u56fe\u62fc\u63a5\uff1a\u805a\u5408\u6240\u6709\u76f8\u90bb\u5bf9\u7684\u5339\u914d\u7edf\u8ba1
        pairs = self.info.get("pairs", [])
        if pairs:
            total = sum(p.get("total_matches", 0) for p in pairs)
            inlier = sum(p.get("inlier_num", 0) for p in pairs)
        else:
            total = self.info.get("total_matches", 0)
            inlier = self.info.get("inlier_num", 0)
            if total == 0 and self.inliers is not None:
                inlier = len(self.inliers)

        if total < 0 or inlier < 0:
            total = max(0, total)
            inlier = max(0, inlier)
        ratio = inlier / total if total > 0 else 0.0
        ratio = min(ratio, 1.0)

        return {
            "\u603b\u5339\u914d\u5bf9\u6570": int(total) if total > 0 else "-",
            "RANSAC\u5185\u70b9\u6570": int(inlier),
            "\u5185\u70b9\u7387": round(float(ratio), 4) if total > 0 else "-"
        }

    def _calc_reprojection_for_pair(self, H, inliers):
        """计算单对图片的重投影误差"""
        pts1 = inliers[:, :2].astype(np.float64)
        pts2 = inliers[:, 2:].astype(np.float64)
        if len(pts1) == 0:
            return {"rmse": 0.0, "median": 0.0, "p95": 0.0}

        pts1_homo = np.hstack([pts1, np.ones((len(pts1), 1), dtype=np.float64)])
        pts1_proj_homo = (H @ pts1_homo.T).T
        w = pts1_proj_homo[:, 2:3]
        w[np.abs(w) < 1e-10] = 1e-10
        pts1_proj = pts1_proj_homo[:, :2] / w

        distances = np.linalg.norm(pts1_proj - pts2, axis=1)
        valid_distances = distances[distances < 100]
        if len(valid_distances) == 0:
            valid_distances = distances

        return {
            "rmse": float(np.sqrt(np.mean(valid_distances ** 2))),
            "median": float(np.median(valid_distances)),
            "p95": float(np.percentile(valid_distances, 95)),
        }

    def calc_reprojection_error(self):
        try:
            if not self.H_list or not self.inliers_list:
                return {
                    "重投影RMSE(像素)": "-",
                    "重投影中位数(像素)": "-",
                    "重投影P95(像素)": "-",
                    "_warning": "缺少H矩阵或内点数据，跳过重投影误差计算"
                }

            rmse_vals, med_vals, p95_vals = [], [], []
            for H, inliers in zip(self.H_list, self.inliers_list):
                if H is None or inliers is None:
                    continue
                pair_result = self._calc_reprojection_for_pair(H, inliers)
                rmse_vals.append(pair_result["rmse"])
                med_vals.append(pair_result["median"])
                p95_vals.append(pair_result["p95"])

            if not rmse_vals:
                return {
                    "重投影RMSE(像素)": 0.0,
                    "重投影中位数(像素)": 0.0,
                    "重投影P95(像素)": 0.0
                }

            return {
                "重投影RMSE(像素)": round(float(np.mean(rmse_vals)), 4),
                "重投影中位数(像素)": round(float(np.mean(med_vals)), 4),
                "重投影P95(像素)": round(float(np.mean(p95_vals)), 4)
            }
        except Exception as e:
            raise RuntimeError("计算重投影误差失败：" + str(e))

    def calc_panorama_ssim(self):
        """1像素偏移 SSIM：滑动窗口对比自身微小平移，检测拼接缝/鬼影（不依赖 H 矩阵）"""
        try:
            gray = cv2.cvtColor(self.panorama, cv2.COLOR_BGR2GRAY)

            # 有效区域 mask（排除黑边）
            valid = gray > 10
            valid_rows, valid_cols = np.where(valid)
            if len(valid_rows) < 500:
                return {
                    "全景SSIM": "-",
                    "全景SSIM_min": "-",
                    "全景SSIM_std": "-",
                    "_warning": "全景图有效像素太少，跳过全景SSIM计算"
                }

            r_min, r_max = valid_rows.min(), valid_rows.max()
            c_min, c_max = valid_cols.min(), valid_cols.max()

            # 滑动窗口参数：32×32 窗口，步长 24，覆盖整个有效区域
            WIN = 32
            STRIDE = 24

            ssim_scores = []

            for cy in range(r_min + WIN, r_max - WIN, STRIDE):
                for cx in range(c_min + WIN, c_max - WIN, STRIDE):
                    if not valid[cy, cx]:
                        continue

                    window = gray[cy:cy + WIN, cx:cx + WIN]
                    if window.shape != (WIN, WIN):
                        continue

                    # 水平偏移 1px：原窗口 vs 右移 1px → 检测垂直拼缝
                    w_h = window[:, :-1]
                    w_h_shifted = window[:, 1:]
                    try:
                        s = structural_similarity(w_h, w_h_shifted, data_range=255)
                        ssim_scores.append(float(max(0, s)))
                    except Exception:
                        pass

                    # 垂直偏移 1px：原窗口 vs 下移 1px → 检测水平拼缝
                    w_v = window[:-1, :]
                    w_v_shifted = window[1:, :]
                    try:
                        s = structural_similarity(w_v, w_v_shifted, data_range=255)
                        ssim_scores.append(float(max(0, s)))
                    except Exception:
                        pass

            if not ssim_scores:
                return {"全景SSIM": 0.0, "全景SSIM_min": 0.0, "全景SSIM_std": 0.0,
                        "_warning": "无法采样到有效切片"}

            return {
                "全景SSIM": round(float(np.mean(ssim_scores)), 4),
                "全景SSIM_min": round(float(np.min(ssim_scores)), 4),
                "全景SSIM_std": round(float(np.std(ssim_scores)), 4),
            }
        except Exception as e:
            raise RuntimeError("全景SSIM计算失败：" + str(e))

    @staticmethod
    def _sobel_gradient(gray):
        gx = cv2.Sobel(gray, cv2.CV_64F, 1, 0, ksize=3)
        gy = cv2.Sobel(gray, cv2.CV_64F, 0, 1, ksize=3)
        return np.sqrt(gx ** 2 + gy ** 2)

    def calc_canvas_metrics(self):
        try:
            gray_pano = cv2.cvtColor(self.panorama, cv2.COLOR_BGR2GRAY)
            total = gray_pano.size
            if total == 0:
                return {"\u6709\u6548\u753b\u5e03\u5360\u6bd4": 0.0, "\u7a7a\u767d\u5360\u6bd4": 1.0}

            valid = np.sum(gray_pano > 10)
            valid_ratio = valid / total
            valid_ratio = max(0.0, min(1.0, valid_ratio))

            return {
                "\u6709\u6548\u753b\u5e03\u5360\u6bd4": round(float(valid_ratio), 4),
                "\u7a7a\u767d\u5360\u6bd4": round(float(1 - valid_ratio), 4)
            }
        except Exception as e:
            raise RuntimeError("\u8ba1\u7b97\u753b\u5e03\u5229\u7528\u7387\u5931\u8d25\uff1a" + str(e))

    def calc_sharpness_metrics(self):
        try:
            pano_sharp = self._laplacian_var(self.panorama)

            if self.quick_mode:
                return {
                    "\u5168\u666f\u56fe\u6e05\u6670\u5ea6\u65b9\u5dee": round(float(pano_sharp), 2),
                    "\u539f\u56fe\u5e73\u5747\u6e05\u6670\u5ea6\u65b9\u5dee": 0.0,
                    "\u6e05\u6670\u5ea6\u4fdd\u6301\u7387": 0.0
                }

            src_sharp_list = []
            for p in self.img_paths:
                img = _safe_imread(p)
                if img is not None:
                    src_sharp_list.append(self._laplacian_var(img))

            if len(src_sharp_list) == 0:
                return {
                    "\u5168\u666f\u56fe\u6e05\u6670\u5ea6\u65b9\u5dee": round(float(pano_sharp), 2),
                    "\u539f\u56fe\u5e73\u5747\u6e05\u6670\u5ea6\u65b9\u5dee": 0.0,
                    "\u6e05\u6670\u5ea6\u4fdd\u6301\u7387": 0.0
                }

            avg_src_sharp = np.mean(src_sharp_list)
            retention = pano_sharp / avg_src_sharp if avg_src_sharp > 1e-6 else 0.0

            return {
                "\u5168\u666f\u56fe\u6e05\u6670\u5ea6\u65b9\u5dee": round(float(pano_sharp), 2),
                "\u539f\u56fe\u5e73\u5747\u6e05\u6670\u5ea6\u65b9\u5dee": round(float(avg_src_sharp), 2),
                "\u6e05\u6670\u5ea6\u4fdd\u6301\u7387": round(float(retention), 4)
            }
        except Exception as e:
            raise RuntimeError("\u8ba1\u7b97\u6e05\u6670\u5ea6\u6307\u6807\u5931\u8d25\uff1a" + str(e))

    @staticmethod
    def _laplacian_var(img):
        if img is None or img.size == 0:
            return 0.0
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        return float(np.var(cv2.Laplacian(gray, cv2.CV_64F)))

    def get_all_metrics(self):
        result = {"\u72b6\u6001": "\u6210\u529f"}
        warnings = []

        try:
            result.update(self.calc_match_metrics())
        except Exception as e:
            warnings.append("\u5339\u914d\u8d28\u91cf\u6307\u6807\u8ba1\u7b97\u5931\u8d25\uff1a" + str(e))

        try:
            result.update(self.calc_reprojection_error())
        except Exception as e:
            warnings.append("\u51e0\u4f55\u914d\u51c6\u6307\u6807\u8ba1\u7b97\u5931\u8d25\uff1a" + str(e))

        try:
            pano_ssim = self.calc_panorama_ssim()
            if "_warning" in pano_ssim:
                warnings.append(pano_ssim.pop("_warning"))
            result.update(pano_ssim)
        except Exception as e:
            warnings.append("\u91cd\u53e0\u533a\u6307\u6807\u8ba1\u7b97\u5931\u8d25\uff1a" + str(e))

        try:
            result.update(self.calc_canvas_metrics())
        except Exception as e:
            warnings.append("\u753b\u5e03\u5229\u7528\u7387\u8ba1\u7b97\u5931\u8d25\uff1a" + str(e))

        try:
            result.update(self.calc_sharpness_metrics())
        except Exception as e:
            warnings.append("\u6e05\u6670\u5ea6\u6307\u6807\u8ba1\u7b97\u5931\u8d25\uff1a" + str(e))

        result["\u603b\u8017\u65f6(\u79d2)"] = round(float(self.info.get("total_time", 0)), 4)

        if warnings:
            result["\u8b66\u544a"] = "; ".join(warnings)

        return result

    def get_composite_scores(self, metrics):
        scores = {}
        inlier_ratio = _safe_float(metrics.get("\u5185\u70b9\u7387", 0.0), 0.0)
        scores["\u5339\u914d\u8d28\u91cf"] = inlier_ratio

        # RMSE 归一化：以图像对角线 0.5% 为满分阈值
        img_diag = max(
            np.sqrt(self.images[0].shape[0]**2 + self.images[0].shape[1]**2),
            1.0
        )
        rmse = _safe_float(metrics.get("\u91cd\u6295\u5f71RMSE(\u50cf\u7d20)", img_diag * 0.005), img_diag * 0.005)
        scores["\u5bf9\u9f50\u7cbe\u5ea6"] = max(0.0, 1.0 - rmse / max(img_diag * 0.005, 1.0))

        ssim_val = _safe_float(metrics.get("\u5168\u666fSSIM", 0.0), 0.0)
        scores["\u91cd\u53e0\u4e00\u81f4\u6027"] = ssim_val
        canvas_ratio = _safe_float(metrics.get("\u6709\u6548\u753b\u5e03\u5360\u6bd4", 0.0), 0.0)
        scores["\u753b\u5e03\u5229\u7528\u7387"] = canvas_ratio

        # 清晰度保持率：100% 即为满分（拼接后不应比原图更清晰）
        retention = _safe_float(metrics.get("\u6e05\u6670\u5ea6\u4fdd\u6301\u7387", 0.0), 0.0)
        scores["\u6e05\u6670\u5ea6"] = min(1.0, max(0.0, retention))

        # 运行效率：每张图 10s 为满分基准
        image_count = len(self.images)
        time_budget = max(image_count * 10.0, 1.0)
        t = _safe_float(metrics.get("\u603b\u8017\u65f6(\u79d2)", time_budget), time_budget)
        scores["\u8fd0\u884c\u6548\u7387"] = max(0.0, 1.0 - t / time_budget)

        valid_scores = [v for v in scores.values() if v is not None]
        scores["\u7efc\u5408\u5f97\u5206"] = round(float(np.mean(valid_scores)), 4) if valid_scores else 0.0
        return {k: round(float(v), 4) for k, v in scores.items()}


class BatchTester:
    """
    \u6279\u91cf\u6d4b\u8bd5\u8bc4\u4f30\u5668
    \u5355\u4e2a\u7528\u4f8b\u5931\u8d25\u4e0d\u4e2d\u65ad\u6574\u4f53\u6d41\u7a0b
    """

    def __init__(self, test_root, output_csv=None, output_json=None, show_progress=True):
        self.test_root = _ensure_absolute_path(test_root)
        self.output_csv = _ensure_absolute_path(output_csv or CONFIG["default_csv"])
        if output_json:
            self.output_json = _ensure_absolute_path(output_json)
        else:
            base, ext = os.path.splitext(self.output_csv)
            self.output_json = base + ".json"
        self.show_progress = show_progress
        self.results = []
        self.case_list = []

        if not os.path.isdir(self.test_root):
            raise NotADirectoryError("\u6d4b\u8bd5\u6839\u76ee\u5f55\u4e0d\u5b58\u5728\uff1a" + self.test_root)

        try:
            self.case_list = sorted([
                d for d in os.listdir(self.test_root)
                if os.path.isdir(os.path.join(self.test_root, d))
                and not d.startswith(('_', '.'))
            ])
        except Exception as e:
            raise IOError("\u626b\u63cf\u6d4b\u8bd5\u76ee\u5f55\u5931\u8d25\uff1a" + str(e))

        if len(self.case_list) == 0:
            print(_color_text("\u26a0\ufe0f  \u8b66\u544a\uff1a\u6d4b\u8bd5\u76ee\u5f55\u4e2d\u672a\u53d1\u73b0\u4efb\u4f55\u6d4b\u8bd5\u7528\u4f8b", "yellow"))

    def run(self):
        total = len(self.case_list)
        success_count = 0
        fail_count = 0

        print(_color_text("\n" + "=" * 60, "cyan"))
        print(_color_text("  \u5f00\u59cb\u6279\u91cf\u8bc4\u4f30\uff0c\u5171\u53d1\u73b0 " + str(total) + " \u4e2a\u6d4b\u8bd5\u7528\u4f8b", "cyan"))
        print(_color_text("=" * 60 + "\n", "cyan"))

        for idx, case_name in enumerate(self.case_list, 1):
            case_full_path = os.path.join(self.test_root, case_name)

            if self.show_progress:
                progress = "[" + str(idx) + "/" + str(total) + "]"
                print(progress + " \u6b63\u5728\u8bc4\u4f30\uff1a" + case_name + "...", end=" ", flush=True)

            try:
                eva = PanoramaEvaluator(case_full_path)
                metrics = eva.get_all_metrics()
                metrics["\u7528\u4f8b\u540d\u79f0"] = case_name
                metrics["\u72b6\u6001"] = "\u6210\u529f"

                composite = eva.get_composite_scores(metrics)
                for k, v in composite.items():
                    metrics["\u5206\u6570_" + k] = round(v, 4)

                self.results.append(metrics)
                success_count += 1

                if self.show_progress:
                    status_icon = _color_text("\u2705", "green")
                    inlier_rate = metrics.get("\u5185\u70b9\u7387", 0)
                    rmse = metrics.get("\u91cd\u6295\u5f71RMSE(\u50cf\u7d20)", 0)
                    print(status_icon + " \u5b8c\u6210 (\u5185\u70b9\u7387={}, RMSE={}px)".format(
                        _fmt_pct(inlier_rate, 0), _fmt_float(rmse, 2)
                    ))

            except Exception as e:
                fail_count += 1
                error_msg = str(e)
                self.results.append({
                    "\u7528\u4f8b\u540d\u79f0": case_name,
                    "\u72b6\u6001": "\u5931\u8d25",
                    "\u9519\u8bef\u4fe1\u606f": error_msg
                })
                if self.show_progress:
                    print(_color_text("\u274c \u5931\u8d25", "red"))
                    first_line = error_msg.split("\n")[0] if "\n" in error_msg else error_msg
                    print("      \u539f\u56e0\uff1a" + first_line)

        self._save_csv()
        self._save_json()

        print(_color_text("\n" + "=" * 60, "cyan"))
        print(_color_text("  \u6279\u91cf\u8bc4\u4f30\u5b8c\u6210\uff01", "cyan"))
        print(_color_text("=" * 60, "cyan"))
        print("  \u603b\u8ba1\uff1a" + str(total) + " \u4e2a\u7528\u4f8b")
        print("  \u6210\u529f\uff1a" + _color_text(str(success_count), "green") + " \u4e2a")
        print("  \u5931\u8d25\uff1a" + _color_text(str(fail_count), "red") + " \u4e2a")
        print("  JSON\u62a5\u544a\uff1a" + self.output_json)
        print("  CSV\u62a5\u544a\uff1a" + self.output_csv)
        print()

        return self.results

    def _save_csv(self):
        if not self.results:
            print(_color_text("\u65e0\u8bc4\u4f30\u7ed3\u679c\u53ef\u4fdd\u5b58", "yellow"))
            return

        fields = ["\u7528\u4f8b\u540d\u79f0", "\u72b6\u6001"]
        for res in self.results:
            for k in res.keys():
                if k not in fields:
                    fields.append(k)

        for end_field in ["\u9519\u8bef\u4fe1\u606f", "\u8b66\u544a"]:
            if end_field in fields:
                fields.remove(end_field)
                fields.append(end_field)

        try:
            out_dir = os.path.dirname(self.output_csv)
            if out_dir and not os.path.exists(out_dir):
                os.makedirs(out_dir, exist_ok=True)

            with open(self.output_csv, "w", encoding="utf-8-sig", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=fields, extrasaction='ignore')
                writer.writeheader()
                writer.writerows(self.results)
        except Exception as e:
            print(_color_text("\u4fdd\u5b58CSV\u5931\u8d25\uff1a" + str(e), "red"))

    def _save_json(self):
        if not self.results:
            empty_table = {"title": "\u5168\u666f\u62fc\u63a5\u8bc4\u4f30\u7ed3\u679c", "headers": [], "rows": []}
            try:
                out_dir = os.path.dirname(self.output_json)
                if out_dir and not os.path.exists(out_dir):
                    os.makedirs(out_dir, exist_ok=True)
                with open(self.output_json, "w", encoding="utf-8") as f:
                    json.dump(empty_table, f, ensure_ascii=False, indent=2)
            except Exception:
                pass
            return

        for r in self.results:
            if "\u72b6\u6001" not in r:
                r["\u72b6\u6001"] = "\u6210\u529f" if "\u9519\u8bef\u4fe1\u606f" not in r else "\u5931\u8d25"

        table_result = _metrics_to_table_json(self.results, title="\u5168\u666f\u62fc\u63a5\u8bc4\u4f30\u7ed3\u679c")

        try:
            out_dir = os.path.dirname(self.output_json)
            if out_dir and not os.path.exists(out_dir):
                os.makedirs(out_dir, exist_ok=True)

            tmp_json = self.output_json + ".tmp"
            with open(tmp_json, "w", encoding="utf-8") as f:
                json.dump(table_result, f, ensure_ascii=False, indent=2)
            os.replace(tmp_json, self.output_json)
        except Exception as e:
            print(_color_text("\u4fdd\u5b58JSON\u5931\u8d25\uff1a" + str(e), "red"))


class QuickEvaluator:
    """
    \u5feb\u901f\u8bc4\u4f30\u5668
    \u65e0\u9700\u642d\u5efa\u5b8c\u6574\u76ee\u5f55\u7ed3\u6784\uff0c\u76f4\u63a5\u4f20\u5165\u56fe\u7247\u5373\u53ef\u8bc4\u4f30
    """

    def __init__(self, img1_path, img2_path, panorama_path, H=None, total_matches=0, inlier_num=0):
        self.img1_path = _ensure_absolute_path(img1_path)
        self.img2_path = _ensure_absolute_path(img2_path)
        self.panorama_path = _ensure_absolute_path(panorama_path)
        self.H = H
        self.total_matches = total_matches
        self.inlier_num = inlier_num

        self.img1 = _safe_imread(self.img1_path)
        self.img2 = _safe_imread(self.img2_path)
        self.panorama = _safe_imread(self.panorama_path)

        if self.img1 is None:
            raise IOError("\u8bfb\u53d6\u56fe\u72471\u5931\u8d25\uff1a" + self.img1_path)
        if self.img2 is None:
            raise IOError("\u8bfb\u53d6\u56fe\u72472\u5931\u8d25\uff1a" + self.img2_path)
        if self.panorama is None:
            raise IOError("\u8bfb\u53d6\u5168\u666f\u56fe\u5931\u8d25\uff1a" + self.panorama_path)

    def evaluate(self):
        result = {"\u72b6\u6001": "\u6210\u529f", "\u8bc4\u4f30\u6a21\u5f0f": "\u5feb\u901f\u8bc4\u4f30"}
        warnings = []

        total = self.total_matches
        inlier = self.inlier_num
        ratio = inlier / total if total > 0 else 0.0
        result["\u603b\u5339\u914d\u5bf9\u6570"] = int(total)
        result["RANSAC\u5185\u70b9\u6570"] = int(inlier)
        result["\u5185\u70b9\u7387"] = round(ratio, 4)

        result["\u91cd\u6295\u5f71RMSE(\u50cf\u7d20)"] = "-"
        result["\u91cd\u6295\u5f71\u4e2d\u4f4d\u6570(\u50cf\u7d20)"] = "-"
        result["\u91cd\u6295\u5f71P95(\u50cf\u7d20)"] = "-"
        if self.H is None:
            warnings.append("\u672a\u63d0\u4f9b\u5355\u5e94\u6027\u77e9\u9635H\uff0c\u90e8\u5206\u6307\u6807\u8df3\u8fc7")

        result["\u91cd\u53e0\u533a\u68af\u5ea6MAE"] = "-"

        try:
            if self.H is not None:
                h, w = self.img1.shape[:2]
                img2_warped = cv2.warpPerspective(self.img2, self.H, (w, h))
                gray1 = cv2.cvtColor(self.img1, cv2.COLOR_BGR2GRAY)
                gray2_warped = cv2.cvtColor(img2_warped, cv2.COLOR_BGR2GRAY)
                mask1 = (gray1 > 0).astype(np.uint8)
                mask2 = (gray2_warped > 0).astype(np.uint8)
                overlap_mask = cv2.bitwise_and(mask1, mask2)
                overlap_count = cv2.countNonZero(overlap_mask)

                if overlap_count > 0:
                    overlap_px1 = gray1[overlap_mask == 1].astype(np.float64)
                    overlap_px2 = gray2_warped[overlap_mask == 1].astype(np.float64)
                    mae = np.mean(np.abs(overlap_px1 - overlap_px2))
                    rmse_val = np.sqrt(np.mean((overlap_px1 - overlap_px2) ** 2))
                    try:
                        ssim_score = structural_similarity(gray1, gray2_warped, mask=overlap_mask, data_range=255)
                    except Exception:
                        ssim_score = 0.0
                    result["\u91cd\u53e0\u533a\u7070\u5ea6MAE"] = round(float(mae), 4)
                    result["\u91cd\u53e0\u533a\u7070\u5ea6RMSE"] = round(float(rmse_val), 4)
                    result["\u5168\u666fSSIM"] = round(float(max(0, ssim_score)), 4)
                else:
                    result["\u91cd\u53e0\u533a\u7070\u5ea6MAE"] = "-"
                    result["\u91cd\u53e0\u533a\u7070\u5ea6RMSE"] = "-"
                    result["\u5168\u666fSSIM"] = "-"
                    warnings.append("\u672a\u68c0\u6d4b\u5230\u91cd\u53e0\u533a\u57df")
            else:
                result["\u91cd\u53e0\u533a\u7070\u5ea6MAE"] = "-"
                result["\u91cd\u53e0\u533a\u7070\u5ea6RMSE"] = "-"
                result["\u5168\u666fSSIM"] = "-"
        except Exception as e:
            result["\u91cd\u53e0\u533a\u7070\u5ea6MAE"] = "-"
            result["\u91cd\u53e0\u533a\u7070\u5ea6RMSE"] = "-"
            result["\u5168\u666fSSIM"] = "-"
            warnings.append("\u91cd\u53e0\u533a\u8ba1\u7b97\u5931\u8d25\uff1a" + str(e))

        try:
            gray_pano = cv2.cvtColor(self.panorama, cv2.COLOR_BGR2GRAY)
            total_px = gray_pano.size
            valid = np.sum(gray_pano > 10)
            valid_ratio = valid / total_px if total_px > 0 else 0
            result["\u6709\u6548\u753b\u5e03\u5360\u6bd4"] = round(float(valid_ratio), 4)
            result["\u7a7a\u767d\u5360\u6bd4"] = round(float(1 - valid_ratio), 4)
        except Exception as e:
            result["\u6709\u6548\u753b\u5e03\u5360\u6bd4"] = "-"
            result["\u7a7a\u767d\u5360\u6bd4"] = "-"
            warnings.append("\u753b\u5e03\u5229\u7528\u7387\u8ba1\u7b97\u5931\u8d25\uff1a" + str(e))

        try:
            pano_sharp = PanoramaEvaluator._laplacian_var(self.panorama)
            s1 = PanoramaEvaluator._laplacian_var(self.img1)
            s2 = PanoramaEvaluator._laplacian_var(self.img2)
            avg_src = (s1 + s2) / 2
            retention = pano_sharp / avg_src if avg_src > 1e-6 else 0
            result["\u5168\u666f\u56fe\u6e05\u6670\u5ea6\u65b9\u5dee"] = round(float(pano_sharp), 2)
            result["\u539f\u56fe\u5e73\u5747\u6e05\u6670\u5ea6\u65b9\u5dee"] = round(float(avg_src), 2)
            result["\u6e05\u6670\u5ea6\u4fdd\u6301\u7387"] = round(float(retention), 4)
        except Exception as e:
            result["\u5168\u666f\u56fe\u6e05\u6670\u5ea6\u65b9\u5dee"] = "-"
            result["\u539f\u56fe\u5e73\u5747\u6e05\u6670\u5ea6\u65b9\u5dee"] = "-"
            result["\u6e05\u6670\u5ea6\u4fdd\u6301\u7387"] = "-"
            warnings.append("\u6e05\u6670\u5ea6\u8ba1\u7b97\u5931\u8d25\uff1a" + str(e))

        result["\u603b\u8017\u65f6(\u79d2)"] = "-"

        if warnings:
            result["\u8b66\u544a"] = "; ".join(warnings)

        return result


# ===================== Web API 工具函数 =====================
# 【新增】用于Web流水线对接的工具函数集

def _validate_image(img: np.ndarray, name: str = "图片") -> None:
    """验证图片numpy数组格式是否正确"""
    if img is None:
        raise ValueError(f"{name}不能为空")
    if not isinstance(img, np.ndarray):
        raise TypeError(f"{name}必须是numpy数组")
    if len(img.shape) not in (2, 3):
        raise ValueError(f"{name}维度错误，期望2D(灰度)或3D(BGR)，实际{len(img.shape)}D")
    if img.dtype != np.uint8:
        raise TypeError(f"{name}数据类型必须是uint8")


def fig_to_base64(fig) -> str:
    """将matplotlib图表转换为base64编码PNG字符串，用于Web前端展示"""
    buf = io.BytesIO()
    fig.savefig(buf, format='png', dpi=CONFIG["chart_dpi"], bbox_inches='tight')
    buf.seek(0)
    img_bytes = buf.getvalue()
    plt.close(fig)
    return base64.b64encode(img_bytes).decode('utf-8')


def img_to_base64(img: np.ndarray, fmt: str = '.png') -> str:
    """将OpenCV图片(numpy数组)转换为base64编码字符串"""
    _validate_image(img)
    if len(img.shape) == 2:
        img = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
    success, encoded = cv2.imencode(fmt, img)
    if not success:
        raise RuntimeError("图片编码失败")
    return base64.b64encode(encoded.tobytes()).decode('utf-8')


def evaluate_image_pair(img1: np.ndarray, img2: np.ndarray,
                        H: Optional[np.ndarray] = None,
                        inliers: Optional[np.ndarray] = None,
                        total_matches: int = 0,
                        inlier_num: int = 0) -> Dict:
    """
    【新增】评估两张相邻图片的拼接质量（可独立调用，用于多图拼接逐对评估）
    :param img1: 图1 (BGR numpy数组)
    :param img2: 图2 (BGR numpy数组)
    :param H: 单应性矩阵 3x3（可选，无H则仅计算无参考指标）
    :param inliers: 内点匹配对 Nx4 数组 [pts1_x, pts1_y, pts2_x, pts2_y]（可选）
    :param total_matches: 总匹配对数（可选）
    :param inlier_num: RANSAC内点数（可选）
    :return: 指标字典
    """
    _validate_image(img1, "图片1")
    _validate_image(img2, "图片2")

    result = {}
    warnings = []

    # ---------- 匹配质量指标 ----------
    if total_matches > 0 or inlier_num > 0:
        ratio = inlier_num / total_matches if total_matches > 0 else 0.0
        result["总匹配对数"] = int(total_matches)
        result["RANSAC内点数"] = int(inlier_num)
        result["内点率"] = round(float(min(ratio, 1.0)), 4)
    elif inliers is not None and len(inliers) > 0:
        result["RANSAC内点数"] = int(len(inliers))
        result["内点率"] = None
        warnings.append("未提供total_matches，内点率无法计算")
    else:
        result["内点率"] = None
        warnings.append("未提供匹配信息，匹配质量指标跳过")

    # ---------- 重投影误差（需H和inliers） ----------
    result["重投影RMSE(像素)"] = None
    result["重投影中位数(像素)"] = None
    result["重投影P95(像素)"] = None

    if H is not None and inliers is not None and len(inliers) > 0:
        try:
            if H.shape != (3, 3):
                warnings.append(f"单应性矩阵维度错误{str(H.shape)}，期望3x3，重投影误差跳过")
            elif len(inliers.shape) != 2 or inliers.shape[1] != 4:
                warnings.append(f"内点维度错误{str(inliers.shape)}，重投影误差跳过")
            else:
                pts1 = inliers[:, :2].astype(np.float64)
                pts2 = inliers[:, 2:].astype(np.float64)
                pts2_homo = np.hstack([pts2, np.ones((len(pts2), 1), dtype=np.float64)])
                pts2_proj_homo = (H @ pts2_homo.T).T
                w = pts2_proj_homo[:, 2:3]
                w[np.abs(w) < 1e-10] = 1e-10
                pts2_proj = pts2_proj_homo[:, :2] / w
                distances = np.linalg.norm(pts1 - pts2_proj, axis=1)
                valid_d = distances[distances < 100]
                if len(valid_d) == 0:
                    valid_d = distances
                result["重投影RMSE(像素)"] = round(float(np.sqrt(np.mean(valid_d ** 2))), 4)
                result["重投影中位数(像素)"] = round(float(np.median(valid_d)), 4)
                result["重投影P95(像素)"] = round(float(np.percentile(valid_d, 95)), 4)
        except Exception as e:
            warnings.append(f"重投影误差计算失败: {str(e)}")

    # ---------- 重叠区一致性（需H） ----------
    result["重叠区灰度MAE"] = None
    result["重叠区灰度RMSE"] = None
    result["重叠区SSIM"] = None
    result["重叠区梯度MAE"] = None

    if H is not None:
        try:
            if H.shape == (3, 3):
                h, w = img1.shape[:2]
                img2_warped = cv2.warpPerspective(img2, H, (w, h),
                                                  flags=cv2.INTER_LINEAR,
                                                  borderMode=cv2.BORDER_CONSTANT,
                                                  borderValue=0)
                gray1 = cv2.cvtColor(img1, cv2.COLOR_BGR2GRAY)
                gray2_warped = cv2.cvtColor(img2_warped, cv2.COLOR_BGR2GRAY)
                mask1 = (gray1 > 0).astype(np.uint8)
                mask2 = (gray2_warped > 0).astype(np.uint8)
                overlap_mask = cv2.bitwise_and(mask1, mask2)
                overlap_count = cv2.countNonZero(overlap_mask)

                if overlap_count > 0:
                    overlap_px1 = gray1[overlap_mask == 1].astype(np.float64)
                    overlap_px2 = gray2_warped[overlap_mask == 1].astype(np.float64)
                    mae = np.mean(np.abs(overlap_px1 - overlap_px2))
                    rmse_val = np.sqrt(np.mean((overlap_px1 - overlap_px2) ** 2))
                    try:
                        ssim_score = structural_similarity(gray1, gray2_warped,
                                                           mask=overlap_mask, data_range=255)
                    except Exception:
                        ssim_score = 0.0
                    grad1 = PanoramaEvaluator._sobel_gradient(gray1)
                    grad2 = PanoramaEvaluator._sobel_gradient(gray2_warped)
                    grad_mae = np.mean(np.abs(grad1[overlap_mask == 1] - grad2[overlap_mask == 1]))

                    result["重叠区灰度MAE"] = round(float(mae), 4)
                    result["重叠区灰度RMSE"] = round(float(rmse_val), 4)
                    result["重叠区SSIM"] = round(float(max(0, ssim_score)), 4)
                    result["重叠区梯度MAE"] = round(float(grad_mae), 4)
                else:
                    warnings.append("两图无有效重叠区域")
        except Exception as e:
            warnings.append(f"重叠区指标计算失败: {str(e)}")

    if warnings:
        result["警告"] = "; ".join(warnings)

    return result


class WebApiEvaluator:
    """
    【新增】Web API友好的评估器
    - 直接接收内存中的numpy图片数组，无需文件路径
    - 支持2张及以上多张图片的拼接评估
    - 返回JSON可序列化的纯字典结果
    - 可选生成base64编码图表，便于前端直接展示
    - 兼容核心算法组直接调用，无需落盘中间文件
    """

    def __init__(self,
                 source_images: List[np.ndarray],
                 panorama: np.ndarray,
                 H_list: Optional[List[np.ndarray]] = None,
                 inliers_list: Optional[List[np.ndarray]] = None,
                 match_stats: Optional[List[Dict]] = None,
                 total_time: float = 0.0):
        """
        初始化Web API评估器
        :param source_images: 原始输入图片列表（按拼接顺序），每张为BGR numpy数组，长度>=2
        :param panorama: 拼接完成的全景图，BGR numpy数组
        :param H_list: 各相邻对单应性矩阵列表，长度=len(source_images)-1，每个为3x3数组（可选）
        :param inliers_list: 各相邻对内点匹配对列表，长度=len(source_images)-1，每个为Nx4数组（可选）
        :param match_stats: 各相邻对匹配统计列表，每个字典含total_matches、inlier_num字段（可选）
        :param total_time: 拼接总耗时（秒，可选）
        """
        # 验证输入
        if not isinstance(source_images, list) or len(source_images) < 2:
            raise ValueError(f"source_images必须是长度>=2的列表，实际长度{len(source_images) if isinstance(source_images, list) else '非列表'}")

        for idx, img in enumerate(source_images):
            _validate_image(img, f"原始图片{idx + 1}")
        _validate_image(panorama, "全景拼接结果图")

        self.source_images = source_images
        self.panorama = panorama
        self.num_images = len(source_images)
        self.H_list = H_list or [None] * (self.num_images - 1)
        self.inliers_list = inliers_list or [None] * (self.num_images - 1)
        self.match_stats = match_stats or [{} for _ in range(self.num_images - 1)]
        self.total_time = float(total_time)

        if len(self.H_list) != self.num_images - 1:
            raise ValueError(f"H_list长度应为{self.num_images - 1}，实际为{len(self.H_list)}")
        if len(self.inliers_list) != self.num_images - 1:
            raise ValueError(f"inliers_list长度应为{self.num_images - 1}，实际为{len(self.inliers_list)}")
        if len(self.match_stats) != self.num_images - 1:
            raise ValueError(f"match_stats长度应为{self.num_images - 1}，实际为{len(self.match_stats)}")

    # ---------- 画布利用率指标 ----------
    def _calc_canvas_metrics(self) -> Dict:
        gray_pano = cv2.cvtColor(self.panorama, cv2.COLOR_BGR2GRAY)
        total = gray_pano.size
        if total == 0:
            return {"有效画布占比": 0.0, "空白占比": 1.0}
        valid = np.sum(gray_pano > 10)
        valid_ratio = valid / total
        valid_ratio = max(0.0, min(1.0, valid_ratio))
        return {
            "有效画布占比": round(float(valid_ratio), 4),
            "空白占比": round(float(1 - valid_ratio), 4)
        }

    # ---------- 清晰度指标 ----------
    def _calc_sharpness_metrics(self) -> Dict:
        pano_sharp = PanoramaEvaluator._laplacian_var(self.panorama)
        src_sharp_list = [PanoramaEvaluator._laplacian_var(img) for img in self.source_images]
        avg_src_sharp = np.mean(src_sharp_list) if src_sharp_list else 0.0
        retention = pano_sharp / avg_src_sharp if avg_src_sharp > 1e-6 else 0.0
        return {
            "全景图清晰度方差": round(float(pano_sharp), 2),
            "原图平均清晰度方差": round(float(avg_src_sharp), 2),
            "清晰度保持率": round(float(retention), 4),
            "图片数量": self.num_images
        }

    # ---------- 逐相邻对评估 ----------
    def _calc_pairwise_metrics(self) -> Dict:
        pair_results = []
        total_matches_sum = 0
        total_inliers_sum = 0
        rmse_list = []
        ssim_list = []
        mae_list = []

        for i in range(self.num_images - 1):
            img_a = self.source_images[i]
            img_b = self.source_images[i + 1]
            H = self.H_list[i]
            inliers = self.inliers_list[i]
            stats = self.match_stats[i] or {}

            pair_res = evaluate_image_pair(
                img_a, img_b,
                H=H,
                inliers=inliers,
                total_matches=stats.get("total_matches", 0),
                inlier_num=stats.get("inlier_num", 0)
            )
            pair_res["图片对"] = f"img{i + 1}-img{i + 2}"
            pair_results.append(pair_res)

            if "总匹配对数" in pair_res and pair_res["总匹配对数"] is not None:
                total_matches_sum += pair_res["总匹配对数"]
            if "RANSAC内点数" in pair_res and pair_res["RANSAC内点数"] is not None:
                total_inliers_sum += pair_res["RANSAC内点数"]
            if pair_res.get("重投影RMSE(像素)") is not None:
                rmse_list.append(pair_res["重投影RMSE(像素)"])
            if pair_res.get("重叠区SSIM") is not None:
                ssim_list.append(pair_res["重叠区SSIM"])
            if pair_res.get("重叠区灰度MAE") is not None:
                mae_list.append(pair_res["重叠区灰度MAE"])

        summary = {}
        if total_matches_sum > 0:
            summary["累计总匹配对数"] = total_matches_sum
            summary["累计内点数"] = total_inliers_sum
            summary["平均内点率"] = round(total_inliers_sum / total_matches_sum, 4) if total_matches_sum > 0 else None
        if rmse_list:
            summary["平均重投影RMSE(像素)"] = round(float(np.mean(rmse_list)), 4)
            summary["重投影RMSE_P95(像素)"] = round(float(np.percentile(rmse_list, 95)), 4)
        if ssim_list:
            summary["平均重叠区SSIM"] = round(float(np.mean(ssim_list)), 4)
            summary["最小重叠区SSIM"] = round(float(np.min(ssim_list)), 4)
        if mae_list:
            summary["平均重叠区灰度MAE"] = round(float(np.mean(mae_list)), 4)

        return {"逐对详情": pair_results, "汇总": summary}

    # ---------- 综合评分（归一化0-1） ----------
    def _calc_composite_scores(self, metrics: Dict) -> Dict:
        scores = {}
        scores["匹配质量"] = metrics.get("平均内点率", 0.0) or 0.0

        # RMSE 归一化：以图像对角线 0.5% 为满分阈值
        img_diag = max(
            np.sqrt(self.source_images[0].shape[0]**2 + self.source_images[0].shape[1]**2),
            1.0
        )
        rmse = metrics.get("平均重投影RMSE(像素)", img_diag * 0.005) or img_diag * 0.005
        scores["对齐精度"] = max(0.0, 1.0 - rmse / max(img_diag * 0.005, 1.0))

        scores["重叠一致性"] = metrics.get("平均重叠区SSIM", 0.0) or 0.0
        scores["画布利用率"] = metrics.get("有效画布占比", 0.0)

        # 清晰度保持率：100% 即为满分
        retention = metrics.get("清晰度保持率", 0.0) or 0.0
        scores["清晰度"] = min(1.0, max(0.0, retention))

        # 运行效率：每张图 10s 为满分基准
        time_budget = max(self.num_images * 10.0, 1.0)
        t = metrics.get("总耗时(秒)", time_budget) or time_budget
        scores["运行效率"] = max(0.0, 1.0 - t / time_budget)

        valid_scores = [v for v in scores.values() if v is not None]
        scores["综合得分"] = round(float(np.mean(valid_scores)), 4) if valid_scores else 0.0
        return {k: round(float(v), 4) for k, v in scores.items()}

    # ---------- 生成雷达图base64 ----------
    def generate_radar_chart_base64(self, scores: Dict) -> Optional[str]:
        """生成单案例多维度雷达图，返回base64字符串"""
        _setup_matplotlib()
        dims = CONFIG["radar_dimensions"]
        available_dims = [d for d in dims if d in scores and scores[d] is not None]
        if not available_dims:
            return None
        n_dims = len(available_dims)
        angles = np.linspace(0, 2 * np.pi, n_dims, endpoint=False).tolist()
        angles += angles[:1]
        values = [scores[d] for d in available_dims]
        values += values[:1]

        fig, ax = plt.subplots(figsize=(7, 7), subplot_kw=dict(polar=True))
        ax.plot(angles, values, 'o-', linewidth=2.5, color=CONFIG["chart_colors"]["inlier_ratio"], markersize=6)
        ax.fill(angles, values, alpha=0.25, color=CONFIG["chart_colors"]["inlier_ratio"])
        ax.set_xticks(angles[:-1])
        ax.set_xticklabels(available_dims, fontsize=12, fontweight='bold')
        ax.set_ylim(0, 1)
        ax.set_yticks([0.2, 0.4, 0.6, 0.8, 1.0])
        ax.set_yticklabels(['0.2', '0.4', '0.6', '0.8', '1.0'], fontsize=9)
        ax.grid(True, linestyle='--', alpha=0.7)
        ax.set_title("拼接质量综合雷达图", fontsize=15, fontweight='bold', pad=25)
        plt.tight_layout()
        return fig_to_base64(fig)

    # ---------- 主评估入口 ----------
    def evaluate(self, generate_chart: bool = False,
                 include_intermediate_images: bool = False) -> Dict:
        """
        执行完整评估
        :param generate_chart: 是否生成base64雷达图
        :param include_intermediate_images: 是否返回全景图base64（供前端预览）
        :return: 完整评估结果字典（JSON可序列化）
        """
        result = {
            "状态": "成功",
            "图片数量": self.num_images,
        }
        warnings = []

        try:
            pairwise = self._calc_pairwise_metrics()
            result["相邻对评估"] = pairwise["逐对详情"]
            result.update(pairwise["汇总"])
        except Exception as e:
            warnings.append(f"相邻对评估失败: {str(e)}")

        try:
            canvas_metrics = self._calc_canvas_metrics()
            result.update(canvas_metrics)
        except Exception as e:
            warnings.append(f"画布利用率计算失败: {str(e)}")

        try:
            sharp_metrics = self._calc_sharpness_metrics()
            result.update(sharp_metrics)
        except Exception as e:
            warnings.append(f"清晰度计算失败: {str(e)}")

        result["总耗时(秒)"] = round(self.total_time, 4)

        try:
            composite = self._calc_composite_scores(result)
            result["综合评分"] = composite
        except Exception as e:
            warnings.append(f"综合评分计算失败: {str(e)}")

        if generate_chart:
            try:
                chart_b64 = self.generate_radar_chart_base64(result.get("综合评分", {}))
                if chart_b64:
                    result["雷达图_base64"] = chart_b64
            except Exception as e:
                warnings.append(f"雷达图生成失败: {str(e)}")

        if include_intermediate_images:
            try:
                result["全景图_base64"] = img_to_base64(self.panorama)
            except Exception as e:
                warnings.append(f"全景图编码失败: {str(e)}")

        if warnings:
            result["警告"] = "; ".join(warnings)

        return result


# 【便捷函数】Web后端可直接调用的一站式接口
def evaluate_stitching_api(source_images: List[np.ndarray],
                           panorama: np.ndarray,
                           H_list: Optional[List[np.ndarray]] = None,
                           inliers_list: Optional[List[np.ndarray]] = None,
                           match_stats: Optional[List[Dict]] = None,
                           total_time: float = 0.0,
                           generate_chart: bool = True,
                           include_panorama_preview: bool = True) -> Dict:
    """
    【Web API便捷入口】一站式评估函数，核心算法组可直接调用，无需实例化类
    :param source_images: 原始图片列表（按拼接顺序），每张为BGR numpy数组，长度2~N
    :param panorama: 拼接得到的全景图，BGR numpy数组
    :param H_list: 相邻对单应性矩阵列表（可选，长度=图片数-1）
    :param inliers_list: 相邻对内点匹配对列表（可选，长度=图片数-1）
    :param match_stats: 相邻对匹配统计列表，每个元素含total_matches、inlier_num（可选）
    :param total_time: 拼接总耗时（秒）
    :param generate_chart: 是否生成base64雷达图
    :param include_panorama_preview: 是否返回全景图base64预览
    :return: 完整评估结果字典，可直接jsonify返回给前端
    """
    evaluator = WebApiEvaluator(
        source_images=source_images,
        panorama=panorama,
        H_list=H_list,
        inliers_list=inliers_list,
        match_stats=match_stats,
        total_time=total_time
    )
    return evaluator.evaluate(
        generate_chart=generate_chart,
        include_intermediate_images=include_panorama_preview
    )


def _setup_matplotlib():
    plt.rcParams["font.sans-serif"] = CONFIG["font_family"]
    plt.rcParams["axes.unicode_minus"] = False
    plt.rcParams["figure.dpi"] = CONFIG["chart_dpi"]


def _load_csv_results(csv_path):
    results = []
    csv_path = _ensure_absolute_path(csv_path)
    if not os.path.exists(csv_path):
        raise FileNotFoundError("CSV\u6587\u4ef6\u4e0d\u5b58\u5728\uff1a" + csv_path)

    with open(csv_path, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            results.append(dict(row))
    return results


def _clear_output_dir(output_dir):
    if not os.path.isdir(output_dir):
        return
    for fname in os.listdir(output_dir):
        fpath = os.path.join(output_dir, fname)
        if os.path.isfile(fpath):
            ext = os.path.splitext(fname)[1].lower()
            if ext in {".png", ".jpg", ".jpeg"}:
                try:
                    os.remove(fpath)
                except Exception:
                    pass


_EN_TEXTS = {
    "radar_title": "Quality Radar Chart",
    "dims": {
        "匹配质量": "Match Quality",
        "对齐精度": "Alignment",
        "重叠一致性": "Overlap Consistency",
        "画布利用率": "Canvas Usage",
        "清晰度": "Sharpness",
        "运行效率": "Efficiency"
    },
    "single_title": "Panorama Stitching Quality Metrics",
    "overall": "Overall Score"
}


def _get_text(key, subkey=None, use_english=False):
    if not use_english:
        return subkey if subkey is not None else key
    if subkey is not None:
        return _EN_TEXTS.get(key, {}).get(subkey, subkey)
    return _EN_TEXTS.get(key, key)


def generate_single_task_charts(metrics, composite_scores, output_dir, use_english=True):
    _setup_matplotlib()
    output_dir = _ensure_absolute_path(output_dir)
    if not os.path.isdir(output_dir):
        os.makedirs(output_dir, exist_ok=True)
    _clear_output_dir(output_dir)

    inlier_ratio = _safe_float(metrics.get("内点率"), 0.0)
    rmse_val = _safe_float(metrics.get("重投影RMSE(像素)"))
    ssim_val = _safe_float(metrics.get("重叠区SSIM"), 0.0)
    time_val = _safe_float(metrics.get("总耗时(秒)"), 0.0)
    canvas_val = _safe_float(metrics.get("有效画布占比"), 0.0)
    overall_score = composite_scores.get("综合得分", 0.0)

    colors = CONFIG["chart_colors"]

    fig, axes = plt.subplots(2, 3, figsize=(15, 10))
    dashboard_title = _get_text("single_title", None, use_english)
    fig.suptitle(dashboard_title, fontsize=16, fontweight='bold')

    def _draw_gauge(ax, value, title_cn, max_val, good_high=True, color='#4e79a7', is_pct=False):
        title = _get_text("dims", title_cn, use_english) if title_cn in _EN_TEXTS["dims"] else title_cn
        ax.set_xlim(-1.2, 1.2)
        ax.set_ylim(-0.2, 1.2)
        ax.set_aspect('equal')
        ax.axis('off')

        theta = np.linspace(np.pi, 0, 100)
        x = np.cos(theta)
        y = np.sin(theta)
        ax.plot(x, y, color='#e0e0e0', linewidth=15)

        if value is not None:
            ratio = min(1.0, max(0.0, value / max_val if good_high else (max_val - value) / max_val))
            theta_fill = np.linspace(np.pi, np.pi - ratio * np.pi, 100)
            x_fill = np.cos(theta_fill)
            y_fill = np.sin(theta_fill)
            ax.plot(x_fill, y_fill, color=color, linewidth=15)
            display_val = f"{value:.1%}" if is_pct else f"{value:.2f}"
            ax.text(0, 0.2, display_val, ha='center', va='center', fontsize=20, fontweight='bold')
        else:
            ax.text(0, 0.2, "-", ha='center', va='center', fontsize=20, fontweight='bold', color='#999999')
        ax.text(0, -0.1, title, ha='center', va='center', fontsize=11)

    _draw_gauge(axes[0, 0], inlier_ratio, "匹配质量", 1.0, True, colors["inlier_ratio"], is_pct=True)
    rmse_title = "Reprojection RMSE" if use_english else "重投影RMSE"
    _draw_gauge(axes[0, 1], rmse_val if rmse_val is not None else None, rmse_title, 10.0, False, colors["rmse"])
    _draw_gauge(axes[0, 2], ssim_val, "重叠一致性", 1.0, True, colors["ssim"], is_pct=True)
    time_title = "Time Cost (s)" if use_english else "总耗时(秒)"
    _draw_gauge(axes[1, 0], time_val, time_title, 30.0, False, colors["time"])
    canvas_title = "Canvas Usage" if use_english else "画布利用率"
    _draw_gauge(axes[1, 1], canvas_val, canvas_title, 1.0, True, colors["canvas"], is_pct=True)
    overall_title = _get_text("overall", None, use_english)
    _draw_gauge(axes[1, 2], overall_score, overall_title, 1.0, True, '#59a14f', is_pct=True)

    plt.tight_layout(rect=[0, 0, 1, 0.95])
    plt.savefig(os.path.join(output_dir, "metrics_dashboard.png"), dpi=CONFIG["chart_dpi"], bbox_inches='tight')
    plt.close()

    dims_cn = ["匹配质量", "对齐精度", "重叠一致性", "画布利用率", "清晰度", "运行效率"]
    dims = [_get_text("dims", d, use_english) for d in dims_cn]
    n_dims = len(dims_cn)
    angles = np.linspace(0, 2 * np.pi, n_dims, endpoint=False).tolist()
    angles += angles[:1]

    scores = []
    for d in dims_cn:
        scores.append(composite_scores.get(d, 0.0))
    scores += scores[:1]

    fig, ax = plt.subplots(figsize=(8, 8), subplot_kw=dict(polar=True))
    ax.plot(angles, scores, 'o-', linewidth=2, color='#4e79a7', markersize=6)
    ax.fill(angles, scores, alpha=0.25, color='#4e79a7')
    ax.set_xticks(angles[:-1])
    ax.set_xticklabels(dims, fontsize=11, fontweight='bold')
    ax.set_ylim(0, 1)
    ax.set_yticks([0.2, 0.4, 0.6, 0.8, 1.0])
    ax.set_yticklabels(['0.2', '0.4', '0.6', '0.8', '1.0'], fontsize=9)
    ax.grid(True, linestyle='--', alpha=0.7)
    radar_title = _get_text("radar_title", None, use_english)
    ax.set_title(radar_title, fontsize=14, fontweight='bold', pad=20)
    plt.tight_layout()
    plt.savefig(os.path.join(output_dir, "quality_radar.png"), dpi=CONFIG["chart_dpi"], bbox_inches='tight')
    plt.close()


def generate_charts(csv_path, output_dir=None, use_english=False):
    _setup_matplotlib()
    output_dir = _ensure_absolute_path(output_dir or CONFIG["default_chart_dir"])
    if not os.path.isdir(output_dir):
        os.makedirs(output_dir, exist_ok=True)

    _clear_output_dir(output_dir)

    all_results = _load_csv_results(csv_path)
    success_results = [r for r in all_results if r.get("\u72b6\u6001") != "\u5931\u8d25"]

    if not success_results:
        print(_color_text("\u6ca1\u6709\u6210\u529f\u7684\u8bc4\u4f30\u7ed3\u679c\uff0c\u65e0\u6cd5\u751f\u6210\u56fe\u8868", "yellow"))
        return

    cases = [r.get("\u7528\u4f8b\u540d\u79f0", "\u5f53\u524d\u4efb\u52a1") for r in success_results]
    inlier_ratios = [_safe_float(r.get("\u5185\u70b9\u7387"), 0.0) for r in success_results]
    rmse_list = [_safe_float(r.get("\u91cd\u6295\u5f71RMSE(\u50cf\u7d20)"), 0.0) for r in success_results]
    ssim_list = [_safe_float(r.get("\u5168\u666fSSIM"), 0.0) for r in success_results]
    times = [_safe_float(r.get("\u603b\u8017\u65f6(\u79d2)"), 0.0) for r in success_results]
    canvas_ratios = [_safe_float(r.get("\u6709\u6548\u753b\u5e03\u5360\u6bd4"), 0.0) for r in success_results]

    colors = CONFIG["chart_colors"]
    figsize = CONFIG["chart_figsize"]

    plt.figure(figsize=figsize)
    bars = plt.bar(cases, inlier_ratios, color=colors["inlier_ratio"])
    plt.title("\u4e0d\u540c\u573a\u666f\u5185\u70b9\u7387\u5bf9\u6bd4", fontsize=14, fontweight='bold')
    plt.ylabel("\u5185\u70b9\u7387")
    plt.ylim(0, 1.1)
    plt.grid(axis="y", alpha=0.3, linestyle='--')
    for bar, val in zip(bars, inlier_ratios):
        plt.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.01,
                 '{:.1%}'.format(val), ha='center', va='bottom', fontsize=9)
    plt.xticks(rotation=45 if len(cases) > 5 else 0)
    plt.tight_layout()
    plt.savefig(os.path.join(output_dir, "inlier_ratio.png"), dpi=CONFIG["chart_dpi"], bbox_inches='tight')
    plt.close()

    plt.figure(figsize=figsize)
    bars = plt.bar(cases, rmse_list, color=colors["rmse"])
    plt.title("\u4e0d\u540c\u573a\u666f\u91cd\u6295\u5f71RMSE\u5bf9\u6bd4\uff08\u8d8a\u5c0f\u8d8a\u597d\uff09", fontsize=14, fontweight='bold')
    plt.ylabel("RMSE / \u50cf\u7d20")
    plt.grid(axis="y", alpha=0.3, linestyle='--')
    for bar, val in zip(bars, rmse_list):
        plt.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.1,
                 '{:.2f}'.format(val), ha='center', va='bottom', fontsize=9)
    plt.xticks(rotation=45 if len(cases) > 5 else 0)
    plt.tight_layout()
    plt.savefig(os.path.join(output_dir, "reprojection_rmse.png"), dpi=CONFIG["chart_dpi"], bbox_inches='tight')
    plt.close()

    plt.figure(figsize=figsize)
    bars = plt.bar(cases, ssim_list, color=colors["ssim"])
    plt.title("\u4e0d\u540c\u573a\u666f\u5168\u666fSSIM\u5bf9\u6bd4\uff08\u8d8a\u5927\u8d8a\u597d\uff09", fontsize=14, fontweight='bold')
    plt.ylabel("SSIM")
    plt.ylim(0, 1.1)
    plt.grid(axis="y", alpha=0.3, linestyle='--')
    for bar, val in zip(bars, ssim_list):
        plt.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.01,
                 '{:.3f}'.format(val), ha='center', va='bottom', fontsize=9)
    plt.xticks(rotation=45 if len(cases) > 5 else 0)
    plt.tight_layout()
    plt.savefig(os.path.join(output_dir, "overlap_ssim.png"), dpi=CONFIG["chart_dpi"], bbox_inches='tight')
    plt.close()

    plt.figure(figsize=figsize)
    bars = plt.bar(cases, times, color=colors["time"])
    plt.title("\u4e0d\u540c\u573a\u666f\u62fc\u63a5\u8017\u65f6\u5bf9\u6bd4", fontsize=14, fontweight='bold')
    plt.ylabel("\u8017\u65f6 / \u79d2")
    plt.grid(axis="y", alpha=0.3, linestyle='--')
    for bar, val in zip(bars, times):
        plt.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.05,
                 '{:.2f}s'.format(val), ha='center', va='bottom', fontsize=9)
    plt.xticks(rotation=45 if len(cases) > 5 else 0)
    plt.tight_layout()
    plt.savefig(os.path.join(output_dir, "time_cost.png"), dpi=CONFIG["chart_dpi"], bbox_inches='tight')
    plt.close()

    plt.figure(figsize=figsize)
    x = np.arange(len(cases))
    width = 0.35
    plt.bar(x - width / 2, canvas_ratios, width, label='\u6709\u6548\u753b\u5e03\u5360\u6bd4', color=colors["canvas"])
    plt.bar(x + width / 2, [1 - r for r in canvas_ratios], width, label='\u7a7a\u767d\u5360\u6bd4', color='#bab0ac')
    plt.title("\u4e0d\u540c\u573a\u666f\u753b\u5e03\u5229\u7528\u7387\u5bf9\u6bd4", fontsize=14, fontweight='bold')
    plt.ylabel("\u5360\u6bd4")
    plt.xticks(x, cases, rotation=45 if len(cases) > 5 else 0)
    plt.ylim(0, 1.1)
    plt.legend()
    plt.grid(axis="y", alpha=0.3, linestyle='--')
    plt.tight_layout()
    plt.savefig(os.path.join(output_dir, "canvas_utilization.png"), dpi=CONFIG["chart_dpi"], bbox_inches='tight')
    plt.close()

    _generate_radar_chart(success_results, output_dir, use_english=use_english)

    print(_color_text("\U0001f5bc\ufe0f  \u6240\u6709\u56fe\u8868\u5df2\u751f\u6210\u5230\uff1a" + output_dir + " \u76ee\u5f55", "green"))


def _generate_radar_chart(results, output_dir, use_english=False):
    dims_cn = CONFIG["radar_dimensions"]
    dims = [_get_text("dims", d, use_english) for d in dims_cn]
    n_dims = len(dims_cn)

    angles = np.linspace(0, 2 * np.pi, n_dims, endpoint=False).tolist()
    angles += angles[:1]

    fig, ax = plt.subplots(figsize=(10, 10), subplot_kw=dict(polar=True))

    colors = ['#4e79a7', '#e15759', '#59a14f', '#f28e2b', '#76b7b2', '#edc948', '#b07aa1', '#ff9da7']

    for idx, res in enumerate(results):
        case_name = res.get("\u7528\u4f8b\u540d\u79f0", "\u5f53\u524d\u4efb\u52a1")
        scores = []
        score_keys = {
            "\u5339\u914d\u8d28\u91cf": "\u5185\u70b9\u7387",
            "\u5bf9\u9f50\u7cbe\u5ea6": "\u91cd\u6295\u5f71RMSE(\u50cf\u7d20)",
            "\u91cd\u53e0\u4e00\u81f4\u6027": "\u5168\u666fSSIM",
            "\u753b\u5e03\u5229\u7528\u7387": "\u6709\u6548\u753b\u5e03\u5360\u6bd4",
            "\u6e05\u6670\u5ea6": "\u6e05\u6670\u5ea6\u4fdd\u6301\u7387",
            "\u8fd0\u884c\u6548\u7387": "\u603b\u8017\u65f6(\u79d2)"
        }

        for d in dims_cn:
            key = score_keys[d]
            val = _safe_float(res.get(key), 0.0)
            if d == "\u5bf9\u9f50\u7cbe\u5ea6":
                s = max(0, 1 - val / 10)
            elif d == "\u8fd0\u884c\u6548\u7387":
                s = max(0, 1 - val / 30)
            elif d == "\u6e05\u6670\u5ea6":
                s = min(1, val / 1.5)
            else:
                s = val
            scores.append(s)

        scores += scores[:1]
        color = colors[idx % len(colors)]
        ax.plot(angles, scores, 'o-', linewidth=2, label=case_name, color=color, markersize=4)
        ax.fill(angles, scores, alpha=0.1, color=color)

    ax.set_xticks(angles[:-1])
    ax.set_xticklabels(dims, fontsize=12, fontweight='bold')
    ax.set_ylim(0, 1)
    ax.set_yticks([0.2, 0.4, 0.6, 0.8, 1.0])
    ax.set_yticklabels(['0.2', '0.4', '0.6', '0.8', '1.0'], fontsize=9)
    ax.grid(True, linestyle='--', alpha=0.7)

    radar_title = _get_text("radar_title", None, use_english) if use_english else "\u591a\u7ef4\u5ea6\u7efc\u5408\u80fd\u529b\u96f7\u8fbe\u56fe"
    plt.title(radar_title, fontsize=16, fontweight='bold', pad=30)
    ax.legend(loc='upper right', bbox_to_anchor=(1.3, 1.1), fontsize=10)

    plt.tight_layout()
    plt.savefig(os.path.join(output_dir, "quality_radar.png"), dpi=CONFIG["chart_dpi"], bbox_inches='tight')
    plt.close()


def generate_comparison(csv_path_a, csv_path_b, output_dir=None, label_a="A\u7ec4", label_b="B\u7ec4"):
    _setup_matplotlib()
    output_dir = _ensure_absolute_path(output_dir or "\u5bf9\u6bd4\u7ed3\u679c")
    os.makedirs(output_dir, exist_ok=True)

    results_a = _load_csv_results(csv_path_a)
    results_b = _load_csv_results(csv_path_b)

    success_a = {r["\u7528\u4f8b\u540d\u79f0"]: r for r in results_a if r.get("\u72b6\u6001") != "\u5931\u8d25"}
    success_b = {r["\u7528\u4f8b\u540d\u79f0"]: r for r in results_b if r.get("\u72b6\u6001") != "\u5931\u8d25"}

    common_cases = sorted(set(success_a.keys()) & set(success_b.keys()))

    if not common_cases:
        print(_color_text("\u26a0\ufe0f  \u4e24\u7ec4\u7ed3\u679c\u6ca1\u6709\u5171\u540c\u7684\u6d4b\u8bd5\u7528\u4f8b\uff0c\u65e0\u6cd5\u5bf9\u6bd4", "yellow"))
        return

    print(_color_text("\n\ud83d\udcca \u5f00\u59cb\u5bf9\u6bd4\u5206\u6790\uff1a" + label_a + " vs " + label_b, "cyan"))
    print("\u5171\u540c\u6d4b\u8bd5\u7528\u4f8b\uff1a" + str(len(common_cases)) + " \u4e2a")

    compare_metrics = [
        ("\u5185\u70b9\u7387", True, "\u5339\u914d\u8d28\u91cf"),
        ("\u91cd\u6295\u5f71RMSE(\u50cf\u7d20)", False, "\u51e0\u4f55\u7cbe\u5ea6"),
        ("\u5168\u666fSSIM", True, "\u91cd\u53e0\u4e00\u81f4\u6027"),
        ("\u6709\u6548\u753b\u5e03\u5360\u6bd4", True, "\u753b\u5e03\u5229\u7528\u7387"),
        ("\u6e05\u6670\u5ea6\u4fdd\u6301\u7387", True, "\u6e05\u6670\u5ea6"),
        ("\u603b\u8017\u65f6(\u79d2)", False, "\u8fd0\u884c\u901f\u5ea6")
    ]

    comparison_table = []
    for metric_name, higher_better, category in compare_metrics:
        vals_a = []
        vals_b = []
        for case in common_cases:
            va = float(success_a[case].get(metric_name, 0))
            vb = float(success_b[case].get(metric_name, 0))
            vals_a.append(va)
            vals_b.append(vb)

        avg_a = np.mean(vals_a) if vals_a else 0
        avg_b = np.mean(vals_b) if vals_b else 0

        if higher_better:
            winner = label_a if avg_a > avg_b else label_b if avg_b > avg_a else "\u5e73\u5c40"
            diff_pct = (avg_a - avg_b) / avg_b * 100 if abs(avg_b) > 1e-6 else 0
        else:
            winner = label_a if avg_a < avg_b else label_b if avg_b < avg_a else "\u5e73\u5c40"
            diff_pct = (avg_b - avg_a) / avg_a * 100 if abs(avg_a) > 1e-6 else 0

        comparison_table.append({
            "\u6307\u6807": metric_name,
            "\u7c7b\u522b": category,
            "\u8d8a\u5927\u8d8a\u597d": "\u662f" if higher_better else "\u5426",
            label_a + "_\u5747\u503c": round(avg_a, 4),
            label_b + "_\u5747\u503c": round(avg_b, 4),
            "\u63d0\u5347/\u4e0b\u964d(%)": round(diff_pct, 2),
            "\u4f18\u80dc\u65b9": winner
        })

    compare_csv = os.path.join(output_dir, "\u5bf9\u6bd4\u7ed3\u679c\u8868.csv")
    with open(compare_csv, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(comparison_table[0].keys()))
        writer.writeheader()
        writer.writerows(comparison_table)

    _generate_comparison_charts(comparison_table, label_a, label_b, output_dir)

    print(_color_text("\n--- \u5bf9\u6bd4\u7ed3\u679c\u6458\u8981 ---", "cyan"))
    wins_a = sum(1 for r in comparison_table if r["\u4f18\u80dc\u65b9"] == label_a)
    wins_b = sum(1 for r in comparison_table if r["\u4f18\u80dc\u65b9"] == label_b)
    print("\u6307\u6807\u4f18\u80dc\u7edf\u8ba1\uff1a" + label_a + " \u80dc\u51fa " + str(wins_a) + " \u9879\uff0c" + label_b + " \u80dc\u51fa " + str(wins_b) + " \u9879")
    for row in comparison_table:
        if row["\u4f18\u80dc\u65b9"] == label_a:
            win_mark = " \u2705"
        elif row["\u4f18\u80dc\u65b9"] == label_b:
            win_mark = " \u274c"
        else:
            win_mark = " \u2796"
        print("  " + row["\u6307\u6807"] + ": " + label_a + "=" + "{:.4f}".format(row[label_a + "_\u5747\u503c"]) + " vs " + label_b + "=" + "{:.4f}".format(row[label_b + "_\u5747\u503c"]) + " ({:+.2f}%)".format(row["\u63d0\u5347/\u4e0b\u964d(%)"]) + win_mark)

    print(_color_text("\n\u5bf9\u6bd4\u7ed3\u679c\u5df2\u4fdd\u5b58\u5230\uff1a" + output_dir, "green"))


def _generate_comparison_charts(comparison_table, label_a, label_b, output_dir):
    _setup_matplotlib()

    chart_metrics = ["\u5185\u70b9\u7387", "\u91cd\u6295\u5f71RMSE(\u50cf\u7d20)", "\u5168\u666fSSIM", "\u603b\u8017\u65f6(\u79d2)"]
    metric_labels = ["\u5185\u70b9\u7387", "\u91cd\u6295\u5f71RMSE(\u50cf\u7d20)", "SSIM", "\u8017\u65f6(\u79d2)"]

    n = len(chart_metrics)
    fig, axes = plt.subplots(2, 2, figsize=(12, 10))
    axes = axes.flatten()
    colors = [CONFIG["chart_colors"]["inlier_ratio"], "#bab0ac"]

    for idx, (metric, m_label) in enumerate(zip(chart_metrics, metric_labels)):
        ax = axes[idx]
        row = next(r for r in comparison_table if r["\u6307\u6807"] == metric)
        val_a = row[label_a + "_\u5747\u503c"]
        val_b = row[label_b + "_\u5747\u503c"]

        x = np.arange(1)
        width = 0.25
        bars1 = ax.bar(x - width/2, [val_a], width, label=label_a, color=colors[0])
        bars2 = ax.bar(x + width/2, [val_b], width, label=label_b, color=colors[1])

        higher_better = row["\u8d8a\u5927\u8d8a\u597d"] == "\u662f"
        better = "\u2191 \u8d8a\u5927\u8d8a\u597d" if higher_better else "\u2193 \u8d8a\u5c0f\u8d8a\u597d"
        ax.set_title(m_label + " (" + better + ")", fontsize=12, fontweight='bold')
        ax.set_xticks([])
        ax.legend(fontsize=10)
        ax.grid(axis="y", alpha=0.3, linestyle='--')

        for bar, val in zip(bars1, [val_a]):
            ax.text(bar.get_x() + bar.get_width()/2, bar.get_height(),
                    '{:.4f}'.format(val), ha='center', va='bottom', fontsize=10)
        for bar, val in zip(bars2, [val_b]):
            ax.text(bar.get_x() + bar.get_width()/2, bar.get_height(),
                    '{:.4f}'.format(val), ha='center', va='bottom', fontsize=10)

    plt.suptitle(label_a + " vs " + label_b + " \u6838\u5fc3\u6307\u6807\u5bf9\u6bd4", fontsize=16, fontweight='bold', y=1.02)
    plt.tight_layout()
    plt.savefig(os.path.join(output_dir, "core_metrics_comparison.png"), dpi=CONFIG["chart_dpi"], bbox_inches='tight')
    plt.close()

    dims = ["\u5339\u914d\u8d28\u91cf", "\u51e0\u4f55\u7cbe\u5ea6", "\u91cd\u53e0\u4e00\u81f4\u6027", "\u753b\u5e03\u5229\u7528\u7387", "\u6e05\u6670\u5ea6", "\u8fd0\u884c\u901f\u5ea6"]
    n_dims = len(dims)
    angles = np.linspace(0, 2 * np.pi, n_dims, endpoint=False).tolist()
    angles += angles[:1]

    def get_norm_score(row):
        va = row[label_a + "_\u5747\u503c"]
        vb = row[label_b + "_\u5747\u503c"]
        higher_better = row["\u8d8a\u5927\u8d8a\u597d"] == "\u662f"
        max_val = max(abs(va), abs(vb), 1e-6)
        if higher_better:
            return va / max_val, vb / max_val
        else:
            return (max_val - va) / max_val, (max_val - vb) / max_val

    scores_a = []
    scores_b = []
    metric_order = ["\u5185\u70b9\u7387", "\u91cd\u6295\u5f71RMSE(\u50cf\u7d20)", "\u5168\u666fSSIM", "\u6709\u6548\u753b\u5e03\u5360\u6bd4", "\u6e05\u6670\u5ea6\u4fdd\u6301\u7387", "\u603b\u8017\u65f6(\u79d2)"]
    for metric in metric_order:
        row = next(r for r in comparison_table if r["\u6307\u6807"] == metric)
        sa, sb = get_norm_score(row)
        scores_a.append(sa)
        scores_b.append(sb)

    scores_a += scores_a[:1]
    scores_b += scores_b[:1]

    fig, ax = plt.subplots(figsize=(8, 8), subplot_kw=dict(polar=True))
    ax.plot(angles, scores_a, 'o-', linewidth=2, label=label_a, color=CONFIG["chart_colors"]["inlier_ratio"])
    ax.fill(angles, scores_a, alpha=0.25, color=CONFIG["chart_colors"]["inlier_ratio"])
    ax.plot(angles, scores_b, 's-', linewidth=2, label=label_b, color=colors[1])
    ax.fill(angles, scores_b, alpha=0.25, color=colors[1])

    ax.set_xticks(angles[:-1])
    ax.set_xticklabels(dims, fontsize=11, fontweight='bold')
    ax.set_ylim(0, 1.1)
    ax.set_title("\u7efc\u5408\u80fd\u529b\u5bf9\u6bd4\u96f7\u8fbe\u56fe\uff08\u5f52\u4e00\u5316\uff09", fontsize=14, fontweight='bold', pad=20)
    ax.legend(loc='upper right', bbox_to_anchor=(1.3, 1.1), fontsize=11)
    ax.grid(True, linestyle='--', alpha=0.7)

    plt.tight_layout()
    plt.savefig(os.path.join(output_dir, "overall_radar_comparison.png"), dpi=CONFIG["chart_dpi"], bbox_inches='tight')
    plt.close()


def generate_markdown_report(csv_path, output_path=None, report_title="\u5168\u666f\u62fc\u63a5\u8d28\u91cf\u8bc4\u4f30\u62a5\u544a"):
    output_path = _ensure_absolute_path(output_path or CONFIG["default_report"])
    results = _load_csv_results(csv_path)
    success_results = [r for r in results if r.get("\u72b6\u6001") != "\u5931\u8d25"]
    fail_results = [r for r in results if r.get("\u72b6\u6001") == "\u5931\u8d25"]

    total = len(results)
    success = len(success_results)
    fail = len(fail_results)

    lines = []
    lines.append("# " + report_title)
    lines.append("")
    lines.append("**\u751f\u6210\u65f6\u95f4**\uff1a" + datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
    lines.append("")

    lines.append("## \u4e00\u3001\u8bc4\u4f30\u6982\u89c8")
    lines.append("")
    lines.append("| \u6307\u6807 | \u6570\u503c |")
    lines.append("|------|------|")
    lines.append("| \u6d4b\u8bd5\u7528\u4f8b\u603b\u6570 | " + str(total) + " |")
    lines.append("| \u8bc4\u4f30\u6210\u529f | " + str(success) + " |")
    lines.append("| \u8bc4\u4f30\u5931\u8d25 | " + str(fail) + " |")
    if total > 0:
        lines.append("| \u6210\u529f\u7387 | {:.1f}% |".format(success/total*100))
    else:
        lines.append("| \u6210\u529f\u7387 | N/A |")
    lines.append("")

    if success == 0:
        lines.append("> \u26a0\ufe0f \u6ca1\u6709\u6210\u529f\u8bc4\u4f30\u7684\u7528\u4f8b\uff0c\u65e0\u6cd5\u751f\u6210\u8be6\u7ec6\u7edf\u8ba1\u3002")
        report_content = "\n".join(lines)
        out_dir = os.path.dirname(output_path)
        if out_dir and not os.path.exists(out_dir):
            os.makedirs(out_dir, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(report_content)
        print(_color_text("\ud83d\udcdd \u8bc4\u4f30\u62a5\u544a\u5df2\u751f\u6210\uff1a" + output_path, "green"))
        return

    lines.append("## \u4e8c\u3001\u6838\u5fc3\u6307\u6807\u7edf\u8ba1")
    lines.append("")

    core_metrics = [
        ("\u5185\u70b9\u7387", "\u5185\u70b9\u7387", True),
        ("\u91cd\u6295\u5f71RMSE(\u50cf\u7d20)", "\u91cd\u6295\u5f71RMSE(\u50cf\u7d20)", False),
        ("\u5168\u666fSSIM", "\u5168\u666fSSIM", True),
        ("\u6709\u6548\u753b\u5e03\u5360\u6bd4", "\u6709\u6548\u753b\u5e03\u5360\u6bd4", True),
        ("\u6e05\u6670\u5ea6\u4fdd\u6301\u7387", "\u6e05\u6670\u5ea6\u4fdd\u6301\u7387", True),
        ("\u603b\u8017\u65f6(\u79d2)", "\u603b\u8017\u65f6(\u79d2)", False),
    ]

    lines.append("| \u6307\u6807 | \u5747\u503c | \u6700\u4f18\u503c | \u6700\u5dee\u503c | \u6807\u51c6\u5dee | \u8bc4\u4ef7\u65b9\u5411 |")
    lines.append("|------|------|--------|--------|--------|----------|")

    metric_stats = {}
    for col_name, metric_key, higher_better in core_metrics:
        vals = []
        for r in success_results:
            v = r.get(metric_key, "0")
            try:
                vals.append(float(v))
            except (ValueError, TypeError):
                vals.append(0.0)

        if not vals:
            continue

        arr = np.array(vals)
        mean_v = np.mean(arr)
        std_v = np.std(arr)
        if higher_better:
            best_v = np.max(arr)
            worst_v = np.min(arr)
            best_case = success_results[np.argmax(arr)]["\u7528\u4f8b\u540d\u79f0"]
            worst_case = success_results[np.argmin(arr)]["\u7528\u4f8b\u540d\u79f0"]
        else:
            best_v = np.min(arr)
            worst_v = np.max(arr)
            best_case = success_results[np.argmin(arr)]["\u7528\u4f8b\u540d\u79f0"]
            worst_case = success_results[np.argmax(arr)]["\u7528\u4f8b\u540d\u79f0"]

        direction = "\u2191 \u8d8a\u5927\u8d8a\u597d" if higher_better else "\u2193 \u8d8a\u5c0f\u8d8a\u597d"
        lines.append("| {} | {:.4f} | {:.4f} ({}) | {:.4f} ({}) | {:.4f} | {} |".format(
            col_name, mean_v, best_v, best_case, worst_v, worst_case, std_v, direction))
        metric_stats[col_name] = {
            "mean": mean_v, "best": best_v, "worst": worst_v,
            "best_case": best_case, "worst_case": worst_case,
            "higher_better": higher_better
        }

    lines.append("")

    lines.append("## \u4e09\u3001\u5404\u7528\u4f8b\u8be6\u7ec6\u7ed3\u679c")
    lines.append("")
    lines.append("| \u7528\u4f8b\u540d\u79f0 | \u5185\u70b9\u7387 | RMSE(px) | SSIM | \u753b\u5e03\u5229\u7528\u7387 | \u6e05\u6670\u5ea6\u4fdd\u6301\u7387 | \u8017\u65f6(s) |")
    lines.append("|----------|--------|----------|------|------------|--------------|---------|")

    for r in success_results:
        name = r.get("\u7528\u4f8b\u540d\u79f0", "-")
        inlier = r.get("\u5185\u70b9\u7387", "-")
        rmse = r.get("\u91cd\u6295\u5f71RMSE(\u50cf\u7d20)", "-")
        ssim = r.get("\u5168\u666fSSIM", "-")
        canvas = r.get("\u6709\u6548\u753b\u5e03\u5360\u6bd4", "-")
        sharp = r.get("\u6e05\u6670\u5ea6\u4fdd\u6301\u7387", "-")
        t = r.get("\u603b\u8017\u65f6(\u79d2)", "-")
        lines.append("| {} | {} | {} | {} | {} | {} | {} |".format(name, inlier, rmse, ssim, canvas, sharp, t))

    lines.append("")

    if fail_results:
        lines.append("## \u56db\u3001\u5931\u8d25\u7528\u4f8b\u5217\u8868")
        lines.append("")
        lines.append("| \u7528\u4f8b\u540d\u79f0 | \u9519\u8bef\u539f\u56e0 |")
        lines.append("|----------|----------|")
        for r in fail_results:
            err = r.get("\u9519\u8bef\u4fe1\u606f", "\u672a\u77e5\u9519\u8bef").replace("|", "/").replace("\n", " ")
            if len(err) > 80:
                err = err[:77] + "..."
            lines.append("| {} | {} |".format(r["\u7528\u4f8b\u540d\u79f0"], err))
        lines.append("")

    lines.append("## \u4e94\u3001\u6838\u5fc3\u7ed3\u8bba")
    lines.append("")

    conclusions = []

    if "\u5185\u70b9\u7387" in metric_stats:
        mean_inlier = metric_stats["\u5185\u70b9\u7387"]["mean"]
        if mean_inlier >= 0.7:
            conclusions.append("\u2705 **\u5339\u914d\u8d28\u91cf\u4f18\u79c0**\uff1a\u5e73\u5747\u5185\u70b9\u7387\u8fbe\u5230 {:.1%}\uff0c\u7279\u5f81\u5339\u914d\u6548\u679c\u826f\u597d\u3002".format(mean_inlier))
        elif mean_inlier >= 0.4:
            conclusions.append("\u26a0\ufe0f **\u5339\u914d\u8d28\u91cf\u4e00\u822c**\uff1a\u5e73\u5747\u5185\u70b9\u7387\u4e3a {:.1%}\uff0c\u5efa\u8bae\u4f18\u5316\u7279\u5f81\u63d0\u53d6\u6216\u5339\u914d\u53c2\u6570\u3002".format(mean_inlier))
        else:
            conclusions.append("\u274c **\u5339\u914d\u8d28\u91cf\u8f83\u5dee**\uff1a\u5e73\u5747\u5185\u70b9\u7387\u4ec5 {:.1%}\uff0c\u7279\u5f81\u5339\u914d\u5b58\u5728\u8f83\u5927\u95ee\u9898\u3002".format(mean_inlier))

    if "\u91cd\u6295\u5f71RMSE(\u50cf\u7d20)" in metric_stats:
        mean_rmse = metric_stats["\u91cd\u6295\u5f71RMSE(\u50cf\u7d20)"]["mean"]
        if mean_rmse <= 2:
            conclusions.append("\u2705 **\u51e0\u4f55\u914d\u51c6\u7cbe\u5ea6\u9ad8**\uff1a\u5e73\u5747\u91cd\u6295\u5f71\u8bef\u5dee\u4ec5 {:.2f} \u50cf\u7d20\uff0c\u5bf9\u9f50\u6548\u679c\u4f18\u79c0\u3002".format(mean_rmse))
        elif mean_rmse <= 5:
            conclusions.append("\u26a0\ufe0f **\u51e0\u4f55\u914d\u51c6\u7cbe\u5ea6\u4e00\u822c**\uff1a\u5e73\u5747\u91cd\u6295\u5f71\u8bef\u5dee {:.2f} \u50cf\u7d20\uff0c\u5efa\u8bae\u4f18\u5316\u5355\u5e94\u6027\u4f30\u8ba1\u3002".format(mean_rmse))
        else:
            conclusions.append("\u274c **\u51e0\u4f55\u914d\u51c6\u7cbe\u5ea6\u5dee**\uff1a\u5e73\u5747\u91cd\u6295\u5f71\u8bef\u5dee\u8fbe {:.2f} \u50cf\u7d20\uff0c\u5b58\u5728\u660e\u663e\u9519\u4f4d\u3002".format(mean_rmse))

    if "\u5168\u666fSSIM" in metric_stats:
        mean_ssim = metric_stats["\u5168\u666fSSIM"]["mean"]
        if mean_ssim >= 0.8:
            conclusions.append("\u2705 **\u91cd\u53e0\u533a\u4e00\u81f4\u6027\u597d**\uff1a\u5e73\u5747SSIM\u4e3a {:.3f}\uff0c\u62fc\u63a5\u8fc7\u6e21\u81ea\u7136\u3002".format(mean_ssim))
        elif mean_ssim >= 0.5:
            conclusions.append("\u26a0\ufe0f **\u91cd\u53e0\u533a\u4e00\u81f4\u6027\u4e00\u822c**\uff1a\u5e73\u5747SSIM\u4e3a {:.3f}\uff0c\u5b58\u5728\u53ef\u89c1\u62fc\u63a5\u7f1d\u6216\u8272\u5dee\u3002".format(mean_ssim))
        else:
            conclusions.append("\u274c **\u91cd\u53e0\u533a\u4e00\u81f4\u6027\u5dee**\uff1a\u5e73\u5747SSIM\u4ec5 {:.3f}\uff0c\u91cd\u53e0\u533a\u57df\u878d\u5408\u6548\u679c\u5dee\u3002".format(mean_ssim))

    if "\u6709\u6548\u753b\u5e03\u5360\u6bd4" in metric_stats:
        mean_canvas = metric_stats["\u6709\u6548\u753b\u5e03\u5360\u6bd4"]["mean"]
        if mean_canvas > 0.7:
            canvas_note = "\u753b\u5e03\u5229\u7528\u5145\u5206"
        else:
            canvas_note = "\u5b58\u5728\u8f83\u591a\u7a7a\u767d\u533a\u57df\uff0c\u53ef\u8003\u8651\u4f18\u5316\u88c1\u526a\u7b56\u7565"
        conclusions.append("\ud83d\udcd0 \u5e73\u5747\u6709\u6548\u753b\u5e03\u5229\u7528\u7387\u4e3a {:.1%}\uff0c{}\u3002".format(mean_canvas, canvas_note))

    if "\u5185\u70b9\u7387" in metric_stats:
        conclusions.append("\ud83c\udfc6 \u7efc\u5408\u8868\u73b0\u6700\u4f73\u573a\u666f\uff1a**{}**\u3002".format(metric_stats["\u5185\u70b9\u7387"]["best_case"]))
        conclusions.append("\u26a0\ufe0f \u9700\u8981\u91cd\u70b9\u6539\u8fdb\u573a\u666f\uff1a**{}**\u3002".format(metric_stats["\u91cd\u6295\u5f71RMSE(\u50cf\u7d20)"]["worst_case"]))

    for c in conclusions:
        lines.append("- " + c)

    lines.append("")
    lines.append("---")
    lines.append("*\u62a5\u544a\u7531\u5168\u666f\u62fc\u63a5\u8bc4\u4f30\u5de5\u5177\u81ea\u52a8\u751f\u6210*")

    report_content = "\n".join(lines)

    out_dir = os.path.dirname(output_path)
    if out_dir and not os.path.exists(out_dir):
        os.makedirs(out_dir, exist_ok=True)

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(report_content)

    print(_color_text("\ud83d\udcdd \u8bc4\u4f30\u62a5\u544a\u5df2\u751f\u6210\uff1a" + output_path, "green"))

def run_task_evaluation(task_id: str, store_root: str = "./store", generate_csv: bool = True, generate_report: bool = False) -> dict:
    """
    生产环境专用：按约定目录规范执行单任务全景拼接评估
    :param task_id: 任务唯一ID，用于定位目录
    :param store_root: store 根目录的绝对/相对路径
    :param generate_csv: 是否生成CSV附件（本地调试默认True）
    :param generate_report: 是否生成Markdown报告，默认False
    :return: 完整评估结果字典
    """
    # 1. 构建标准目录路径，统一转绝对路径，彻底规避工作目录错位问题
    upload_case_dir = os.path.abspath(os.path.join(store_root, "uploads", task_id))
    analysis_output_dir = os.path.abspath(os.path.join(store_root, "analysis", task_id))

    # 2. 校验输入目录完整性（只读校验，不做任何修改）
    if not os.path.isdir(os.path.join(upload_case_dir, "input")):
        raise FileNotFoundError(f"任务 {task_id} 缺少 input 原图目录")
    if not os.path.isdir(os.path.join(upload_case_dir, "result")):
        raise FileNotFoundError(f"任务 {task_id} 缺少 result 拼接结果目录")

    # 3. Python 自建 analysis 输出目录（含所有父级目录）
    os.makedirs(analysis_output_dir, exist_ok=True)

    # 4. 复用你原有的核心评估器，零改动读取输入
    # （和本地 test_cases 目录结构完全一致，直接兼容）
    evaluator = PanoramaEvaluator(upload_case_dir)
    detail_metrics = evaluator.get_all_metrics()
    detail_metrics["\u7528\u4f8b\u540d\u79f0"] = task_id
    detail_metrics["\u72b6\u6001"] = "\u6210\u529f"
    composite_scores = evaluator.get_composite_scores(detail_metrics)

    for score_name, score_val in composite_scores.items():
        detail_metrics["\u5206\u6570_" + score_name] = round(score_val, 4)

    # 5. 输出 1：表格格式JSON结果（{title, headers, rows}）原子写入
    table_result = _metrics_to_table_json([detail_metrics], title="\u5168\u666f\u62fc\u63a5\u8bc4\u4f30\u7ed3\u679c")
    full_result = table_result
    json_save_path = os.path.join(analysis_output_dir, "evaluation_result.json")
    tmp_json = json_save_path + ".tmp"
    with open(tmp_json, "w", encoding="utf-8") as f:
        json.dump(full_result, f, ensure_ascii=False, indent=2)
    os.replace(tmp_json, json_save_path)

    # 6. 输出 2：CSV 格式结果表（可选，兼容导出）
    csv_save_path = None
    if generate_csv:
        csv_save_path = os.path.join(analysis_output_dir, "evaluation_result.csv")
        with open(csv_save_path, "w", encoding="utf-8-sig", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=list(detail_metrics.keys()))
            writer.writeheader()
            writer.writerow(detail_metrics)

    # 7. 输出 3：单任务专用可视化图表（仪表盘+雷达图，英文文本）
    generate_single_task_charts(detail_metrics, composite_scores, analysis_output_dir, use_english=True)

    # 8. 输出 4：Markdown 格式评估报告（可选）
    if generate_report:
        if not csv_save_path:
            csv_save_path = os.path.join(analysis_output_dir, "_temp_report.csv")
            with open(csv_save_path, "w", encoding="utf-8-sig", newline="") as f:
                w = csv.DictWriter(f, fieldnames=list(detail_metrics.keys()))
                w.writeheader()
                w.writerow(detail_metrics)
        report_save_path = os.path.join(analysis_output_dir, "evaluation_report.md")
        generate_markdown_report(
            csv_save_path,
            report_save_path,
            report_title=f"任务 {task_id} 全景拼接质量评估报告"
        )
        if not generate_csv:
            os.remove(csv_save_path)

    return full_result


HAS_SIGALRM = hasattr(signal, "SIGALRM")


def _timeout_handler_prod(signum, frame):
    raise TimeoutError("analysis timeout (30s limit)")


def run_production_analysis(task_dir: str, output_dir: str, generate_report: bool = False, generate_csv: bool = False) -> dict:
    """
    生产环境标准分析入口，完全对齐接口文档
    :param task_dir: 任务目录（sys.argv[1]，Go传入）
    :param output_dir: 分析输出目录（sys.argv[2]，Go已提前创建）
    :param generate_report: 是否生成Markdown报告，线上默认False
    :param generate_csv: 是否生成CSV下载附件，线上默认False（仅JSON+PNG）
    :return: 完整评估结果字典
    """
    old_handler = None
    if HAS_SIGALRM:
        old_handler = signal.signal(signal.SIGALRM, _timeout_handler_prod)
        signal.alarm(30)

    try:
        evaluator = PanoramaEvaluator(task_dir)
        detail_metrics = evaluator.get_all_metrics()
        detail_metrics["\u7528\u4f8b\u540d\u79f0"] = "current_task"
        detail_metrics["\u72b6\u6001"] = "\u6210\u529f"
        composite_scores = evaluator.get_composite_scores(detail_metrics)

        for score_name, score_val in composite_scores.items():
            detail_metrics["\u5206\u6570_" + score_name] = round(score_val, 4)

        table_result = _metrics_to_table_json([detail_metrics], title="\u5168\u666f\u62fc\u63a5\u8bc4\u4f30\u7ed3\u679c")
        full_result = table_result

        json_save_path = os.path.join(output_dir, "evaluation_result.json")
        tmp_json_path = json_save_path + ".tmp"
        with open(tmp_json_path, "w", encoding="utf-8") as f:
            json.dump(full_result, f, ensure_ascii=False, indent=2)
        os.replace(tmp_json_path, json_save_path)

        if generate_csv:
            csv_save_path = os.path.join(output_dir, "evaluation_result.csv")
            with open(csv_save_path, "w", encoding="utf-8-sig", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=list(detail_metrics.keys()))
                writer.writeheader()
                writer.writerow(detail_metrics)

        generate_single_task_charts(detail_metrics, composite_scores, output_dir, use_english=True)

        if generate_report:
            csv_for_report = os.path.join(output_dir, "_temp_report.csv")
            with open(csv_for_report, "w", encoding="utf-8-sig", newline="") as f:
                w = csv.DictWriter(f, fieldnames=list(detail_metrics.keys()))
                w.writeheader()
                w.writerow(detail_metrics)
            report_save_path = os.path.join(output_dir, "evaluation_report.md")
            generate_markdown_report(
                csv_for_report,
                report_save_path,
                report_title="\u5168\u666f\u62fc\u63a5\u8d28\u91cf\u8bc4\u4f30\u62a5\u544a"
            )
            os.remove(csv_for_report)

        print(f"analysis completed, output: {output_dir}")
        return full_result
    finally:
        if HAS_SIGALRM:
            signal.alarm(0)
            if old_handler is not None:
                signal.signal(signal.SIGALRM, old_handler)


def main():
    # ===== 生产环境标准入口：2个位置参数（优先级最高，对齐接口文档）=====
    if len(sys.argv) == 3 and not sys.argv[1].startswith("-"):
        task_dir = _ensure_absolute_path(sys.argv[1])
        output_dir = _ensure_absolute_path(sys.argv[2])
        try:
            run_production_analysis(task_dir, output_dir)
            sys.exit(0)
        except Exception as e:
            print(f"analysis failed: {str(e)}", file=sys.stderr)
            sys.exit(1)

    # ===== 以下为原有本地调试逻辑，全部保留不变 =====
    parser = argparse.ArgumentParser(
        description="全景图像拼接质量评估工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用示例:
  python panorama_evaluator.py --task-id task_001 --store-root ./store
  python panorama_evaluator.py --batch ./test_cases
  python panorama_evaluator.py --batch ./test_cases --charts --report
  python panorama_evaluator.py --compare result_a.csv result_b.csv --label-a "我的算法" --label-b "OpenCV"
  python panorama_evaluator.py --quick img1.jpg img2.jpg panorama.jpg
  python panorama_evaluator.py --check ./test_cases/case01
        """
    )

    # 生产环境任务模式
    parser.add_argument("--task-id", type=str, help="生产环境：指定评估任务ID")
    parser.add_argument("--store-root", type=str, default="./store", help="生产环境：store根目录路径")

    # 批量评估模式
    parser.add_argument("--batch", "-b", type=str, metavar="TEST_DIR",
                        help="批量评估模式：指定测试用例根目录")
    parser.add_argument("--output", "-o", type=str, default=None,
                        help="CSV结果输出路径")
    parser.add_argument("--charts", "-c", action="store_true",
                        help="批量评估后自动生成可视化图表")
    parser.add_argument("--report", "-r", action="store_true",
                        help="批量评估后自动生成Markdown评估报告")
    parser.add_argument("--chart-dir", type=str, default=None,
                        help="图表输出目录")

    # 基准对比模式
    parser.add_argument("--compare", type=str, nargs=2, metavar=("CSV_A", "CSV_B"),
                        help="基准对比模式：对比两组CSV结果")
    parser.add_argument("--label-a", type=str, default="A组",
                        help="对比模式下A组标签")
    parser.add_argument("--label-b", type=str, default="B组",
                        help="对比模式下B组标签")
    parser.add_argument("--compare-dir", type=str, default=None,
                        help="对比结果输出目录")

    # 快速评估模式
    parser.add_argument("--quick", "-q", type=str, nargs=3, metavar=("IMG1", "IMG2", "PANORAMA"),
                        help="快速评估模式：直接传入两张原图和全景图路径")
    parser.add_argument("--H", type=str, default=None,
                        help="快速评估模式：单应性矩阵H.npy路径（可选）")
    parser.add_argument("--matches", type=int, default=0,
                        help="快速评估模式：总匹配对数（可选）")
    parser.add_argument("--inliers", type=int, default=0,
                        help="快速评估模式：内点数（可选）")

    # 通用选项
    parser.add_argument("--no-color", action="store_true",
                        help="禁用终端彩色输出")
    parser.add_argument("--check", type=str, metavar="CASE_DIR",
                        help="仅检查用例目录结构，不执行评估")

    args = parser.parse_args()

    if args.no_color:
        CONFIG["color_enabled"] = False

    _setup_matplotlib()

    # ===== 生产环境：任务式评估（优先级最高）=====
    if args.task_id:
        try:
            result = run_task_evaluation(args.task_id, args.store_root)
            output_dir = os.path.join(args.store_root, "analysis", args.task_id)
            print(_color_text(f"✅ 任务 {args.task_id} 评估完成", "green"))
            print(f"   结果目录：{os.path.abspath(output_dir)}")
            print(f"   综合得分：{result['composite_scores'].get('综合得分', '-')}")
        except Exception as e:
            print(_color_text(f"❌ 评估失败：{str(e)}", "red"))
            sys.exit(1)
        return

    if args.check:
        case_path = _ensure_absolute_path(args.check)
        print(_color_text("检查用例目录：" + case_path, "cyan"))
        is_valid, missing, guidance = _validate_case_structure(case_path)
        if is_valid:
            print(_color_text("✅ 目录结构完整，可以进行评估", "green"))
        else:
            print(_color_text("❌ 目录结构存在问题", "red"))
            if missing:
                print("缺失项：" + ", ".join(missing))
            print(guidance)
        return

    if args.batch:
        test_dir = _ensure_absolute_path(args.batch)
        output_csv = _ensure_absolute_path(args.output or CONFIG["default_csv"])
        try:
            tester = BatchTester(test_dir, output_csv)
            results = tester.run()

            if args.charts:
                chart_dir = args.chart_dir or os.path.join(os.path.dirname(output_csv), CONFIG["default_chart_dir"])
                generate_charts(output_csv, chart_dir)

            if args.report:
                report_path = os.path.join(os.path.dirname(output_csv), CONFIG["default_report"])
                generate_markdown_report(output_csv, report_path)
        except Exception as e:
            print(_color_text("批量评估失败：" + str(e), "red"))
            sys.exit(1)
        return

    if args.compare:
        csv_a, csv_b = args.compare
        try:
            generate_comparison(csv_a, csv_b, args.compare_dir, args.label_a, args.label_b)
        except Exception as e:
            print(_color_text("对比失败：" + str(e), "red"))
            sys.exit(1)
        return

    if args.quick:
        img1, img2, pano = args.quick
        try:
            H = None
            if args.H:
                H = np.load(_ensure_absolute_path(args.H),allow_pickle=True)
            qe = QuickEvaluator(img1, img2, pano, H=H,
                                total_matches=args.matches, inlier_num=args.inliers)
            metrics = qe.evaluate()

            print(_color_text("\n===== 快速评估结果 =====", "cyan"))
            for k, v in metrics.items():
                print("  " + k + ": " + str(v))
            print()
        except Exception as e:
            print(_color_text("快速评估失败：" + str(e), "red"))
            sys.exit(1)
        return

    # 默认执行逻辑
    print(_color_text("全景图像拼接质量评估工具", "cyan"))
    print("使用 -h 查看帮助信息")
    print()
    print("运行默认示例（批量评估 test_cases 目录）...")
    # 获取当前脚本自身所在的绝对目录，彻底规避工作目录错位问题
    SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
    default_test_root = os.path.join(SCRIPT_DIR, "test_cases")
    default_csv_path = os.path.join(SCRIPT_DIR, CONFIG["default_csv"])
    default_chart_dir = os.path.join(SCRIPT_DIR, "答辩图表")

    if os.path.isdir(default_test_root):
        tester = BatchTester(default_test_root, default_csv_path)
        tester.run()
        generate_charts(default_csv_path, default_chart_dir)
    else:
        print(_color_text("未找到默认测试目录：" + default_test_root, "yellow"))
        print("请使用命令行参数指定运行模式，或使用 -h 查看帮助")


if __name__ == "__main__":
    main()