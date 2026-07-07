package handler

import (
	"net/http"
	"os"
	"path/filepath"
	"sort"

	"pisweb/internal/model"
	"pisweb/internal/service"

	"github.com/gin-gonic/gin"
)

// TaskHandler 任务查询处理器
type TaskHandler struct {
	svc         *service.TaskService
	uploadDir   string
	analysisDir string
}

// NewTaskHandler 创建 TaskHandler
func NewTaskHandler(svc *service.TaskService, uploadDir, analysisDir string) *TaskHandler {
	return &TaskHandler{svc: svc, uploadDir: uploadDir, analysisDir: analysisDir}
}

// GetTask 查询单个任务状态 GET /api/task/:task_id
func (h *TaskHandler) GetTask(c *gin.Context) {
	taskID := c.Param("task_id")
	if taskID == "" {
		c.JSON(http.StatusBadRequest, gin.H{"code": 400, "message": "缺少 task_id"})
		return
	}

	task, err := h.svc.GetTask(taskID)
	if err != nil {
		c.JSON(http.StatusNotFound, gin.H{"code": 404, "message": "任务不存在"})
		return
	}

	c.JSON(http.StatusOK, gin.H{
		"code":    0,
		"message": "ok",
		"data":    h.taskToResponse(task),
	})
}

// taskToResponse 将 Task 模型转为 API 响应格式
func (h *TaskHandler) taskToResponse(task *model.Task) gin.H {
	resp := gin.H{
		"task_id":     task.ID,
		"status":      task.Status,
		"image_count": task.ImageCount,
		"created_at":  task.CreatedAt.Format("2006-01-02T15:04:05Z"),
	}

	if task.Status == model.StatusCompleted {
		resp["cost_ms"] = task.CostMs
		resp["keypoints"] = task.Keypoints
		resp["result_url"] = "/api/result/" + task.ID
		resp["thumbnail_url"] = "/api/thumbnail/" + task.ID
		if urls := listAnalysisFiles(h.analysisDir, task.ID); len(urls) > 0 {
			resp["analysis_urls"] = urls
		}
		if urls := listInputFiles(h.uploadDir, task.ID); len(urls) > 0 {
			resp["input_urls"] = urls
		}
	}

	if task.Status == model.StatusFailed {
		resp["error"] = task.ErrorMsg
	}

	return resp
}

// listInputFiles 列出任务的原始上传图片 URL
func listInputFiles(uploadDir, taskID string) []string {
	dir := filepath.Join(uploadDir, taskID, "input")
	entries, err := os.ReadDir(dir)
	if err != nil {
		return nil
	}

	var urls []string
	for _, e := range entries {
		if !e.IsDir() {
			urls = append(urls, "/api/input/"+taskID+"/"+e.Name())
		}
	}
	sort.Strings(urls)
	return urls
}
