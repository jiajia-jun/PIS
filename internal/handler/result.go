package handler

import (
	"net/http"
	"os"
	"path/filepath"
	"pisweb/internal/service"

	"github.com/gin-gonic/gin"
)

// ResultHandler 结果图处理器
type ResultHandler struct {
	svc       *service.TaskService
	uploadDir string
}

// NewResultHandler 创建 ResultHandler
func NewResultHandler(svc *service.TaskService, uploadDir string) *ResultHandler {
	return &ResultHandler{svc: svc, uploadDir: uploadDir}
}

// GetResult 返回拼接结果图 GET /api/result/:task_id
func (h *ResultHandler) GetResult(c *gin.Context) {
	taskID := c.Param("task_id")
	if taskID == "" {
		c.JSON(http.StatusBadRequest, gin.H{"code": 400, "message": "缺少 task_id"})
		return
	}

	// 确认任务存在且已完成
	task, err := h.svc.GetTask(taskID)
	if err != nil {
		c.JSON(http.StatusNotFound, gin.H{"code": 404, "message": "任务不存在"})
		return
	}
	if task.Status != "completed" {
		c.JSON(http.StatusNotFound, gin.H{"code": 404, "message": "结果尚未生成"})
		return
	}

	// 读取 result.jpg 并返回二进制流
	resultPath := filepath.Join(h.uploadDir, taskID, "result", "result.jpg")
	if _, err := os.Stat(resultPath); os.IsNotExist(err) {
		c.JSON(http.StatusNotFound, gin.H{"code": 404, "message": "结果文件不存在"})
		return
	}

	c.Header("Cache-Control", "public, max-age=3600")
	c.File(resultPath)
}
