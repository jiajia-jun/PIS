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
	"pisweb/internal/tool"
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

	// 读取运行模式并写入任务
	mode := "normal"
	if modes, ok := form.Value["mode"]; ok && len(modes) > 0 && modes[0] == "super" {
		mode = "super"
	}
	task.Mode = mode
	h.svc.UpdateTask(task)

	taskID := task.ID

	inputDir := filepath.Join(h.uploadDir, taskID, "input")
	thumbDir := filepath.Join(h.uploadDir, taskID, "input_thumb")
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
	if err := os.MkdirAll(thumbDir, 0755); err != nil {
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
		dstName := fmt.Sprintf("img_%03d%s", i+1, filepath.Ext(file.Filename))
		dstPath := filepath.Join(inputDir, dstName)
		if err := saveUploadedFile(file, dstPath); err != nil {
			c.JSON(
				http.StatusInternalServerError,
				gin.H{"code": 500, "message": "保存文件失败"})
			return
		}
		// 生成源图片缩略图
		thumbPath := filepath.Join(thumbDir, dstName)
		if err := saveInputThumbnail(file, thumbPath); err != nil {
			// 缩略图失败不影响主流程，仅记录
			_ = err
		}
	}

	taskDir := filepath.Join(h.uploadDir, taskID)

	// 根据运行模式设置超时：normal=30s, super=300s
	timeoutSeconds := 0 // 0 表示使用 Pool 默认值 30s
	if mode == "super" {
		timeoutSeconds = 300
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

// saveInputThumbnail 读取上传文件并生成缩略图
func saveInputThumbnail(file *multipart.FileHeader, dst string) error {
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

	return tool.ResizeToJPEG(src, dstFile, tool.ThumbnailWidth)
}

// UploadSample 使用预置示例图片创建拼接任务
func (h *UploadHandler) UploadSample(c *gin.Context) {
	mode := c.DefaultQuery("mode", "normal")
	if mode != "super" {
		mode = "normal"
	}

	samplesDir := filepath.Join(filepath.Dir(h.uploadDir), "samples", "input")
	entries, err := os.ReadDir(samplesDir)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{
			"code":    500,
			"message": "示例数据不可用",
		})
		return
	}

	var imageFiles []string
	for _, entry := range entries {
		if entry.IsDir() {
			continue
		}
		ext := strings.ToLower(filepath.Ext(entry.Name()))
		if ext == ".jpg" || ext == ".jpeg" || ext == ".png" || ext == ".webp" {
			imageFiles = append(imageFiles, entry.Name())
		}
	}

	if len(imageFiles) == 0 {
		c.JSON(http.StatusInternalServerError, gin.H{
			"code":    500,
			"message": "示例数据为空",
		})
		return
	}

	task, err := h.svc.CreateTask(len(imageFiles))
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{
			"code":    500,
			"message": "创建任务失败",
		})
		return
	}

	task.Mode = mode
	h.svc.UpdateTask(task)
	taskID := task.ID

	inputDir := filepath.Join(h.uploadDir, taskID, "input")
	thumbDir := filepath.Join(h.uploadDir, taskID, "input_thumb")
	resultDir := filepath.Join(h.uploadDir, taskID, "result")
	if err := os.MkdirAll(inputDir, 0755); err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"code": 500, "message": "创建目录失败"})
		return
	}
	if err := os.MkdirAll(thumbDir, 0755); err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"code": 500, "message": "创建目录失败"})
		return
	}
	if err := os.MkdirAll(resultDir, 0755); err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"code": 500, "message": "创建目录失败"})
		return
	}

	for _, fname := range imageFiles {
		srcPath := filepath.Join(samplesDir, fname)
		dstPath := filepath.Join(inputDir, fname)
		if err := copyFile(srcPath, dstPath); err != nil {
			c.JSON(http.StatusInternalServerError, gin.H{"code": 500, "message": "复制示例文件失败"})
			return
		}

		// 生成缩略图
		thumbPath := filepath.Join(thumbDir, fname)
		if err := generateThumbnailFromFile(dstPath, thumbPath); err != nil {
			_ = err // 缩略图失败不影响主流程
		}
	}

	taskDir := filepath.Join(h.uploadDir, taskID)

	// 根据运行模式设置超时：normal=30s, super=300s
	timeoutSeconds := 0
	if mode == "super" {
		timeoutSeconds = 300
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

// copyFile 复制单个文件
func copyFile(src, dst string) error {
	s, err := os.Open(src)
	if err != nil {
		return err
	}
	defer s.Close()

	d, err := os.Create(dst)
	if err != nil {
		return err
	}
	defer d.Close()

	_, err = io.Copy(d, s)
	return err
}

// generateThumbnailFromFile 从磁盘文件生成缩略图
func generateThumbnailFromFile(srcPath, dstPath string) error {
	src, err := os.Open(srcPath)
	if err != nil {
		return err
	}
	defer src.Close()

	dst, err := os.Create(dstPath)
	if err != nil {
		return err
	}
	defer dst.Close()

	return tool.ResizeToJPEG(src, dst, tool.ThumbnailWidth)
}
