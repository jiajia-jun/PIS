# PIS-web — 全景图像拼接系统

基于 B/S 架构的全景图像拼接 Web 应用。用户通过浏览器上传多张有重叠区域的图片，后端异步调用 OpenCV 算法完成拼接与质量评估，前端实时展示结果。

---

## 1. 核心算法

### 1.1 算法总览

本项目实现了一条完整的图像拼接管线，核心流程为：

```
输入图像 → SIFT 特征提取 → BFMatcher + KNN 匹配 → Lowe's ratio test 筛选
→ RANSAC 单应矩阵估计 → OpenCV Stitcher（球面/平面回退）→ 黑边裁剪 → 全景图
```

### 1.2 SIFT 特征提取

**原理**：SIFT（Scale-Invariant Feature Transform）由 David Lowe 于 1999 年提出，核心思想是在尺度空间中寻找对缩放、旋转、光照均不敏感的稳定特征点。算法分四步：

1. **尺度空间极值检测**：用不同 σ 值的高斯差分（DoG）金字塔检测候选点
2. **关键点精确定位**：对 DoG 响应做 3D 二次拟合，剔除低对比度和边缘响应点
3. **方向分配**：基于局部梯度直方图为每个关键点分配主方向，实现旋转不变性
4. **特征描述子**：在关键点周围 16×16 邻域计算 128 维梯度方向直方图向量

**为什么适合本任务**：全景拼接的核心难点在于不同图片可能存在缩放差异（拍摄距离不同）、旋转差异（手持角度不同）和光照差异（曝光参数不同）。SIFT 是少数同时对缩放、旋转、光照和一定视角变化都具有不变性的特征检测算法——这恰好覆盖了用户随意拍摄时最常见的几种变异。相比深度学习方案（SuperPoint 等），SIFT 无需 GPU、无需预训练模型、在 CPU 上即可在 1-2 秒内完成 2000px 图像的检测，完美契合 "Web 服务端异步处理" 的场景约束。

**回退策略**：在 `opencv-python-headless`（不含 non-free 模块）环境下，SIFT 不可用，自动回退为 **ORB**（Oriented FAST + Rotated BRIEF）。ORB 检测速度比 SIFT 快一个数量级但精度略低，适合对匹配质量要求不极端的场景。

### 1.3 特征匹配与 Lowe's Ratio Test

**原理**：对相邻图像对的所有 SIFT 描述子，使用 **BFMatcher**（暴力匹配器，L2 距离）进行两两匹配。对每个查询特征点，保留最近邻和次近邻两个候选（K=2 KNN），然后应用 **Lowe's ratio test**：

> 若 d₁ / d₂ < 0.7，则保留最佳匹配；否则判定为假匹配并舍弃。

其中 d₁ 是最近邻距离，d₂ 是次近邻距离。直觉：正确匹配的描述子应该 "显著优于" 第二候选，而错误匹配的最近邻和次近邻距离相近（都是随机噪声）。

**为什么适合本任务**：用户上传的图片可能存在重复纹理（砖墙、草地、天空等），纯暴力匹配会产生大量假匹配。Lowe's ratio test 以极小的计算代价（只需多保存一个次近邻）就能过滤掉大部分歧义匹配，是 SIFT 论文作者本人推荐的标配筛选策略。阈值 0.7 在准确率和召回率之间取得平衡——已在本项目数百张室内外场景图片上验证有效。

### 1.4 RANSAC 单应矩阵估计

**原理**：RANSAC（Random Sample Consensus）由 Fischler 和 Bolles 于 1981 年提出，用于从含大量离群点（错误匹配）的数据中鲁棒估计数学模型。在本任务中，目标是从匹配点对中估计 3×3 单应矩阵 **H**（描述两幅图像间的透视变换关系）：

1. 从匹配点对中**随机取 4 对**（单应矩阵的最小解算需求）
2. 用 DLT（直接线性变换）计算候选 **H**
3. 检查其余点对是否满足投影一致性：‖x' − Hx‖ < ε（ε=5 像素），统计内点数
4. 重复 N 次，**保留内点数最多的 H**
5. 用该 H 的所有内点通过最小二乘法精化得到最终 H

**为什么适合本任务**：经过 ratio test 后的匹配集中仍可能混入 10%-30% 的误匹配（尤其在纹理重复的场景）。传统最小二乘法会对所有点（含误匹配）一视同仁，结果被离群点严重拖偏。RANSAC 的 "随机采样—内点投票" 策略天然免疫离群点——只要 4 个正确的匹配点被采样到，就能算出正确的 H，而错误的 H 因得不到足够内点投票被自动淘汰。这一特性在图像拼接场景中至关重要。

### 1.5 OpenCV Stitcher 管线与球面/平面回退

**原理**：上述 SIFT → Ratio Test → RANSAC 流程以及后续的相机参数调整、曝光补偿、接缝查找和多频段融合，在 OpenCV 中被封装为 `cv2.Stitcher` 类。本项目在此基础上实现了**双模式回退**：

1. **优先球面投影**（`Stitcher_PANORAMA`）：假设相机绕光心旋转拍摄，适用于大视角全景
2. **回退平面投影**（`Stitcher_SCANS`）：假设相机平移扫描拍摄，适用于平面文档/白板拼接

球面模式失败时自动回退平面模式，无需用户干预。

### 1.6 六维质量评估

拼接完成后，系统自动对结果进行量化评估，六个维度：

| 指标 | 含义 | 方向 | 计算方式 |
|------|------|------|---------|
| 内点率 | RANSAC 内点数 / 总匹配数 | 越高越好 | 反映特征匹配可靠性 |
| 重投影 RMSE | 源点经 H 投影到目标空间的均方根误差 | 越低越好 | 反映几何对齐精度 |
| 全景 SSIM | 全景图滑动窗口 1px 偏移 SSIM 均值 | 越高越好 | 反映全景图局部结构连续性 |
| 有效画布占比 | 全景图中非黑像素的比例 | 越高越好 | 反映画布利用效率 |
| 清晰度保持率 | 全景图与原图的 Laplacian 方差比 | 越高越好 | 反映拼接对细节的保留程度 |
| 综合得分 | 六维归一化评分均值 | 越高越好 | 单一数字的总体质量评价 |

---

## 2. 运行环境

### 2.1 硬件要求

| 项目 | 最低配置 | 推荐配置 |
|------|---------|---------|
| CPU | 4 核 | 8 核以上（Worker Pool 20 并发时） |
| 内存 | 4 GB | 8 GB 以上（20 并发含 Python 子进程时峰值约 800 MB） |
| 磁盘 | 1 GB 可用空间 | 10 GB（拼接结果和分析图表随任务累积） |
| GPU | 不需要 | —（全部 CPU 计算） |
| 网络 | 局域网可达 | 公网 IP（对外服务时） |

### 2.2 操作系统

| 系统 | 支持状态 | 备注 |
|------|---------|------|
| Windows 10/11 | ✅ 完全支持 | 开发与生产均验证 |
| Linux (Ubuntu 20.04+) | ✅ 完全支持 | 推荐生产部署 |
| macOS | ✅ 理论支持 | 未专门测试，Go 交叉编译即可 |

### 2.3 Go 环境

| 依赖 | 版本 | 用途 |
|------|------|------|
| Go | **1.25.5** | 编译后端 |
| Gin | v1.12.0 | HTTP 路由与中间件 |
| GORM | v1.31.2 | ORM |
| MySQL 驱动 | v1.6.0 | GORM MySQL 后端 |
| UUID | v1.6.0 | 任务 ID 生成 |
| Zap | v1.28.0 | 结构化日志 |
| imaging | v1.6.2 | Lanczos 图片缩放 |
| yaml.v3 | v3.0.1 | 配置解析 |

### 2.4 MySQL

- **版本**：MySQL 8.0+（使用 utf8mb4 字符集）
- **连接串**：通过环境变量 `DATABASE_PIS` 注入，格式：

```
root:密码@tcp(地址:3306)/数据库名?charset=utf8mb4&parseTime=True
```

### 2.5 Python 环境（仅 `stitch_type=python` 或 `analysis_type=python` 时需要）

| 依赖 | 版本要求 | 用途 |
|------|---------|------|
| Python | **3.8+**（推荐 3.10+） | 脚本解释器 |
| OpenCV | **4.5+**（推荐 4.8+，含 contrib） | SIFT 特征检测 + Stitcher 拼接管线 |
| NumPy | 1.21+ | 矩阵运算、npy 文件读写 |
| Matplotlib | 3.5+ | 质量评估图表生成 |

**安装 Python 依赖：**

```bash
pip install opencv-contrib-python numpy matplotlib
```

> ⚠️ 注意：必须安装 `opencv-contrib-python` 而非 `opencv-python-headless`，后者不含 SIFT（non-free 模块）。若只能用 headless 版本，SIFT 会自动回退为 ORB，拼接功能仍可用但精度略降。

### 2.6 Node.js（仅前端开发时需要）

| 依赖 | 版本 | 用途 |
|------|------|------|
| Node.js | 18+ / 20+ | 包管理与构建 |
| npm | 9+ | 安装前端依赖 |

### 2.7 前端依赖（package.json）

| 依赖 | 版本 | 用途 |
|------|------|------|
| Vue | ^3.5.39 | 前端框架（Composition API） |
| Element Plus | ^2.14.2 | UI 组件库 |
| Vue Router | ^4.6.4 | SPA 路由 |
| Vue I18n | ^9.14.4 | 中/英双语国际化 |
| Vite | ^8.1.1 | 构建工具 |
| @vitejs/plugin-vue | ^6.0.7 | Vite Vue 插件 |

---

## 3. 安装与启动

### 3.1 后端

```bash
# 1. 克隆项目
cd PIS-web

# 2. 安装 Go 依赖
go mod tidy

# 3. 创建数据库（MySQL 命令行或客户端中执行）
# CREATE DATABASE pis CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

# 4. 设置环境变量
# Windows: 系统环境变量中添加 DATABASE_PIS
# Linux/macOS:
export DATABASE_PIS='root:密码@tcp(127.0.0.1:3306)/pis?charset=utf8mb4&parseTime=True'

# 5. 编辑 config.yaml（可选，默认 mock 模式直接可用）

# 6. 启动
go run .
```

启动成功输出：
```
拼接引擎: mock, 分析引擎: mock-analysis
服务启动: http://0.0.0.0:8080
```

GORM 会在首次启动时自动创建 `tasks` 表，无需手动执行 SQL。

> 💡 **没有测试图片？** 上传页面提供「使用示例图片」按钮，后端会自动从 `store/samples/input/` 复制预置图片创建任务，启动后即可体验完整流程。Mock 模式下也能直接看到拼接结果，无需 Python 环境。

### 3.2 前端（开发模式）

```bash
cd frontend
npm install
npm run dev
```

Vite 会自动从 `../config.yaml` 读取后端 host:port 并配置 API 代理。

### 3.3 生产部署

```bash
# 1. 构建前端静态文件
cd frontend
npm run build          # 产物输出到 dist/

# 2. 编译 Go 后端
cd ..
go build -o pis-web .

# 3. 运行（单文件部署，Go 同时服务 API + 前端静态文件）
./pis-web
```

生产模式下只需一个 `pis-web` 可执行文件 + `config.yaml` + `frontend/dist/` + `scripts/`（如果用 python 引擎）。

---

## 4. 配置参数说明

`config.yaml` 完整参数：

```yaml
engine:
  stitch_type: mock           # 拼接引擎: "mock" | "python" | "cpp"
  analysis_type: mock         # 分析引擎: "mock" | "python"
  python_path: "python3"      # Python 解释器路径（可绝对路径）
  stitch_script_path: "./scripts/stitch.py"       # 拼接脚本路径
  analysis_script_path: "./scripts/eval_pipeline.py"   # 分析脚本路径
  cpp_binary: ""              # C++ 引擎可执行文件（预留）

server:
  host: ""                    # 监听地址，空=所有网卡(0.0.0.0)，可设 127.0.0.1 仅本地
  port: 8080                  # 监听端口
  upload_max_size_mb: 200     # 上传总大小限制(MB)，超限返回 413

worker:
  pool_size: 20               # Worker 协程数（最大并发 Python 进程数）
  timeout_seconds: 30         # 普通模式超时秒数（超能模式固定 300 秒）

store:
  upload_dir: ./store/uploads    # 上传文件和拼接结果存储目录
  analysis_dir: ./store/analysis # 分析图表和评估数据存储目录
```

### 引擎模式说明

| 模式 | stitch_type | analysis_type | 需要 Python | 适用场景 |
|------|------------|---------------|-------------|---------|
| 纯 Mock | `mock` | `mock` | ❌ | 前端开发、集成测试、无 Python 环境 |
| 混合 | `python` | `mock` | ✅ 仅拼接 | 测试拼接、跳过分析 |
| 混合 | `mock` | `python` | ✅ 仅分析 | 调试分析（需已有 result.jpg） |
| 纯生产 | `python` | `python` | ✅ | 正式环境 |

---

## 5. 运行命令与参数

### 5.1 Go 后端

```bash
# 开发运行
go run .                           # 无参数，自动读当前目录 config.yaml

# 编译
go build -o pis-web .              # Windows: -o pis-web.exe

# 交叉编译
GOOS=linux GOARCH=amd64 go build -o pis-web .

# 运行测试
go test ./internal/... -v          # 单元测试（待补充）
go test ./webTest/ -v              # 集成测试（需 DATABASE_PIS 环境变量）
go test ./webTest/ -v -run TestUploadAndTaskFlow  # 单测某个用例
```

### 5.2 Python 拼接脚本 `stitch.py`

```bash
# Go 后端自动调用，也可手动执行用于调试
python3 scripts/stitch.py ./store/uploads/{task_id}/

# 参数: 1 个 — 任务目录路径
#   输入: {任务目录}/input/*.jpg
#   输出: {任务目录}/result/result.jpg + meta.json + H_list.npy + inliers_list.pkl + result_info.json
```

### 5.3 Python 分析脚本 `eval_pipeline.py`

```bash
# Go 后端自动调用，也可手动执行用于调试
python3 scripts/eval_pipeline.py ./store/uploads/{task_id}/ ./store/analysis/{task_id}/

# 参数: 2 个 — 任务目录 + 分析输出目录
#   输入: {任务目录}/result/ 下的拼接产物
#   输出: {分析输出目录}/*.png + eval_result.json + full_metrics.json
```

### 5.4 前端

```bash
cd frontend

npm run dev         # 启动开发服务器（带 HMR 热更新）
npm run build       # 构建生产版本到 dist/
npm run preview     # 预览生产构建

# Vite 配置在 vite.config.js 中，自动从 ../config.yaml 读取后端地址
```

### 5.5 API 测试

```bash
# 上传 2 张图片
curl -X POST http://localhost:8080/api/upload \
  -F "images=@left.jpg" \
  -F "images=@right.jpg"
# → {"code":0,"message":"ok","data":{"task_id":"uuid-xxx"}}

# 轮询任务状态（前端每 1 秒调用一次）
curl http://localhost:8080/api/task/uuid-xxx

# 获取拼接结果原图
curl http://localhost:8080/api/result/uuid-xxx -o panorama.jpg

# 获取缩略图（800px 宽）
curl http://localhost:8080/api/thumbnail/uuid-xxx -o thumb.jpg

# 获取分析图表
curl http://localhost:8080/api/analysis/uuid-xxx/quality_radar.png -o radar.png

# 获取评估数据
curl http://localhost:8080/api/analysis/uuid-xxx/eval_result.json

# 历史记录（分页）
curl "http://localhost:8080/api/history?page=1&size=10"

# 使用示例图片创建任务（普通模式）
curl -X POST "http://localhost:8080/api/upload/sample?mode=normal"

# 使用示例图片创建任务（超能模式）
curl -X POST "http://localhost:8080/api/upload/sample?mode=super"

# 获取原始上传图片
curl http://localhost:8080/api/input/uuid-xxx/img_001.jpg -o original.jpg

# 获取原始上传图片缩略图
curl http://localhost:8080/api/input-thumb/uuid-xxx/img_001.jpg -o input_thumb.jpg
```

---

## 6. 项目结构

```
PIS-web/
├── main.go                     # 入口（调用 app.New + Run）
├── config.yaml                 # 运行时配置
├── go.mod / go.sum             # Go 模块定义
│
├── internal/                   # Go 源码
│   ├── app/app.go              # 应用组装（依赖注入）
│   ├── config/config.go        # 配置加载（yaml + env）
│   ├── database/db.go          # MySQL 连接 + AutoMigrate
│   ├── model/task.go           # Task 实体 + 状态常量
│   ├── engine/                 # 算法引擎（策略模式）
│   │   ├── engine.go           # AlgorithmEngine 接口 + Meta 结构体
│   │   ├── mock.go             # Mock 拼接引擎
│   │   ├── python.go           # Python 拼接引擎
│   │   ├── cpp.go              # C++ 引擎（预留）
│   │   ├── analysis_mock.go    # Mock 分析引擎
│   │   └── analysis_python.go  # Python 分析引擎
│   ├── handler/                # HTTP 处理器（9 个端点）
│   │   ├── upload.go           # POST /api/upload + POST /api/upload/sample
│   │   ├── task.go             # GET  /api/task/:task_id
│   │   ├── history.go          # GET  /api/history
│   │   ├── result.go           # GET  /api/result/:task_id
│   │   ├── thumbnail.go        # GET  /api/thumbnail/:task_id
│   │   ├── analysis.go         # GET  /api/analysis/:task_id/:filename
│   │   ├── input.go            # GET  /api/input/:task_id/:filename
│   │   └── input_thumb.go      # GET  /api/input-thumb/:task_id/:filename
│   ├── service/                # 业务逻辑
│   │   ├── task_service.go     # CRUD + HandleResult + 任务日志
│   │   └── task_eviction.go    # 历史淘汰（最多 40 条）
│   ├── worker/                 # Worker Pool
│   │   ├── pool.go             # 任务调度 + processJob
│   │   └── thumbnail.go        # 缩略图预生成
│   ├── middleware/              # 中间件
│   │   ├── limit.go            # BodyLimit（200MB）
│   │   └── logger.go           # RequestLogger（访问日志）
│   └── tool/
│       └── thumbnail.go        # Lanczos 缩放到 800px JPEG
│
├── scripts/                    # Python 算法脚本
│   ├── stitch.py               # 全景拼接（SIFT + RANSAC + OpenCV Stitcher）
│   ├── eval_pipeline.py             # 分析适配器（桥接 + 图表生成）
│   └── eval_core.py                # 数据分析核心（分析组维护）
│
├── frontend/                   # Vue 3 前端
│   ├── index.html              # HTML 入口（含 Splash 入场动画）
│   ├── vite.config.js          # Vite 配置（自动读 config.yaml 代理）
│   └── src/
│       ├── main.js             # Vue 入口
│       ├── App.vue             # 根组件（导航栏 + 语言切换）
│       ├── i18n.js             # 国际化配置
│       ├── api/index.js        # API 封装
│       ├── composables/
│       │   └── useDarkMode.js      # 暗色模式状态管理
│       ├── router/index.js     # 路由（/, /task/:id, /history, /about）
│       ├── locales/{zh,en}.js  # 中/英语言包
│       └── views/
│           ├── UploadView.vue       # 上传页
│           ├── TaskDetailView.vue   # 详情页（结果 + 评估）
│           ├── HistoryView.vue      # 历史页
│           └── AboutView.vue        # 关于我们
│
├── store/                      # 运行时数据（gitignore）
├── logs/                       # access.log + task.log（gitignore）
├── docs/                       # 设计文档与接口规范
└── webTest/                    # 集成测试
```

---

## 7. API 端点

所有 API 统一响应格式：`{ "code": 0, "message": "ok", "data": {} }`

| 方法 | 路径 | 说明 |
|------|------|------|
| `POST` | `/api/upload` | 上传多张图片（multipart `images[]`），返回 `task_id` |
| `POST` | `/api/upload/sample?mode=normal\|super` | 使用预置示例图片创建任务 |
| `GET` | `/api/task/:task_id` | 轮询任务状态，completed 时附带 result/thumbnail/chart/table/input 各 URL |
| `GET` | `/api/history?page=1&size=10` | 分页查询历史记录，按时间倒序 |
| `GET` | `/api/result/:task_id` | 拼接结果原图（JPEG 二进制流） |
| `GET` | `/api/thumbnail/:task_id` | 结果缩略图（800px JPEG，Worker 预生成） |
| `GET` | `/api/input/:task_id/:filename` | 原始上传图片（含路径穿越防护） |
| `GET` | `/api/input-thumb/:task_id/:filename` | 原始上传图片缩略图（1 小时浏览器缓存） |
| `GET` | `/api/analysis/:task_id/:filename` | 分析图表（PNG）或数据（JSON） |

---

## 8. 关键设计

### 8.1 策略模式

算法引擎通过 `AlgorithmEngine` 接口抽象，工厂方法根据 `config.yaml` 动态选择实现。Handler 和 Worker 仅依赖接口，不感知底层引擎类型。拼接和分析引擎**可独立切换**——例如 `stitch=python, analysis=mock` 只测拼接不跑分析。

### 8.2 Worker Pool

固定 20 个 goroutine 从有缓冲 Channel（容量 20）取 Job。上传接口异步提交后立即返回 `task_id`，提交超时 3 秒（队列满返回 503 实现背压）。每个任务根据运行模式设置超时：普通模式 30 秒，超能模式 300 秒（同时用于拼接和分析）。分析或缩略图失败仅记 warning 日志，不影响拼接结果。

### 8.3 Go ↔ Python IPC

**文件系统 + JSON**，禁止 base64 编码和 stdin/stdout 传复杂数据：

- Go → Python：CLI 参数传目录路径
- Python → Go：`meta.json`（status/keypoints/cost_ms/error）+ `result.jpg`
- stitch.py → eval_pipeline.py：`H_list.npy` + `inliers_list.pkl` + `result_info.json`
- Python `finally` 块保证 `meta.json` 必定写入，Go 不依赖 Python 退出码

### 8.4 历史淘汰

最多保留 40 条 `completed`/`failed` 记录。每次 `HandleResult` 后即时触发检查，超出按时间升序删除——同时清理磁盘和数据库。

### 8.5 预置示例数据集

面向局域网部署场景，上传页面提供「使用示例图片」按钮，后端从 `store/samples/input/` 目录复制预置图片到新任务目录。该目录独立于 `store/uploads/`，不受历史淘汰影响，确保示例图片始终可用。

---

## 9. 约束

| 约束 | 值 |
|------|-----|
| 上传大小限制 | 200 MB |
| Worker 数量 | 20 goroutines |
| Python 超时 | 普通 30 秒 / 超能 300 秒 |
| 历史记录上限 | 40 条（超出自动淘汰） |
| 安全防护 | 路径穿越检查、环境变量存储敏感信息、UUID 任务隔离 |

---

## 10. 测试

```bash
# 集成测试（需 DATABASE_PIS 环境变量）
go test ./webTest/ -v

# 运行特定测试
go test ./webTest/ -v -run TestUploadAndTaskFlow   # 全链路
go test ./webTest/ -v -run TestHistory              # 历史分页
go test ./webTest/ -v -run TestConcurrentUpload     # 10 并发上传
```

---

## 11. 文档

| 文档 | 说明 |
|------|------|
| `docs/系统架构设计文档.md` | 系统架构、模块设计、数据流、设计模式 |
| `docs/后端设计文档.md` | 后端详细设计（模块、API、日志、配置） |
| `docs/算法组接口文档.md` | stitch.py 接口规范 |
| `docs/数据分析组接口文档.md` | eval_pipeline.py 接口规范 |
| `docs/数据交互规范.md` | 算法组 ↔ 分析组 ↔ 前端数据交换约定 |
| `docs/错误信息汇总.md` | 全系统错误信息索引与流转路径 |
| `docs/devlog/` | 开发日志（设计变更、差异分析报告等） |

## License

MIT
