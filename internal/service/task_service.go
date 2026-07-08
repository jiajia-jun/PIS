package service

import (
	"fmt"
	"path/filepath"
	"pisweb/internal/engine"
	"pisweb/internal/model"

	"go.uber.org/zap"
	"gorm.io/gorm"
)

// TaskService 任务业务逻辑
type TaskService struct {
	db          *gorm.DB
	taskLog     *zap.Logger
	uploadDir   string
	analysisDir string
}

// NewTaskService 创建 TaskService 实例
func NewTaskService(db *gorm.DB, taskLog *zap.Logger, uploadDir, analysisDir string) *TaskService {
	return &TaskService{
		db:          db,
		taskLog:     taskLog,
		uploadDir:   uploadDir,
		analysisDir: analysisDir,
	}
}

// CreateTask 创建新任务记录
func (s *TaskService) CreateTask(imageCount int) (*model.Task, error) {
	task := &model.Task{
		Status:     model.StatusPending,
		ImageCount: imageCount,
	}
	if err := s.db.Create(task).Error; err != nil {
		return nil, fmt.Errorf("创建任务失败: %w", err)
	}
	return task, nil
}

// UpdateTask 更新任务记录
func (s *TaskService) UpdateTask(task *model.Task) error {
	return s.db.Save(task).Error
}

// GetTask 根据 ID 查询任务
func (s *TaskService) GetTask(taskID string) (*model.Task, error) {
	var task model.Task
	if err := s.db.First(&task, "id = ?", taskID).Error; err != nil {
		return nil, err
	}
	return &task, nil
}

// GetHistory 分页查询历史记录，按创建时间倒序
func (s *TaskService) GetHistory(page, size int) ([]model.Task, int64, error) {
	var tasks []model.Task
	var total int64

	if err := s.db.Model(&model.Task{}).Count(&total).Error; err != nil {
		return nil, 0, err
	}

	offset := (page - 1) * size
	if err := s.db.Order("created_at DESC").Offset(offset).Limit(size).Find(&tasks).Error; err != nil {
		return nil, 0, err
	}

	return tasks, total, nil
}

// HandleResult 处理引擎执行结果，更新数据库并写入任务日志
func (s *TaskService) HandleResult(taskID, inputDir string, meta *engine.Meta, runErr error) {
	task, err := s.GetTask(taskID)
	if err != nil {
		return
	}

	if runErr != nil {
		// 执行失败或超时
		task.Status = model.StatusFailed
		task.ErrorMsg = runErr.Error()
		s.db.Save(task)
		s.writeTaskLog(task)
		s.enforceHistoryLimit()
		return
	}

	// 解析 meta.json
	resultDir := filepath.Join(inputDir, "result")
	meta, err = engine.ReadMetaJSON(resultDir)
	if err != nil {
		task.Status = model.StatusFailed
		task.ErrorMsg = fmt.Sprintf("读取处理结果失败")
		s.db.Save(task)
		s.writeTaskLog(task)
		s.enforceHistoryLimit()
		return
	}

	// 根据 meta.Status 判断拼接是否成功
	if meta.Status == "error" {
		task.Status = model.StatusFailed
		if meta.Error != "" {
			task.ErrorMsg = meta.Error
		} else {
			task.ErrorMsg = "拼接失败（未知原因）"
		}
	} else {
		task.Status = model.StatusCompleted
		task.CostMs = meta.CostMs
		task.Keypoints = meta.Keypoints
		task.ResultPath = filepath.Join(resultDir, "result.jpg")
	}
	s.db.Save(task)

	s.writeTaskLog(task)
	s.enforceHistoryLimit()
}

// writeTaskLog 写入任务日志到 logs/task.log
func (s *TaskService) writeTaskLog(task *model.Task) {
	switch task.Status {
	case model.StatusCompleted:
		s.taskLog.Info("",
			zap.String("task_id", task.ID),
			zap.String("status", task.Status),
			zap.Int64("cost_ms", task.CostMs),
			zap.Int("keypoints", task.Keypoints),
			zap.Int("images", task.ImageCount),
		)
	case model.StatusFailed:
		s.taskLog.Error("",
			zap.String("task_id", task.ID),
			zap.String("status", task.Status),
			zap.String("error", task.ErrorMsg),
			zap.Int("images", task.ImageCount),
		)
	default:
		s.taskLog.Info("",
			zap.String("task_id", task.ID),
			zap.String("status", task.Status),
			zap.Int("images", task.ImageCount),
		)
	}
}
