import numpy as np
import cv2
import random
# ========== 新增：GUI界面依赖 ==========
import tkinter as tk
from tkinter import filedialog, messagebox


def matchKeyPoint(kps_l, kps_r, features_l, features_r, ratio):
    # 用OpenCV内置暴力匹配器（C++底层，速度远快于Python手写循环）
    bf = cv2.BFMatcher()
    matches = bf.knnMatch(features_l, features_r, k=2)

    # 保留原有的比率筛选逻辑，算法原理不变
    goodMatches = []
    for m, n in matches:
        if m.distance < ratio * n.distance:
            goodMatches.append((m.queryIdx, m.trainIdx))

    # 转换为和原来格式一致的坐标点对
    goodMatches_pos = []
    for (idx, correspondingIdx) in goodMatches:
        psA = (int(kps_l[idx].pt[0]), int(kps_l[idx].pt[1]))
        psB = (int(kps_r[correspondingIdx].pt[0]), int(kps_r[correspondingIdx].pt[1]))
        goodMatches_pos.append([psA, psB])
    return goodMatches_pos

def detectAndDescribe(img):
    # 限制最多提取 800 个特征点，足够拼接用，大幅减少后续计算量
    sift = cv2.SIFT_create(nfeatures=800)
    kps, features = sift.detectAndCompute(img, None)
    return kps, features


def drawMatches(img_left, img_right, matches_pos):
    hl, wl = img_left.shape[:2]
    hr, wr = img_right.shape[:2]
    vis = np.zeros((max(hl, hr), wl + wr, 3), dtype=np.uint8)
    vis[0:hl, 0:wl] = img_left
    vis[0:hr, wl:] = img_right
    for (img_left_pos, img_right_pos) in matches_pos:
        pos_l = img_left_pos
        pos_r = (img_right_pos[0] + wl, img_right_pos[1])
        cv2.circle(vis, pos_l, 3, (0, 0, 255), 1)
        cv2.circle(vis, pos_r, 3, (0, 255, 0), 1)
        cv2.line(vis, pos_l, pos_r, (255, 0, 0), 1)
    return vis


# P：源图像（左图）匹配点坐标
# m：目标图像（右图）匹配点坐标
def solve_homography(P, m):
    try:
        A = []
        for r in range(len(P)):
            A.append([-P[r, 0], -P[r, 1], -1, 0, 0, 0, P[r, 0] * m[r, 0], P[r, 1] * m[r, 0], m[r, 0]])
            A.append([0, 0, 0, -P[r, 0], -P[r, 1], -1, P[r, 0] * m[r, 1], P[r, 1] * m[r, 1], m[r, 1]])
        u, s, vt = np.linalg.svd(A)  # SVD求解齐次方程组 Ah=0
        H = np.reshape(vt[8], (3, 3))  # 取SVD最后一行作为解
        # 归一化，令 H[2,2] = 1
        H = (1 / H.item(8)) * H
    except:
        print("Error on compute H")
    return H


# 利用 RANSAC算法，计算H矩阵
def fitHomoMat(matches_pos, nIter=1000, th=5.0):
    dstPoints = []   # left image(destination image)
    srcPoints = []   # right image(source image)
    for dstPoint, srcPoint in matches_pos:
        dstPoints.append(list(dstPoint))
        srcPoints.append(list(srcPoint))
    dstPoints = np.array(dstPoints)
    srcPoints = np.array(srcPoints)
    # 利用RANSAC算法，获取最优的H矩阵
    NumSample = len(matches_pos)
    threshold = th
    NumIter = nIter
    NumRandomSubSample = 4
    MaxInlier = 0
    Best_H = None
    save_Inlier_pos = []
    for run in range(NumIter):
        # 随机采样
        SubSampleIdx = random.sample(range(NumSample), NumRandomSubSample)
        # 计算 H
        H = solve_homography(srcPoints[SubSampleIdx], dstPoints[SubSampleIdx])
        NumInlier = 0
        pos_Inlier = []
        for i in range(NumSample):
            if i not in SubSampleIdx:
                concatCoor = np.hstack((srcPoints[i], [1]))   # 添加z =1
                dstCoor = H @ concatCoor.T   # 计算目标点
                if dstCoor[2] <= 1e-8:   # 避免目标点 z 维度接近 0
                    continue
                dstCoor = dstCoor / dstCoor[2]   # 计算目标点坐标
                # 如果计算的目标点和匹配的目标点距离较近，则将这一对点定义为 Inlier
                if np.linalg.norm(dstCoor[:2] - dstPoints[i]) < threshold:
                    NumInlier = NumInlier + 1
                    pos_Inlier.append((srcPoints[i], dstPoints[i]))
        if MaxInlier < NumInlier:
            MaxInlier = NumInlier
            Best_H = H
            save_Inlier_pos = pos_Inlier
    return Best_H, save_Inlier_pos


def warp(img_left, img_right, HomoMat, blending_mode="linearBlending"):
    hl, wl = img_left.shape[:2]
    hr, wr = img_right.shape[:2]
    stitch_img = np.zeros((max(hl, hr), wl + wr, 3), dtype=np.uint8)
    if blending_mode == "noBlending":
        stitch_img[:hl, :wl] = img_left
    # 逆矩阵映射原图逻辑，无任何mask下标操作
    inv_H = np.linalg.inv(HomoMat)
    for i in range(stitch_img.shape[0]):
        for j in range(stitch_img.shape[1]):
            coor = np.array([j, i, 1])
            img_right_coor = inv_H @ coor
            img_right_coor /= img_right_coor[2]
            y, x = int(round(img_right_coor[0])), int(round(img_right_coor[1]))
            if x < 0 or x >= hr or y < 0 or y >= wr:
                continue
            stitch_img[i, j] = img_right[x, y]
    # 只传列表两个参数，匹配原版融合函数入参
    if blending_mode == "linearBlending":
        stitch_img = linearBlending([img_left, stitch_img])
    elif blending_mode == "linearBlendingWithConstantWidth":
        stitch_img = linearBlendingWithConstantWidth([img_left, stitch_img])
    stitch_img = removeBlackBorder(stitch_img)
    return stitch_img
    #去除黑边
def removeBlackBorder(img):
    h, w = img.shape[:2]
    reduced_h, reduced_w = h, w
    # right to left
    for col in range(w - 1, -1, -1):
        all_black = True
        for i in range(h):
            if (np.count_nonzero(img[i, col]) > 0):
                all_black = False
                break
        if (all_black == True):
            reduced_w = reduced_w - 1
    # bottom to top
    for row in range(h - 1, -1, -1):
        all_black = True
        for i in range(reduced_w):
            if (np.count_nonzero(img[row, i]) > 0):
                all_black = False
                break
        if (all_black == True):
            reduced_h = reduced_h - 1
    return img[:reduced_h, :reduced_w]


def linearBlending(imgs):
    img_left, img_right = imgs
    (hl, wl) = img_left.shape[:2]
    (hr, wr) = img_right.shape[:2]
    # mask是二维单通道，只用i,j访问，无第三维
    img_left_mask = np.zeros((hr, wr), dtype=np.uint8)
    img_right_mask = np.zeros((hr, wr), dtype=np.uint8)
    for i in range(hl):
        for j in range(wl):
            if np.count_nonzero(img_left[i, j]) > 0:
                img_left_mask[i, j] = 1
    for i in range(hr):
        for j in range(wr):
            if np.count_nonzero(img_right[i, j]) > 0:
                img_right_mask[i, j] = 1
    overlap_mask = np.zeros((hr, wr), dtype=np.uint8)
    for i in range(hr):
        for j in range(wr):
            if (np.count_nonzero(img_left_mask[i, j]) > 0 and np.count_nonzero(img_right_mask[i, j]) > 0):
                overlap_mask[i, j] = 1
    alpha_mask = np.zeros((hr, wr))
    for i in range(hr):
        minIdx = maxIdx = -1
        for j in range(wr):
            if (overlap_mask[i, j] == 1 and minIdx == -1):
                minIdx = j
            if (overlap_mask[i, j] == 1):
                maxIdx = j
        if (minIdx == maxIdx):
            continue
        decrease_step = 1 / (maxIdx - minIdx)
        for j in range(minIdx, maxIdx + 1):
            alpha_mask[i, j] = 1 - (decrease_step * (j - minIdx))
    linearBlending_img = np.copy(img_right)
    linearBlending_img[:hl, :wl] = np.copy(img_left)
    # 这里只用i,j，不会加第三维下标
    for i in range(hr):
        for j in range(wr):
            if (np.count_nonzero(overlap_mask[i, j]) > 0):
                linearBlending_img[i, j] = alpha_mask[i, j] * img_left[i, j] + (1 - alpha_mask[i, j]) * img_right[i, j]
    return linearBlending_img


def linearBlendingWithConstantWidth(imgs):
    img_left, img_right = imgs
    (hl, wl) = img_left.shape[:2]
    (hr, wr) = img_right.shape[:2]
    img_left_mask = np.zeros((hr, wr), dtype=np.uint8)
    img_right_mask = np.zeros((hr, wr), dtype=np.uint8)
    constant_width = 3
    for i in range(hl):
        for j in range(wl):
            if np.count_nonzero(img_left[i, j]) > 0:
                img_left_mask[i, j] = 1
    for i in range(hr):
        for j in range(wr):
            if np.count_nonzero(img_right[i, j]) > 0:
                img_right_mask[i, j] = 1
    overlap_mask = np.zeros((hr, wr), dtype=np.uint8)
    for i in range(hr):
        for j in range(wr):
            if (np.count_nonzero(img_left_mask[i, j]) > 0 and np.count_nonzero(img_right_mask[i, j]) > 0):
                overlap_mask[i, j] = 1
    alpha_mask = np.zeros((hr, wr))
    for i in range(hr):
        minIdx = maxIdx = -1
        for j in range(wr):
            if (overlap_mask[i, j] == 1 and minIdx == -1):
                minIdx = j
            if (overlap_mask[i, j] == 1):
                maxIdx = j
        if (minIdx == maxIdx):
            continue
        decrease_step = 1 / (maxIdx - minIdx)
        middleIdx = int((maxIdx + minIdx) / 2)
        for j in range(minIdx, middleIdx + 1):
            if (j >= middleIdx - constant_width):
                alpha_mask[i, j] = 1 - (decrease_step * (j - minIdx))
            else:
                alpha_mask[i, j] = 1
        for j in range(middleIdx + 1, maxIdx + 1):
            if (j <= middleIdx + constant_width):
                alpha_mask[i, j] = 1 - (decrease_step * (j - minIdx))
            else:
                alpha_mask[i, j] = 0
    linearBlendingWithConstantWidth_img = np.copy(img_right)
    linearBlendingWithConstantWidth_img[:hl, :wl] = np.copy(img_left)
    for i in range(hr):
        for j in range(wr):
            if (np.count_nonzero(overlap_mask[i, j]) > 0):
                linearBlendingWithConstantWidth_img[i, j] = alpha_mask[i, j] * img_left[i, j] + (1 - alpha_mask[i, j]) * img_right[i, j]
    return linearBlendingWithConstantWidth_img
# ========== 新增：GUI图形界面 ==========
class ImageStitchGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("图像拼接工具（SIFT+RANSAC）")
        self.root.geometry("520x220")
        self.root.option_add("*Font", "SimHei 10")  # 解决中文乱码
        self.img_paths = []

        # 界面组件
        tk.Label(root, text="全景图像拼接工具", font=("SimHei", 14)).pack(pady=12)
        self.tip_label = tk.Label(root, text="未选择任何图片", fg="#666666")
        self.tip_label.pack()

        btn_frame = tk.Frame(root)
        btn_frame.pack(pady=18)
        tk.Button(btn_frame, text="1. 选择多张本地图片", width=16, height=2,
                  command=self.select_images).grid(row=0, column=0, padx=10)
        tk.Button(btn_frame, text="2. 开始拼接", width=16, height=2,
                  bg="#4499dd", fg="white", command=self.run_stitch).grid(row=0, column=1, padx=10)

    def select_images(self):
        # 弹出文件选择框，按住Ctrl可多选
        paths = filedialog.askopenfilenames(
            title="选择拼接图片（按从左到右拍摄顺序选中）",
            filetypes=[("图片文件", "*.jpg;*.jpeg;*.png;*.JPG"), ("全部文件", "*.*")]
        )
        if not paths:
            return
        self.img_paths = list(paths)
        self.tip_label.config(text=f"已选择 {len(self.img_paths)} 张图片")

    def run_stitch(self):
        if len(self.img_paths) < 2:
            messagebox.showerror("提示", "请至少选择2张图片！")
            return
        img_list = []
        try:
            max_long_edge = 1200
            for path in self.img_paths:
                img = cv2.imdecode(np.fromfile(path, dtype=np.uint8), cv2.IMREAD_COLOR)
                if img is None:
                    raise Exception(f"图片读取失败：{path}")
                # 校验原图不是纯黑
                gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
                if np.count_nonzero(gray > 10) < 500:
                    raise Exception(f"图片{path}有效像素过少，无法拼接")
                # 统一缩放，防止尺寸过大黑屏
                h, w = img.shape[:2]
                if max(h, w) > max_long_edge:
                    scale = max_long_edge / max(h, w)
                    new_w, new_h = int(w * scale), int(h * scale)
                    img = cv2.resize(img, (new_w, new_h), interpolation=cv2.INTER_AREA)
                img_list.append(img)

            # 平面扫描模式，适合室内平移照片
            stitcher = cv2.Stitcher.create(cv2.Stitcher_SCANS)
            stitcher.setPanoConfidenceThresh(0.1)
            status, pano = stitcher.stitch(img_list)

            if status != cv2.Stitcher_OK:
                messagebox.showerror("拼接失败", "图片重叠不足/角度偏差过大，无法生成全景")
                return

            # 【修复下标错误的自动裁剪代码】
            gray = cv2.cvtColor(pano, cv2.COLOR_BGR2GRAY)
            pts = cv2.findNonZero(gray)
            x, y, w, h = cv2.boundingRect(pts)
            pano = pano[y:y + h, x:x + w]

            output_name = "全景拼接结果.jpg"
            cv2.imwrite(output_name, pano)
            cv2.imshow("全景拼接结果", pano)
            cv2.waitKey(0)
            cv2.destroyAllWindows()
        except Exception as e:
            messagebox.showerror("读取/拼接异常", f"错误：{str(e)}")
            return

        # 仅保留安全无报错指标：有效画布占比、尺寸、图片数量
        metric_text = ""
        try:
            gray_pano = cv2.cvtColor(pano, cv2.COLOR_BGR2GRAY)
            valid_pixel = np.count_nonzero(gray_pano > 5)
            total_pixel = gray_pano.size
            valid_ratio = valid_pixel / total_pixel

            metric_text = (
                f"==== 基础拼接信息 ====\n"
                f"有效画布占比：{valid_ratio:.4f}\n\n"
                f"参与图片总数：{len(img_list)} 张\n"
                f"全景图尺寸：宽{pano.shape[1]} × 高{pano.shape[0]}"
            )
        except Exception as e:
            metric_text = f"指标计算出错：{str(e)}\n全景图片已正常保存"

        messagebox.showinfo("拼接完成", f"{metric_text}\n文件保存：{output_name}")
# ========== 程序入口：启动GUI窗口 ==========
if __name__ == "__main__":
    root = tk.Tk()
    app = ImageStitchGUI(root)
    root.mainloop()