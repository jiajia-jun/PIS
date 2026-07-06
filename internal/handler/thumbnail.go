package handler

import (
	"net/http"
	"os"
	"path/filepath"

	"pisweb/internal/service"
	"pisweb/internal/tool"

	"github.com/gin-gonic/gin"
)

type ThumbnailHandler struct {
	svc       *service.TaskService
	uploadDir string
}

func NewThumbnailHandler(svc *service.TaskService, uploadDir string) *ThumbnailHandler {
	return &ThumbnailHandler{svc: svc, uploadDir: uploadDir}
}

// GetThumbnail returns the result thumbnail as a binary JPEG stream (in-memory, no disk write)
func (h *ThumbnailHandler) GetThumbnail(c *gin.Context) {
	taskID := c.Param("task_id")

	task, err := h.svc.GetTask(taskID)
	if err != nil || task.Status != "completed" {
		c.JSON(http.StatusNotFound, gin.H{"code": 404, "message": "result not ready"})
		return
	}

	resultPath := filepath.Join(h.uploadDir, taskID, "result", "result.jpg")
	src, err := os.Open(resultPath)
	if err != nil {
		c.JSON(http.StatusNotFound, gin.H{"code": 404, "message": "result file not found"})
		return
	}
	defer src.Close()

	c.Header("Content-Type", "image/jpeg")
	if err := tool.ResizeToJPEG(src, c.Writer, tool.ThumbnailWidth); err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"code": 500, "message": "thumbnail generation failed"})
		return
	}
}
