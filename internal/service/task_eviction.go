package service

import (
	"os"
	"path/filepath"

	"pisweb/internal/model"

	"go.uber.org/zap"
)

const maxHistoryRecords = 40

// enforceHistoryLimit 淘汰机制：completed+failed 超过上限时删除最旧记录及文件
func (s *TaskService) enforceHistoryLimit() {
	var count int64
	s.db.Model(&model.Task{}).Where("status IN ?", []string{model.StatusCompleted, model.StatusFailed}).Count(&count)

	if count <= maxHistoryRecords {
		return
	}

	excess := int(count - maxHistoryRecords)
	var toDelete []model.Task
	s.db.Where("status IN ?", []string{model.StatusCompleted, model.StatusFailed}).
		Order("created_at ASC").Limit(excess).Find(&toDelete)

	for _, t := range toDelete {
		os.RemoveAll(filepath.Join(s.uploadDir, t.ID))
		os.RemoveAll(filepath.Join(s.analysisDir, t.ID))
		s.db.Delete(&t)
		s.taskLog.Info("history evicted",
			zap.String("task_id", t.ID),
			zap.String("status", t.Status),
		)
	}
}
