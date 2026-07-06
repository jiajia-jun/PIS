package handler

import (
	"fmt"
	"io"
	"mime/multipart"
	"net/http"
	"os"
	"path/filepath"

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
		c.JSON(http.StatusBadRequest, gin.H{"code": 400, "message": "file parse error"})
		return
	}

	files := form.File["images"]
	if len(files) == 0 {
		c.JSON(http.StatusBadRequest, gin.H{"code": 400, "message": "no images selected"})
		return
	}

	task, err := h.svc.CreateTask(len(files))
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"code": 500, "message": "create task failed"})
		return
	}
	taskID := task.ID

	inputDir := filepath.Join(h.uploadDir, taskID, "input")
	resultDir := filepath.Join(h.uploadDir, taskID, "result")
	if err := os.MkdirAll(inputDir, 0755); err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"code": 500, "message": "create dir failed"})
		return
	}
	if err := os.MkdirAll(resultDir, 0755); err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"code": 500, "message": "create dir failed"})
		return
	}

	for i, file := range files {
		dstPath := filepath.Join(inputDir, fmt.Sprintf("img_%03d%s", i+1, filepath.Ext(file.Filename)))
		if err := saveUploadedFile(file, dstPath); err != nil {
			c.JSON(http.StatusInternalServerError, gin.H{"code": 500, "message": "save file failed"})
			return
		}
	}

	taskDir := filepath.Join(h.uploadDir, taskID)
	h.pool.Submit(worker.Job{
		TaskID:         taskID,
		TaskDir:        taskDir,
		StitchEngine:   h.stitchEngine,
		AnalysisEngine: h.analysisEngine,
	})

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
