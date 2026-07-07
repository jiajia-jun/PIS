# PIS-web

全景图像拼接系统 Web 后端，基于 Go + Gin 构建。用户上传多张有重叠区域的图片，后端异步拼接并返回全景图，支持历史记录查看与数据分析展示。

## 技术栈

| 组件 | 选型 |
|---|---|
| 语言 | Go 1.25 |
| Web 框架 | Gin |
| ORM | GORM |
| 数据库 | MySQL 8.0 |
| 日志 | go.uber.org/zap |
| 配置 | gopkg.in/yaml.v3 |
| 图片处理 | github.com/disintegration/imaging |

## 快速开始

### 1. 准备数据库

创建 MySQL 数据库（名称随意，如 `pis`）：

```sql
CREATE DATABASE pis CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
```

### 2. 设置环境变量

```bash
# Windows（系统环境变量）
DATABASE_PIS=root:你的密码@tcp(127.0.0.1:3306)/pis?charset=utf8mb4&parseTime=True

# Linux / macOS
export DATABASE_PIS='root:你的密码@tcp(127.0.0.1:3306)/pis?charset=utf8mb4&parseTime=True'
```

### 3. 修改配置

编辑 `config.yaml`，主要关注引擎类型：

```yaml
engine:
  stitch_type: mock      # mock → 无需 Python；python → 调用真实脚本
  analysis_type: mock    # 同上，可独立切换
server:
  port: 8080
```

### 4. 启动

```bash
go run .
```

启动后 GORM 自动建表，输出：

```
stitch engine: mock, analysis engine: mock-analysis
server starting on http://localhost:8080
```

## API 端点

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/upload` | 上传多张图片（multipart, field=images），返回 `task_id` |
| GET | `/api/task/:task_id` | 轮询任务状态，完成时附带 `result_url`、`thumbnail_url`、`analysis_urls` |
| GET | `/api/history?page=1&size=10` | 分页查询历史记录，按时间倒序 |
| GET | `/api/result/:task_id` | 返回拼接结果原图（JPEG 二进制流） |
| GET | `/api/thumbnail/:task_id` | 返回缩略图（800px JPEG，内存生成不落盘） |
| GET | `/api/analysis/:task_id/:filename` | 返回分析图表（PNG 二进制流） |

### 测试示例

```bash
# 上传
curl -X POST http://localhost:8080/api/upload \
  -F "images=@img1.jpg" \
  -F "images=@img2.jpg"

# 轮询状态
curl http://localhost:8080/api/task/{task_id}

# 历史记录
curl http://localhost:8080/api/history?page=1&size=10

# 获取缩略图
curl http://localhost:8080/api/thumbnail/{task_id} -o thumb.jpg
```

## 统一响应格式

```json
{
    "code": 0,
    "message": "ok",
    "data": {}
}
```

## 项目结构

```
PIS-web/
├── main.go                     # 入口：配置加载 → DB → 引擎 → Worker Pool → 路由 → 启动
├── config.yaml                 # 配置文件
├── internal/
│   ├── config/config.go        # YAML 配置 + 环境变量读取
│   ├── model/task.go           # GORM Task 模型（pending/processing/completed/failed）
│   ├── database/db.go          # MySQL 连接 + AutoMigrate
│   ├── engine/                 # 算法引擎（策略模式）
│   │   ├── engine.go           # AlgorithmEngine 接口
│   │   ├── mock.go             # Mock 拼接引擎
│   │   ├── python.go           # Python 拼接引擎
│   │   ├── cpp.go              # C++ 引擎（占位）
│   │   ├── analysis_mock.go    # Mock 分析引擎
│   │   └── analysis_python.go  # Python 分析引擎
│   ├── worker/pool.go          # 固定大小 Worker Pool（先拼接后分析）
│   ├── service/task_service.go # 业务逻辑：CRUD + 结果处理 + 日志 + 清理
│   ├── handler/                # Gin HTTP 处理器
│   │   ├── upload.go
│   │   ├── task.go
│   │   ├── history.go
│   │   ├── result.go
│   │   ├── thumbnail.go
│   │   └── analysis.go
│   ├── middleware/             # 中间件（BodyLimit 200MB + 请求日志）
│   └── tool/thumbnail.go       # 内存缩放工具
├── docs/                       # 设计文档与接口文档
├── scripts/                    # Python 脚本占位（stitch.py / analysis.py）
├── store/
│   ├── uploads/                # 上传图片 + 拼接结果
│   └── analysis/               # 分析图表 PNG
└── logs/                       # access.log + task.log
```

## 引擎切换

通过 `config.yaml` 控制，**拼接和分析可独立切换**：

| engine.stitch_type | 行为 |
|---|---|
| `mock` | MockEngine：复制第一张图为结果，sleep 1s，返回模拟数据 |
| `python` | PythonEngine：`os/exec` 调用 `scripts/stitch.py` |
| `cpp` | CppEngine：占位，待开发 |

| engine.analysis_type | 行为 |
|---|---|
| `mock` | MockAnalysisEngine：生成占位 PNG 图表 |
| `python` | PythonAnalysisEngine：`os/exec` 调用 `scripts/analysis.py` |

## Python 脚本接口

Go 与 Python 通过"文件系统 + JSON"通信，详见 `docs/` 目录下的接口文档。

**stitch.py**：读 `{任务目录}/input/`，写 `{任务目录}/result/result.jpg` + `meta.json`

**analysis.py**：读 `{任务目录}/input/` + `result.jpg`，写 `{分析输出目录}/*.png`

## 关键约束

| 约束 | 值 |
|---|---|
| 上传大小限制 | 200 MB |
| Worker 数量 | 20 goroutines |
| Python 超时 | 30 秒 |
| 上传文件自动清理 | 任务完成后 10 分钟（仅清理 input，result 保留） |
| 拼接失败 | 不调用分析脚本，记录错误信息 |
| 分析失败 | 不影响拼接结果，仅记日志 |

## 日志

| 文件 | 写入者 | 内容 |
|---|---|---|
| `logs/access.log` | middleware | HTTP 请求：method、path、状态码、耗时 |
| `logs/task.log` | service | 任务处理结果：status、cost_ms、keypoints、error |
