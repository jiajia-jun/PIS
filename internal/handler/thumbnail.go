package handler

import (
	"net/http"
	"path/filepath"

	"pisweb/internal/service"

	"github.com/gin-gonic/gin"
)

type ThumbnailHandler struct {
	svc       *service.TaskService
	uploadDir string
}

func NewThumbnailHandler(svc *service.TaskService, uploadDir string) *ThumbnailHandler {
	return &ThumbnailHandler{svc: svc, uploadDir: uploadDir}
}

// GetThumbnail 返回预生成的缩略图（Worker 已存入 result/thumb.jpg）
func (h *ThumbnailHandler) GetThumbnail(c *gin.Context) {
	taskID := c.Param("task_id")

	task, err := h.svc.GetTask(taskID)
	if err != nil || task.Status != "completed" {
		c.JSON(http.StatusNotFound, gin.H{"code": 404, "message": "结果尚未就绪"})
		return
	}

	thumbPath := filepath.Join(h.uploadDir, taskID, "result", "thumb.jpg")
	c.Header("Content-Type", "image/jpeg")
	c.File(thumbPath)
}
