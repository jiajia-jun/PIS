package handler

import (
	"net/http"
	"strconv"

	"pisweb/internal/service"

	"github.com/gin-gonic/gin"
)

// HistoryHandler 历史记录查询处理器
type HistoryHandler struct {
	svc *service.TaskService
}

// NewHistoryHandler 创建 HistoryHandler
func NewHistoryHandler(svc *service.TaskService) *HistoryHandler {
	return &HistoryHandler{svc: svc}
}

// GetHistory 分页查询历史记录 GET /api/history?page=1&size=10
func (h *HistoryHandler) GetHistory(c *gin.Context) {
	page, _ := strconv.Atoi(c.DefaultQuery("page", "1"))
	size, _ := strconv.Atoi(c.DefaultQuery("size", "10"))

	if page < 1 {
		page = 1
	}
	if size < 1 || size > 100 {
		size = 10
	}

	tasks, total, err := h.svc.GetHistory(page, size)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"code": 500, "message": "查询失败"})
		return
	}

	items := make([]gin.H, 0, len(tasks))
	for _, task := range tasks {
		resp := gin.H{
			"task_id":     task.ID,
			"status":      task.Status,
			"image_count": task.ImageCount,
			"keypoints":   task.Keypoints,
			"cost_ms":     task.CostMs,
			"created_at":  task.CreatedAt.Format("2006-01-02T15:04:05Z"),
		}

		if task.Status == "completed" {
			resp["result_url"] = "/api/result/" + task.ID
		}

		items = append(items, resp)
	}

	c.JSON(http.StatusOK, gin.H{
		"code":    0,
		"message": "ok",
		"data": gin.H{
			"total": total,
			"page":  page,
			"size":  size,
			"items": items,
		},
	})
}
