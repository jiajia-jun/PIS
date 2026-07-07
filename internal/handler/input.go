package handler

import (
	"net/http"
	"os"
	"path/filepath"

	"pisweb/internal/service"

	"github.com/gin-gonic/gin"
)

// InputHandler 原始图片处理器
type InputHandler struct {
	svc       *service.TaskService
	uploadDir string
}

// NewInputHandler 创建 InputHandler
func NewInputHandler(svc *service.TaskService, uploadDir string) *InputHandler {
	return &InputHandler{svc: svc, uploadDir: uploadDir}
}

// GetInput 返回原始上传图片 GET /api/input/:task_id/:filename
func (h *InputHandler) GetInput(c *gin.Context) {
	taskID := c.Param("task_id")
	filename := c.Param("filename")

	if taskID == "" || filename == "" {
		c.JSON(http.StatusBadRequest, gin.H{"code": 400, "message": "缺少参数"})
		return
	}

	// 确认任务存在
	if _, err := h.svc.GetTask(taskID); err != nil {
		c.JSON(http.StatusNotFound, gin.H{"code": 404, "message": "任务不存在"})
		return
	}

	// 安全检查: 拒绝路径穿越
	if filepath.Base(filename) != filename {
		c.JSON(http.StatusBadRequest, gin.H{"code": 400, "message": "非法文件名"})
		return
	}

	filePath := filepath.Join(h.uploadDir, taskID, "input", filename)
	if _, err := os.Stat(filePath); os.IsNotExist(err) {
		c.JSON(http.StatusNotFound, gin.H{"code": 404, "message": "文件不存在"})
		return
	}

	c.File(filePath)
}
