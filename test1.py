# 只能放两张图且图片得在本地

import cv2
import numpy as np
from skimage.metrics import structural_similarity
import matplotlib.pyplot as plt

class PanoramaStitcher:
    def __init__(self):
        self.orb = cv2.ORB_create(nfeatures=5000, scaleFactor=1.2, patchSize=31)
        flann_index_params = dict(algorithm=6, table_number=6, key_size=12, multi_probe_level=1)
        flann_search_params = dict(checks=50)
        self.flann = cv2.FlannBasedMatcher(flann_index_params, flann_search_params)

    def detect_feature(self, img):
        kp, des = self.orb.detectAndCompute(img, None)
        return kp, des

    def match_feature(self, des1, des2):
        matches = self.flann.knnMatch(des1, des2, k=2)
        good = []
        for m, n in matches:
            if m.distance < 0.75 * n.distance:
                good.append(m)
        return good

    def calc_inlier_rate(self, mask):
        total = mask.shape[0]
        inlier_num = int(np.sum(mask))
        return round(inlier_num / total, 4) if total > 0 else 0.0

    def calc_reprojection_rmse(self, pts_src, pts_dst, H, mask):
        inlier_src = pts_src[mask.ravel() == 1]
        inlier_dst = pts_dst[mask.ravel() == 1]
        if len(inlier_src) == 0:
            return 999.9999
        pts_warp = cv2.perspectiveTransform(inlier_src.reshape(-1, 1, 2), H).reshape(-1, 2)
        err = np.sum((pts_warp - inlier_dst) ** 2, axis=1)
        rmse = np.sqrt(np.mean(err))
        return round(rmse, 4)

    def calc_overlap_ssim(self, full_canvas, warp_img2, overlap_mask):
        gray_canvas = cv2.cvtColor(full_canvas, cv2.COLOR_BGR2GRAY)
        gray_warp = cv2.cvtColor(warp_img2, cv2.COLOR_BGR2GRAY)
        g1 = gray_canvas[overlap_mask > 0]
        g2 = gray_warp[overlap_mask > 0]
        if len(g1) < 20:
            return 0.0
        ssim_val = structural_similarity(g1, g2, channel_axis=None)
        return round(float(ssim_val), 4)

    def calc_valid_canvas_ratio(self, full_pano):
        gray = cv2.cvtColor(full_pano, cv2.COLOR_BGR2GRAY)
        valid_pixel = np.sum(gray > 8)
        total_pixel = gray.shape[0] * gray.shape[1]
        ratio = valid_pixel / total_pixel
        return round(ratio, 4)

    def laplacian_var(self, gray_img):
        lap = cv2.Laplacian(gray_img, cv2.CV_64F)
        return np.var(lap)

    def calc_clarity_ratio(self, ori_img, pano_img):
        g_ori = cv2.cvtColor(ori_img, cv2.COLOR_BGR2GRAY)
        g_pano = cv2.cvtColor(pano_img, cv2.COLOR_BGR2GRAY)
        sharp_ori = self.laplacian_var(g_ori)
        sharp_pano = self.laplacian_var(g_pano)
        if sharp_ori < 1e-6:
            return 1.0
        ratio = sharp_pano / sharp_ori
        return round(ratio, 4)

    # 柱面投影矫正（解决画面角度扭曲）
    def cylindrical_warp(self, img, focal=None):
        h, w = img.shape[:2]
        if focal is None:
            focal = w * 1.2
        map_x = np.zeros((h, w), dtype=np.float32)
        map_y = np.zeros((h, w), dtype=np.float32)
        cx = w / 2.0
        cy = h / 2.0
        for y in range(h):
            for x in range(w):
                theta = (x - cx) / focal
                h_ = (y - cy) / focal
                x_cyl = focal * np.tan(theta) + cx
                y_cyl = focal * h_ / np.cos(theta) + cy
                map_x[y, x] = x_cyl
                map_y[y, x] = y_cyl
        warp_img = cv2.remap(img, map_x, map_y, cv2.INTER_LINEAR)
        return warp_img

    def stitch_two(self, img_left, img_right):
        # 柱面矫正
        imgL_cyl = self.cylindrical_warp(img_left)
        imgR_cyl = self.cylindrical_warp(img_right)
        h1, w1 = imgL_cyl.shape[:2]
        h2, w2 = imgR_cyl.shape[:2]

        # 特征匹配
        kp1, des1 = self.detect_feature(imgL_cyl)
        kp2, des2 = self.detect_feature(imgR_cyl)
        good_matches = self.match_feature(des1, des2)
        if len(good_matches) < 6:
            raise Exception("匹配特征点过少，无法拼接，请更换重叠更多的图片")

        pts1 = np.float32([kp1[m.queryIdx].pt for m in good_matches]).reshape(-1, 1, 2)
        pts2 = np.float32([kp2[m.trainIdx].pt for m in good_matches]).reshape(-1, 1, 2)

        H, mask = cv2.findHomography(pts2, pts1, cv2.RANSAC, 4.0)

        # 画布边界计算
        corners2 = np.array([[0, 0], [w2, 0], [w2, h2], [0, h2]], dtype=np.float32).reshape(-1, 1, 2)
        corners2_warp = cv2.perspectiveTransform(corners2, H).reshape(-1, 2)
        min_x = int(min(np.min(corners2_warp[:, 0]), 0))
        max_x = int(max(np.max(corners2_warp[:, 0]), w1))
        min_y = int(min(np.min(corners2_warp[:, 1]), 0))
        max_y = int(max(np.max(corners2_warp[:, 1]), h1))

        shift_mat = np.array([[1, 0, -min_x], [0, 1, -min_y], [0, 0, 1]])
        H_total = shift_mat @ H
        canvas_w = max_x - min_x
        canvas_h = max_y - min_y

        warp_right = cv2.warpPerspective(imgR_cyl, H_total, (canvas_w, canvas_h))
        panorama = np.zeros_like(warp_right)
        panorama[-min_y:h1 - min_y, -min_x:w1 - min_x] = imgL_cyl

        # 简单加权融合，无金字塔，不会尺寸报错
        mask_p1 = (panorama > 8).astype(np.float32)
        mask_p2 = (warp_right > 8).astype(np.float32)
        overlap_mask = np.logical_and(mask_p1[:, :, 0] > 0, mask_p2[:, :, 0] > 0)

        total_mask = mask_p1 + mask_p2
        total_mask[total_mask == 0] = 1.0
        panorama = (panorama * mask_p1 + warp_right * mask_p2) / total_mask
        panorama = panorama.astype(np.uint8)

        # 计算5项指标
        metrics = {}
        metrics["内点率"] = self.calc_inlier_rate(mask)
        metrics["重投影RMSE(px)"] = self.calc_reprojection_rmse(pts2, pts1, H, mask)
        metrics["重叠区SSIM"] = self.calc_overlap_ssim(panorama, warp_right, overlap_mask)
        metrics["有效画布占比"] = self.calc_valid_canvas_ratio(panorama)
        metrics["清晰度保持率"] = self.calc_clarity_ratio(img_left, panorama)

        return panorama, metrics

if __name__ == "__main__":
    stitcher = PanoramaStitcher()
    path_left = "1_0.jpg"
    path_right = "2_0.jpg"

    imgL = cv2.imread(path_left)
    imgR = cv2.imread(path_right)
    if imgL is None or imgR is None:
        print("图片读取失败！检查文件名与路径")
    else:
        pano_result, res_metrics = stitcher.stitch_two(imgL, imgR)
        print("======= 测试指标结果（匹配文档5项指标）=======")
        for k, v in res_metrics.items():
            print(f"{k}: {v}")

        cv2.imwrite("panorama_output.jpg", pano_result)
        cv2.imshow("全景拼接结果", pano_result)
        cv2.waitKey(0)
        cv2.destroyAllWindows()

        # 绘制PPT表格
        names = list(res_metrics.keys())
        values = list(res_metrics.values())
        fig, ax = plt.subplots(figsize=(11, 2))
        ax.axis("tight")
        ax.axis("off")
        table = ax.table(cellText=[values], colLabels=names, rowLabels=["auto_test"], loc="center", cellLoc="center")
        table.auto_set_font_size(False)
        table.set_fontsize(11)
        plt.show()