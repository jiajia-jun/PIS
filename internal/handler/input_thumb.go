package handler

import (
	"net/http"
	"os"
	"path/filepath"

	"pisweb/internal/service"

	"github.com/gin-gonic/gin"
)

// InputThumbHandler 源图片缩略图处理器
type InputThumbHandler struct {
	svc       *service.TaskService
	uploadDir string
}

// NewInputThumbHandler 创建 InputThumbHandler
func NewInputThumbHandler(svc *service.TaskService, uploadDir string) *InputThumbHandler {
	return &InputThumbHandler{svc: svc, uploadDir: uploadDir}
}

// GetInputThumb 返回源图片缩略图 GET /api/input-thumb/:task_id/:filename
func (h *InputThumbHandler) GetInputThumb(c *gin.Context) {
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

	filePath := filepath.Join(h.uploadDir, taskID, "input_thumb", filename)
	if _, err := os.Stat(filePath); os.IsNotExist(err) {
		c.JSON(http.StatusNotFound, gin.H{"code": 404, "message": "缩略图不存在"})
		return
	}

	c.Header("Cache-Control", "public, max-age=3600")
	c.File(filePath)
}
