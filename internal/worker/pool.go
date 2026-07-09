package worker

import (
	"context"
	"fmt"
	"path/filepath"
	"time"

	"go.uber.org/zap"
	"pisweb/internal/engine"
	"pisweb/internal/model"
	"pisweb/internal/service"
)

// Job 任务工作单元
type Job struct {
	TaskID         string
	TaskDir        string // 任务根目录 = store/uploads/{task_id}
	StitchEngine   engine.AlgorithmEngine
	AnalysisEngine engine.AlgorithmEngine
	TimeoutSeconds int // 0 表示使用 Pool 默认超时
}

// Pool 固定大小的 Worker Pool
type Pool struct {
	jobs    chan Job
	service *service.TaskService
	size    int
	timeout time.Duration
	logger  *zap.Logger
}

// NewPool 创建 Worker Pool
func NewPool(size int, timeoutSec int, svc *service.TaskService, logger *zap.Logger) *Pool {
	return &Pool{
		jobs:    make(chan Job, size),
		service: svc,
		size:    size,
		timeout: time.Duration(timeoutSec) * time.Second,
		logger:  logger,
	}
}

// Submit 提交任务到队列，超时返回 error（防止请求阻塞）
func (p *Pool) Submit(job Job, timeout time.Duration) error {
	select {
	case p.jobs <- job:
		return nil
	case <-time.After(timeout):
		return fmt.Errorf("任务队列已满，请稍后重试")

	}
}

// Start 启动所有 Worker
func (p *Pool) Start(ctx context.Context) {
	for i := 0; i < p.size; i++ {
		go p.worker(ctx)
	}
}

func (p *Pool) worker(ctx context.Context) {
	for {
		select {
		case job := <-p.jobs:
			p.processJob(job)
		case <-ctx.Done():
			return
		}
	}
}

// processJob 处理单个任务：先拼接，再分析
func (p *Pool) processJob(job Job) {
	// 更新状态为 processing
	task, err := p.service.GetTask(job.TaskID)
	if err != nil {
		return
	}
	task.Status = model.StatusProcessing
	p.service.UpdateTask(task)

	// 第一步：执行拼接
	timeout := p.timeout
	if job.TimeoutSeconds > 0 {
		timeout = time.Duration(job.TimeoutSeconds) * time.Second
	}
	p.logger.Info("start stitching",
		zap.String("task_id", job.TaskID),
		zap.Duration("timeout", timeout),
	)
	stitchCtx, stitchCancel := context.WithTimeout(context.Background(), timeout)
	meta, stitchErr := job.StitchEngine.Run(stitchCtx, job.TaskDir)
	stitchCancel()

	if stitchErr != nil || (meta != nil && meta.Status == "error") {
		// 拼接失败（Go 级错误 或 Python 返回 status="error"），直接记录失败，不跑分析
		p.service.HandleResult(job.TaskID, job.TaskDir, meta, stitchErr)
		return
	}

	// 第二步：执行分析（拼接成功后才跑）
	analysisCtx, analysisCancel := context.WithTimeout(context.Background(), timeout)
	_, analysisErr := job.AnalysisEngine.Run(analysisCtx, job.TaskDir)
	analysisCancel()

	if analysisErr != nil {
		// 分析失败不影响拼接结果，仅记录日志
		p.logger.Warn("analysis failed",
			zap.String("task_id", job.TaskID),
			zap.Error(analysisErr),
		)
	}

	// 第三步：预生成缩略图存盘
	resultPath := filepath.Join(job.TaskDir, "result", "result.jpg")
	thumbPath := filepath.Join(job.TaskDir, "result", "thumb.jpg")
	if err := generateThumbnail(resultPath, thumbPath); err != nil {
		p.logger.Warn("thumbnail generation failed",
			zap.String("task_id", job.TaskID),
			zap.Error(err),
		)
	}

	// 拼接成功，交给 Service 善后
	p.service.HandleResult(job.TaskID, job.TaskDir, meta, nil)
}
