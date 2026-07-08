#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
PIS-web 评估管线适配器
桥接 stitch.py(新格式) → eval_core.py(评估核心) → 前端(展示格式)

调用方式: python3 eval_pipeline.py {任务目录} {分析输出目录}

职责:
  A. 入参桥接 — 把 stitch.py 新格式转为 eval_core 认识的格式
  B. 调评估核心 — from eval_core import run_production_analysis
  C. 出参转换 — 读 eval_core 产出的 evaluation_result.json，映射出
     eval_result.json + full_metrics.json + 中文大尺寸图表
"""

import sys
import os
import json
import time
import pickle
import shutil

import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

# ===================== 配置 =====================

CHART_DPI = 200
LARGE_DPI = 200
FONT_FAMILY = ["SimHei", "Microsoft YaHei", "WenQuanYi Micro Hei", "DejaVu Sans"]

CHART_COLORS = {
    "inlier_ratio": "#4e79a7",
    "rmse": "#e15759",
    "ssim": "#59a14f",
    "time": "#f28e2b",
    "sharpness": "#76b7b2",
    "canvas": "#edc948",
    "overall": "#59a14f",
}

_GAUGE_DEFS = [
    ("内点率",     "内点率",     1.0,  True,  True,  "inlier_ratio"),
    ("重投影RMSE", "重投影RMSE(像素)", 10.0, False, False, "rmse"),
    ("全景SSIM",   "全景SSIM",    1.0,  True,  True,  "ssim"),
    ("总耗时",     "总耗时(秒)",  30.0, False, False, "time"),
    ("画布利用率", "有效画布占比", 1.0,  True,  True,  "canvas"),
    ("综合得分",   "综合得分",    1.0,  True,  True,  "overall"),
]


def _safe_float(val, default=None):
    if val == "-" or val is None:
        return default
    try:
        return float(val)
    except (ValueError, TypeError):
        return default


def _setup_matplotlib():
    plt.rcParams["font.sans-serif"] = FONT_FAMILY
    plt.rcParams["axes.unicode_minus"] = False
    plt.rcParams["figure.dpi"] = CHART_DPI


# ==================== 步骤 A: 入参桥接 ====================

def bridge_input(task_dir):
    """将 stitch.py 新格式转为 eval_core 兼容格式（保留多对数据，仅转换时间单位）"""
    result_dir = os.path.join(task_dir, "result")

    # H_list.npy / inliers_list.pkl 保留不动 —— PanoramaEvaluator 已支持直接读取多对格式

    # --- result_info.json: 仅转换 total_time ms→s，保留 pairs 数组 ---
    info_path = os.path.join(result_dir, "result_info.json")
    if os.path.exists(info_path):
        try:
            with open(info_path, "r", encoding="utf-8") as f:
                info = json.load(f)
        except Exception:
            return

        # 如果已经是转换后的格式 (没有 pairs 但有 total_time 已是秒级)，跳过
        if "pairs" not in info:
            return

        # 备份原始新格式
        backup_path = os.path.join(result_dir, "result_info_full.json")
        if not os.path.exists(backup_path):
            try:
                shutil.copy2(info_path, backup_path)
            except Exception:
                pass

        # stitch.py 产出毫秒 → 转为秒，保留 pairs 供多对评估使用
        info["total_time"] = round(float(info.get("total_time", 0)) / 1000.0, 4)

        try:
            with open(info_path, "w", encoding="utf-8") as f:
                json.dump(info, f, ensure_ascii=False, indent=2)
        except Exception:
            pass


# ==================== 步骤 C: 出参转换 ====================

def _parse_evaluation_table(eval_path):
    """解析 eval_core 产出的 evaluation_result.json，返回 {header: value} 字典"""
    with open(eval_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    headers = data.get("headers", [])
    rows = data.get("rows", [])
    if not rows:
        return {}

    row = rows[0]
    result = {}
    for i, h in enumerate(headers):
        result[h] = row[i] if i < len(row) else None
    return result


def _extract_field(data, *keys):
    """从 data 字典中取第一个存在的字段值"""
    for k in keys:
        if k in data:
            return data[k]
    return None


def build_eval_result(data, case_name):
    """构建精简摘要 eval_result.json"""
    inlier_ratio = _extract_field(data, "内点率")
    if isinstance(inlier_ratio, (int, float)):
        inlier_ratio = round(float(inlier_ratio), 4)

    rmse = _extract_field(data, "重投影RMSE(像素)")
    if isinstance(rmse, (int, float)):
        rmse = round(float(rmse), 4)

    ssim_val = _extract_field(data, "全景SSIM")
    if isinstance(ssim_val, (int, float)):
        ssim_val = round(float(ssim_val), 4)

    canvas = _extract_field(data, "有效画布占比")
    if isinstance(canvas, (int, float)):
        canvas = round(float(canvas), 4)

    sharpness = _extract_field(data, "清晰度保持率")
    if isinstance(sharpness, (int, float)):
        sharpness = round(float(sharpness), 4)

    overall = _extract_field(data, "分数_综合得分", "综合得分")
    if isinstance(overall, (int, float)):
        overall = round(float(overall), 4)

    cost = _extract_field(data, "总耗时(秒)")
    if isinstance(cost, (int, float)):
        cost = round(float(cost), 4)

    return {
        "用例名称": case_name,
        "状态": data.get("状态", "成功"),
        "内点率": inlier_ratio,
        "重投影RMSE": rmse,
        "全景SSIM": ssim_val,
        "有效画布占比": canvas,
        "清晰度保持率": sharpness,
        "综合得分": overall if overall is not None else 0,
        "总耗时(秒)": cost if cost is not None else 0,
        "警告": data.get("警告", ""),
    }


def build_full_metrics(data, case_name, image_count):
    """构建分组详细数据 full_metrics.json"""
    def _f(val):
        if isinstance(val, float):
            return round(val, 6)
        if val == "-" or val is None:
            return None
        if isinstance(val, str):
            try:
                return round(float(val), 6)
            except (ValueError, TypeError):
                return val
        return val

    groups = {
        "匹配质量": {
            "总匹配对数": _f(data.get("总匹配对数")),
            "RANSAC内点数": _f(data.get("RANSAC内点数")),
            "内点率": _f(data.get("内点率")),
        },
        "重投影误差": {
            "重投影RMSE(像素)": _f(data.get("重投影RMSE(像素)")),
            "重投影中位数(像素)": _f(data.get("重投影中位数(像素)")),
            "重投影P95(像素)": _f(data.get("重投影P95(像素)")),
        },
        "拼接一致性": {
            "全景SSIM": _f(data.get("全景SSIM")),
            "全景SSIM_min": _f(data.get("全景SSIM_min")),
            "全景SSIM_std": _f(data.get("全景SSIM_std")),
        },
        "画布利用率": {
            "有效画布占比": _f(data.get("有效画布占比")),
            "空白占比": _f(data.get("空白占比")),
        },
        "清晰度": {
            "全景图清晰度方差": _f(data.get("全景图清晰度方差")),
            "原图平均清晰度方差": _f(data.get("原图平均清晰度方差")),
            "清晰度保持率": _f(data.get("清晰度保持率")),
        },
        "综合评分": {
            "匹配质量": _f(_extract_field(data, "分数_匹配质量")),
            "对齐精度": _f(_extract_field(data, "分数_对齐精度")),
            "拼接一致性": _f(_extract_field(data, "分数_拼接一致性")),
            "画布利用率": _f(_extract_field(data, "分数_画布利用率")),
            "清晰度": _f(_extract_field(data, "分数_清晰度")),
            "运行效率": _f(_extract_field(data, "分数_运行效率")),
            "综合得分": _f(_extract_field(data, "分数_综合得分")),
        },
    }

    return {
        "用例名称": case_name,
        "状态": data.get("状态", "成功"),
        "图片数量": image_count,
        "总耗时(秒)": _f(data.get("总耗时(秒)")),
        "警告": data.get("警告", ""),
        "分组": groups,
    }


# ==================== 图表生成（中文大尺寸，覆盖 eval_core 英文图） ====================

def _draw_gauge(ax, value, title, max_val, good_high=True, color='#4e79a7',
                is_pct=False, fontsize_val=28, fontsize_title=14):
    ax.set_xlim(-1.2, 1.2)
    ax.set_ylim(-0.2, 1.2)
    ax.set_aspect('equal')
    ax.axis('off')

    theta = np.linspace(np.pi, 0, 100)
    ax.plot(np.cos(theta), np.sin(theta), color='#e8e8e8', linewidth=18,
            solid_capstyle='round')

    if value is not None:
        ratio = _safe_float(value, 0.0)
        if not good_high:
            ratio = max(0.0, min(1.0, (max_val - ratio) / max_val))
        else:
            ratio = max(0.0, min(1.0, ratio / max_val))
        theta_fill = np.linspace(np.pi, np.pi - ratio * np.pi, 100)
        ax.plot(np.cos(theta_fill), np.sin(theta_fill), color=color, linewidth=18,
                solid_capstyle='round')
        if is_pct:
            display = f"{_safe_float(value, 0.0):.1%}"
        else:
            display = f"{_safe_float(value, 0.0):.2f}"
        ax.text(0, 0.15, display, ha='center', va='center',
                fontsize=fontsize_val, fontweight='bold', color='#333333')
    else:
        ax.text(0, 0.15, "N/A", ha='center', va='center',
                fontsize=fontsize_val, fontweight='bold', color='#cccccc')

    ax.text(0, -0.18, title, ha='center', va='center',
            fontsize=fontsize_title, color='#555555')


def _generate_large_gauge(value, title, max_val, good_high, is_pct, color, output_path):
    _setup_matplotlib()
    fig, ax = plt.subplots(figsize=(6, 5))
    _draw_gauge(ax, value, title, max_val, good_high=good_high, color=color,
                is_pct=is_pct, fontsize_val=38, fontsize_title=16)
    plt.tight_layout()
    plt.savefig(output_path, dpi=LARGE_DPI, bbox_inches='tight', facecolor='white')
    plt.close()


def generate_charts(data, output_dir):
    """基于解析后的指标数据，生成中文大尺寸图表"""
    _setup_matplotlib()
    os.makedirs(output_dir, exist_ok=True)

    gauge_data = {
        "内点率":    _safe_float(data.get("内点率"), None),
        "重投影RMSE": _safe_float(data.get("重投影RMSE(像素)"), None),
        "全景SSIM":   _safe_float(data.get("全景SSIM"), None),
        "总耗时":     _safe_float(data.get("总耗时(秒)"), None),
        "画布利用率": _safe_float(data.get("有效画布占比"), None),
        "综合得分":   _safe_float(_extract_field(data, "分数_综合得分"), 0.0),
    }

    # --- 1. 仪表盘总览 ---
    fig, axes = plt.subplots(2, 3, figsize=(20, 13))
    fig.suptitle("全景拼接质量评估", fontsize=20, fontweight='bold', color='#333333')

    for idx, (label, key, max_v, good_hi, is_pct, color_key) in enumerate(_GAUGE_DEFS):
        row, col = divmod(idx, 3)
        val = gauge_data[label]
        _draw_gauge(axes[row, col], val, label, max_v, good_high=good_hi,
                    color=CHART_COLORS[color_key], is_pct=is_pct,
                    fontsize_val=32, fontsize_title=14)

    plt.tight_layout(rect=[0, 0, 1, 0.94])
    plt.savefig(os.path.join(output_dir, "metrics_dashboard.png"),
                dpi=CHART_DPI, bbox_inches='tight', facecolor='white')
    plt.close()

    # --- 2. 雷达图 ---
    dims = ["匹配质量", "对齐精度", "拼接一致性", "画布利用率", "清晰度", "运行效率"]
    score_map = {
        "匹配质量": _safe_float(_extract_field(data, "分数_匹配质量"), 0.0),
        "对齐精度": _safe_float(_extract_field(data, "分数_对齐精度"), 0.0),
        "拼接一致性": _safe_float(_extract_field(data, "分数_拼接一致性"), 0.0),
        "画布利用率": _safe_float(_extract_field(data, "分数_画布利用率"), 0.0),
        "清晰度": _safe_float(_extract_field(data, "分数_清晰度"), 0.0),
        "运行效率": _safe_float(_extract_field(data, "分数_运行效率"), 0.0),
    }

    dim_labels = [f"{d}\n({score_map[d]:.2f})" for d in dims]
    n_dims = len(dims)
    angles = np.linspace(0, 2 * np.pi, n_dims, endpoint=False).tolist()
    angles += angles[:1]
    values = [score_map[d] for d in dims]
    values += values[:1]

    fig, ax = plt.subplots(figsize=(10, 10), subplot_kw=dict(polar=True))
    ax.plot(angles, values, 'o-', linewidth=2.5, color='#4e79a7', markersize=8)
    ax.fill(angles, values, alpha=0.2, color='#4e79a7')
    ax.set_xticks(angles[:-1])
    ax.set_xticklabels(dim_labels, fontsize=13, fontweight='bold')
    ax.set_ylim(0, 1)
    ax.set_yticks([0.2, 0.4, 0.6, 0.8, 1.0])
    ax.set_yticklabels(['0.2', '0.4', '0.6', '0.8', '1.0'], fontsize=10)
    ax.grid(True, linestyle='--', alpha=0.5)
    ax.set_title("综合质量雷达图", fontsize=17, fontweight='bold', pad=25, color='#333333')
    plt.tight_layout()
    plt.savefig(os.path.join(output_dir, "quality_radar.png"),
                dpi=CHART_DPI, bbox_inches='tight', facecolor='white')
    plt.close()

    # --- 3. 大图：每项指标独立图 ---
    for label, key, max_v, good_hi, is_pct, color_key in _GAUGE_DEFS:
        val = gauge_data[label]
        _generate_large_gauge(val, label, max_v, good_hi, is_pct,
                              CHART_COLORS[color_key],
                              os.path.join(output_dir, f"gauge_{label}.png"))

    # --- 4. 指标明细表 ---
    _generate_table_image(data, score_map, output_dir)


def _generate_table_image(data, score_map, output_dir):
    """生成指标数据表格 PNG"""
    _setup_matplotlib()

    rows = []
    metric_map = [
        ("内点率",        "内点率",        True,  "RANSAC 内点数 / 总匹配对数"),
        ("总匹配对数",    "总匹配对数",    False, "相邻图对 knnMatch 匹配总数"),
        ("RANSAC内点数",  "RANSAC内点数",  False, "通过 Lowe's ratio + RANSAC 筛选的内点数"),
        ("重投影RMSE",    "重投影RMSE(像素)", False, "src 点经 H 投影到 dst 空间的均方根误差"),
        ("全景SSIM",      "全景SSIM",     True,  "全景图跨切片结构相似度 (0-1)"),
        ("有效画布占比",  "有效画布占比",  True,  "全景图中非黑像素占比"),
        ("清晰度保持率",  "清晰度保持率",  True,  "全景图 Laplacian 方差 / 原图均值"),
        ("总耗时",        "总耗时(秒)",    False, "拼接总耗时（秒）"),
        ("综合得分",      "分数_综合得分", True,  "6 维评分归一化均值"),
    ]

    for label, key, is_pct, desc in metric_map:
        val = data.get(key, "-")
        if isinstance(val, float):
            if is_pct:
                val_str = f"{val:.1%}"
            else:
                val_str = f"{val:.4f}" if abs(val) < 10 else f"{val:.2f}"
        elif val == "-" or val is None:
            val_str = "-"
        else:
            val_str = str(val)
        rows.append([label, val_str, desc])

    n_rows = len(rows)
    fig, ax = plt.subplots(figsize=(14, n_rows * 0.55 + 1.2))
    ax.axis('off')
    fig.patch.set_facecolor('white')

    col_labels = ["指标", "数值", "说明"]
    col_widths = [0.15, 0.15, 0.7]

    table = ax.table(cellText=rows, colLabels=col_labels, colWidths=col_widths,
                     cellLoc='center', loc='center')
    table.auto_set_font_size(False)
    table.set_fontsize(11)
    table.scale(1, 1.6)

    for key, cell in table.get_celld().items():
        cell.set_edgecolor('#e0e0e0')
        cell.set_linewidth(0.5)
        if key[0] == 0:
            cell.set_facecolor('#4e79a7')
            cell.set_text_props(color='white', fontweight='bold', fontsize=12)
        elif key[0] % 2 == 0:
            cell.set_facecolor('#f7f9fc')
        else:
            cell.set_facecolor('white')
        if key[1] == 1 and key[0] > 0:
            cell.set_text_props(fontweight='bold')

    ax.set_title("全景拼接质量评估 — 指标明细表", fontsize=16, fontweight='bold',
                 color='#333333', pad=20)
    plt.tight_layout()
    plt.savefig(os.path.join(output_dir, "metrics_table.png"),
                dpi=CHART_DPI, bbox_inches='tight', facecolor='white')
    plt.close()


# ==================== 主程序 ====================

def main():
    if len(sys.argv) != 3:
        print("用法: python3 eval_pipeline.py {任务目录} {分析输出目录}", file=sys.stderr)
        sys.exit(0)

    task_dir = os.path.abspath(sys.argv[1])
    output_dir = os.path.abspath(sys.argv[2])
    case_name = os.path.basename(task_dir)

    # 确保 scripts/ 在 sys.path 中（eval_core.py 所在目录）
    script_dir = os.path.dirname(os.path.abspath(__file__))
    if script_dir not in sys.path:
        sys.path.insert(0, script_dir)

    try:
        start = time.time()

        # ==== A. 入参桥接：新格式 → 旧格式 ====
        bridge_input(task_dir)

        # 确保输出目录存在（Go 后端已创建，此处兜底）
        os.makedirs(output_dir, exist_ok=True)

        # ==== B. 调评估核心 ====
        from eval_core import run_production_analysis
        run_production_analysis(task_dir, output_dir)

        # ==== C. 出参转换 ====
        eval_path = os.path.join(output_dir, "evaluation_result.json")
        if not os.path.exists(eval_path):
            raise FileNotFoundError(f"eval_core 未产出 evaluation_result.json")

        data = _parse_evaluation_table(eval_path)

        # 图片数量：优先从 result_info.json 的 pairs 推算，回退到输入目录统计
        info_path = os.path.join(task_dir, "result", "result_info.json")
        backup_path = os.path.join(task_dir, "result", "result_info_full.json")
        image_count = 0
        # 优先从转换后的 result_info.json 读取（bridge_input 已保留 pairs）
        if os.path.exists(info_path):
            try:
                with open(info_path, "r", encoding="utf-8") as f:
                    info = json.load(f)
                if "pairs" in info:
                    image_count = len(info["pairs"]) + 1
            except Exception:
                pass
        # 回退1：从备份文件读取
        if image_count == 0 and os.path.exists(backup_path):
            try:
                with open(backup_path, "r", encoding="utf-8") as f:
                    info = json.load(f)
                image_count = len(info.get("pairs", [])) + 1
            except Exception:
                pass
        # 回退2：扫描输入目录
        if image_count == 0:
            input_dir = os.path.join(task_dir, "input")
            if os.path.isdir(input_dir):
                exts = ('.jpg', '.jpeg', '.png', '.bmp', '.tiff')
                image_count = sum(1 for f in os.listdir(input_dir)
                                  if f.lower().endswith(exts))

        # 写 eval_result.json
        eval_result = build_eval_result(data, case_name)
        os.makedirs(output_dir, exist_ok=True)
        with open(os.path.join(output_dir, "eval_result.json"), "w", encoding="utf-8") as f:
            json.dump(eval_result, f, ensure_ascii=False, indent=2)

        # 写 full_metrics.json
        full_metrics = build_full_metrics(data, case_name, image_count)
        with open(os.path.join(output_dir, "full_metrics.json"), "w", encoding="utf-8") as f:
            json.dump(full_metrics, f, ensure_ascii=False, indent=2)

        # 生成中文图表（覆盖 eval_core 英文图）
        generate_charts(data, output_dir)

        elapsed = int((time.time() - start) * 1000)
        print(f"analysis completed, output: {output_dir}, cost: {elapsed}ms")

    except Exception as e:
        os.makedirs(output_dir, exist_ok=True)
        error_result = {"用例名称": case_name, "状态": "失败", "错误信息": str(e)}
        try:
            with open(os.path.join(output_dir, "eval_result.json"), "w", encoding="utf-8") as f:
                json.dump(error_result, f, ensure_ascii=False, indent=2)
        except Exception:
            pass
        try:
            with open(os.path.join(output_dir, "full_metrics.json"), "w", encoding="utf-8") as f:
                json.dump(error_result, f, ensure_ascii=False, indent=2)
        except Exception:
            pass
        print(f"analysis failed: {e}", file=sys.stderr)

    sys.exit(0)


if __name__ == "__main__":
    main()
