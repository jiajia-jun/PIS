package handler

import (
	"fmt"
	"io"
	"mime/multipart"
	"net/http"
	"os"
	"path/filepath"
	"strings"
	"time"

	"pisweb/internal/engine"
	"pisweb/internal/service"
	"pisweb/internal/worker"

	"github.com/gin-gonic/gin"
)

type UploadHandler struct {
	svc            *service.TaskService
	pool           *worker.Pool
	stitchEngine   engine.AlgorithmEngine
	analysisEngine engine.AlgorithmEngine
	uploadDir      string
}

func NewUploadHandler(svc *service.TaskService, pool *worker.Pool, stitchEngine, analysisEngine engine.AlgorithmEngine, uploadDir string) *UploadHandler {
	return &UploadHandler{
		svc:            svc,
		pool:           pool,
		stitchEngine:   stitchEngine,
		analysisEngine: analysisEngine,
		uploadDir:      uploadDir,
	}
}

func (h *UploadHandler) Upload(c *gin.Context) {
	form, err := c.MultipartForm()
	if err != nil {
		msg := "文件解析错误"
		if strings.Contains(err.Error(), "request body too large") {
			c.JSON(http.StatusRequestEntityTooLarge, gin.H{
				"code":    413,
				"message": "文件总大小超过限制",
			})
			return
		}
		c.JSON(http.StatusBadRequest, gin.H{"code": 400, "message": msg})
		return
	}

	files := form.File["images"]
	if len(files) == 0 {
		c.JSON(
			http.StatusBadRequest,
			gin.H{
				"code":    400,
				"message": "未选择图片",
			})
		return
	}

	task, err := h.svc.CreateTask(len(files))
	if err != nil {
		c.JSON(
			http.StatusInternalServerError,
			gin.H{
				"code":    500,
				"message": "创建任务失败",
			})
		return
	}
	taskID := task.ID

	inputDir := filepath.Join(h.uploadDir, taskID, "input")
	resultDir := filepath.Join(h.uploadDir, taskID, "result")
	if err := os.MkdirAll(inputDir, 0755); err != nil {
		c.JSON(
			http.StatusInternalServerError,
			gin.H{
				"code":    500,
				"message": "创建目录失败",
			})
		return
	}
	if err := os.MkdirAll(resultDir, 0755); err != nil {
		c.JSON(
			http.StatusInternalServerError,
			gin.H{
				"code":    500,
				"message": "创建目录失败",
			})
		return
	}

	for i, file := range files {
		dstPath := filepath.Join(inputDir, fmt.Sprintf("img_%03d%s", i+1, filepath.Ext(file.Filename)))
		if err := saveUploadedFile(file, dstPath); err != nil {
			c.JSON(
				http.StatusInternalServerError,
				gin.H{"code": 500, "message": "保存文件失败"})
			return
		}
	}

	taskDir := filepath.Join(h.uploadDir, taskID)

	// 读取运行模式：normal=30s, super=60s
	timeoutSeconds := 0 // 0 表示使用 Pool 默认值 30s
	if mode := c.PostForm("mode"); mode == "super" {
		timeoutSeconds = 60
	}

	if err := h.pool.Submit(worker.Job{
		TaskID:         taskID,
		TaskDir:        taskDir,
		StitchEngine:   h.stitchEngine,
		AnalysisEngine: h.analysisEngine,
		TimeoutSeconds: timeoutSeconds,
	}, 3*time.Second); err != nil {
		c.JSON(http.StatusServiceUnavailable, gin.H{
			"code":    503,
			"message": "系统繁忙，请稍后重试",
		})
		return
	}

	c.JSON(http.StatusOK, gin.H{
		"code":    0,
		"message": "ok",
		"data":    gin.H{"task_id": taskID},
	})
}

func saveUploadedFile(file *multipart.FileHeader, dst string) error {
	src, err := file.Open()
	if err != nil {
		return err
	}
	defer src.Close()

	dstFile, err := os.Create(dst)
	if err != nil {
		return err
	}
	defer dstFile.Close()

	_, err = io.Copy(dstFile, src)
	return err
}
