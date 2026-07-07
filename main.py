import numpy as np
import cv2
import random

def matchKeyPoint(kps_l, kps_r, features_l, features_r, ratio):
    # 存储最近点位置、最近点距离、次近点位置、次近点距离
    Match_idxAndDist = []
    for i in range(len(features_l)):
        # 从 features_r 中找到与 i 距离最近的2个点
        min_IdxDis = [-1, np.inf]    # 距离最近的点
        secMin_IdxDis = [-1, np.inf]# 距离第二近的点
        for j in range(len(features_r)):
            dist = np.linalg.norm(features_l[i] - features_r[j])
            if (min_IdxDis[1] > dist):
                secMin_IdxDis = np.copy(min_IdxDis)
                min_IdxDis = [j, dist]
            elif (secMin_IdxDis[1] > dist and secMin_IdxDis[1] != min_IdxDis[1]):
                secMin_IdxDis = [j, dist]
        Match_idxAndDist.append([min_IdxDis[0], min_IdxDis[1], secMin_IdxDis[0], secMin_IdxDis[1]])

    goodMatches = []
    # 如果i与最近的2个点的距离差较大，那么就不是好的匹配点
    # 即 |fi-fj| / |fi-fj'| > ratio 则取消匹配点
    for i in range(len(Match_idxAndDist)):
        if (Match_idxAndDist[i][1] <= Match_idxAndDist[i][3] * ratio):
            goodMatches.append((i, Match_idxAndDist[i][0]))

    # 获取匹配较好的点对
    goodMatches_pos = []
    for (idx, correspondingIdx) in goodMatches:
        psA = (int(kps_l[idx].pt[0]), int(kps_l[idx].pt[1]))
        psB = (int(kps_r[correspondingIdx].pt[0]), int(kps_r[correspondingIdx].pt[1]))
        goodMatches_pos.append([psA, psB])

    return goodMatches_pos

def detectAndDescribe(img):
    # 构建 SIFT 特征检测器
    sift = cv2.SIFT_create()
    # 进行特征提取
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

    if (blending_mode == "noBlending"):
        stitch_img[:hl, :wl] = img_left

    # 从right img转换到left img
    inv_H = np.linalg.inv(HomoMat)
    for i in range(stitch_img.shape[0]):
        for j in range(stitch_img.shape[1]):
            # 计算左图i,j 对应右图哪个坐标点
            coor = np.array([j, i, 1])
            img_right_coor = inv_H @ coor  # the coordination of right image
            img_right_coor /= img_right_coor[2]

            # y为宽 x为高
            y, x = int(round(img_right_coor[0])), int(round(img_right_coor[1]))
            # 超出范围 不处理
            if (x < 0 or x >= hr or y < 0 or y >= wr):
                continue

            stitch_img[i, j] = img_right[x, y]

    if (blending_mode == "linearBlending"):
        stitch_img = linearBlending([img_left, stitch_img])
    elif (blending_mode == "linearBlendingWithConstantWidth"):
        stitch_img = linearBlendingWithConstantWidth([img_left, stitch_img])

    # 去除黑边
    stitch_img = removeBlackBorder(stitch_img)
    return stitch_img


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
    img_left_mask = np.zeros((hr, wr), dtype=np.uint8)
    img_right_mask = np.zeros((hr, wr), dtype=np.uint8)
    # 找到img_left 和 img_right 的mask部分 即非0部分
    for i in range(hl):
        for j in range(wl):
            if np.count_nonzero(img_left[i, j]) > 0:
                img_left_mask[i, j] = 1
    for i in range(hr):
        for j in range(wr):
            if np.count_nonzero(img_right[i, j]) > 0:
                img_right_mask[i, j] = 1
    # 找到两图重合的部分
    overlap_mask = np.zeros((hr, wr), dtype=np.uint8)
    for i in range(hr):
        for j in range(wr):
            if (np.count_nonzero(img_left_mask[i, j]) > 0 and np.count_nonzero(img_right_mask[i, j]) > 0):
                overlap_mask[i, j] = 1

    alpha_mask = np.zeros((hr, wr))  # alpha value depend on left image,
    for i in range(hr):
        minIdx = maxIdx = -1
        for j in range(wr):
            if (overlap_mask[i, j] == 1 and minIdx == -1):
                minIdx = j
            if (overlap_mask[i, j] == 1):
                maxIdx = j

        if (minIdx == maxIdx):  # 融合区域过小
            continue

        decrease_step = 1 / (maxIdx - minIdx)
        for j in range(minIdx, maxIdx + 1):
            alpha_mask[i, j] = 1 - (decrease_step * (j - minIdx))

    linearBlending_img = np.copy(img_right)
    linearBlending_img[:hl, :wl] = np.copy(img_left)
    # 线性混合
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
    constant_width = 3  # constant width

    # 找到img_left 和 img_right 的mask部分 即非0部分
    for i in range(hl):
        for j in range(wl):
            if np.count_nonzero(img_left[i, j]) > 0:
                img_left_mask[i, j] = 1

    for i in range(hr):
        for j in range(wr):
            if np.count_nonzero(img_right[i, j]) > 0:
                img_right_mask[i, j] = 1

    # 找到重叠部分
    overlap_mask = np.zeros((hr, wr), dtype=np.uint8)
    for i in range(hr):
        for j in range(wr):
            if (np.count_nonzero(img_left_mask[i, j]) > 0 and np.count_nonzero(img_right_mask[i, j]) > 0):
                overlap_mask[i, j] = 1
    # compute the alpha mask to linear blending the overlap region
    alpha_mask = np.zeros((hr, wr))  # alpha value depend on left image
    for i in range(hr):
        minIdx = maxIdx = -1
        for j in range(wr):
            if (overlap_mask[i, j] == 1 and minIdx == -1):
                minIdx = j
            if (overlap_mask[i, j] == 1):
                maxIdx = j

        if (minIdx == maxIdx):  # represent this row's pixels are all zero, or only one pixel not zero
            continue

        decrease_step = 1 / (maxIdx - minIdx)
        # 找到重叠部分的中心位置
        middleIdx = int((maxIdx + minIdx) / 2)

        # left
        for j in range(minIdx, middleIdx + 1):
            if (j >= middleIdx - constant_width):
                alpha_mask[i, j] = 1 - (decrease_step * (j - minIdx))
            else:
                alpha_mask[i, j] = 1

        # right
        for j in range(middleIdx + 1, maxIdx + 1):
            if (j <= middleIdx + constant_width):
                alpha_mask[i, j] = 1 - (decrease_step * (j - minIdx))
            else:
                alpha_mask[i, j] = 0

    linearBlendingWithConstantWidth_img = np.copy(img_right)
    linearBlendingWithConstantWidth_img[:hl, :wl] = np.copy(img_left)
    # linear blending with constant width
    for i in range(hr):
        for j in range(wr):
            if (np.count_nonzero(overlap_mask[i, j]) > 0):
                linearBlendingWithConstantWidth_img[i, j] = alpha_mask[i, j] * img_left[i, j] + (1 - alpha_mask[i, j]) * \
                                                            img_right[i, j]

    return linearBlendingWithConstantWidth_img


if __name__ == "__main__":
     # 读取图像
     img1 = cv2.imread('hill11.JPG')
     img2 = cv2.imread('hill12.JPG')
     # 获取特征点
     kps1, features1 = detectAndDescribe(img1)
     kps2, features2 = detectAndDescribe(img2)
     # vis = drawpos(img1,img2,kps1,kps2)
     # cv2.imwrite("keypoints.jpg",vis)
     # 计算匹配点
     goodMatches_pos = matchKeyPoint(kps1,kps2,features1,features2,ratio=0.75)
     # 绘制匹配点
     vis = drawMatches(img1,img2,goodMatches_pos)
     # cv2.imshow("Matches_pos",vis)
     cv2.imwrite("Matches_pos.jpg",vis)
     # 计算H矩阵
     H, save_Inlier_pos = fitHomoMat(goodMatches_pos,nIter=2000,th=5.0)
     print(H)
     print(len(save_Inlier_pos))
     # 绘制 Inlier 匹配点
     vis2 = drawMatches(img1,img2,save_Inlier_pos)
     cv2.imshow("Matches_pos2",vis2)
     cv2.imwrite("Matches_pos2.jpg",vis2)
     # 进行图像拼接
     # "linearBlending"  重叠部分线性过渡
     # "linearBlendingWithConstantWidth" 重叠部分只对中心固定宽度部分进行过渡
     stitch_img = warp(img1, img2, H, blending_mode="linearBlending")
     cv2.imshow("stitch_img",stitch_img)
     cv2.imwrite("stitch_img_1.jpg",stitch_img)
     cv2.waitKey(0)
     cv2.destroyAllWindows()