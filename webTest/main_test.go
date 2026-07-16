package webtest

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"image"
	"image/color"
	"image/jpeg"
	"io"
	"mime/multipart"
	"net/http/httptest"
	"os"
	"path/filepath"
	"testing"
	"time"

	"pisweb/internal/config"
	"pisweb/internal/database"
	"pisweb/internal/engine"
	"pisweb/internal/handler"
	"pisweb/internal/middleware"
	"pisweb/internal/service"
	"pisweb/internal/worker"

	"github.com/gin-gonic/gin"
)

var (
	router  *gin.Engine
	taskSvc *service.TaskService
	pool    *worker.Pool
)

// TestMain 初始化测试环境
func TestMain(m *testing.M) {
	// 加载配置
	cfg, err := config.Load("../config.yaml")
	if err != nil {
		fmt.Printf("config load failed: %v\n", err)
		os.Exit(1)
	}

	if cfg.DSN == "" {
		fmt.Println("skip: DATABASE_PIS not set")
		os.Exit(0)
	}

	// 初始化数据库
	if err := database.Init(cfg.DSN); err != nil {
		fmt.Printf("db init failed: %v\n", err)
		os.Exit(1)
	}

	// 创建 Mock 引擎
	stitchEngine := &engine.MockEngine{}
	analysisEngine := &engine.MockAnalysisEngine{AnalysisDir: cfg.Store.AnalysisDir}

	// 初始化 TaskService
	os.MkdirAll("logs", 0755)
	taskLogger := middleware.InitTaskLogger("logs/test_task.log")
	defer taskLogger.Sync()

	taskSvc = service.NewTaskService(
		database.DB,
		taskLogger,
		cfg.Store.UploadDir,
		cfg.Store.AnalysisDir,
	)

	// 创建 Worker Pool
	pool = worker.NewPool(cfg.Worker.PoolSize, cfg.Worker.TimeoutSeconds, taskSvc, taskLogger)
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()
	pool.Start(ctx)

	// 初始化 Handler
	uploadH := handler.NewUploadHandler(taskSvc, pool, stitchEngine, analysisEngine, cfg.Store.UploadDir)
	taskH := handler.NewTaskHandler(taskSvc, cfg.Store.UploadDir, cfg.Store.AnalysisDir)
	historyH := handler.NewHistoryHandler(taskSvc, cfg.Store.AnalysisDir)
	resultH := handler.NewResultHandler(taskSvc, cfg.Store.UploadDir)
	analysisH := handler.NewAnalysisHandler(cfg.Store.AnalysisDir)
	thumbH := handler.NewThumbnailHandler(taskSvc, cfg.Store.UploadDir)

	// 初始化路由
	gin.SetMode(gin.TestMode)
	router = gin.New()
	api := router.Group("/api")
	{
		api.POST("/upload", uploadH.Upload)
		api.GET("/task/:task_id", taskH.GetTask)
		api.GET("/history", historyH.GetHistory)
		api.GET("/result/:task_id", resultH.GetResult)
		api.GET("/analysis/:task_id/:filename", analysisH.GetAnalysis)
		api.GET("/thumbnail/:task_id", thumbH.GetThumbnail)
	}

	// 确保存储目录存在
	os.MkdirAll(cfg.Store.UploadDir, 0755)
	os.MkdirAll(cfg.Store.AnalysisDir, 0755)

	code := m.Run()
	os.Exit(code)
}

// tinyJPEG 生成 1x1 有效 JPEG 字节（供测试上传使用）
func tinyJPEG() []byte {
	img := image.NewRGBA(image.Rect(0, 0, 1, 1))
	img.Set(0, 0, color.RGBA{R: 255, G: 0, B: 0, A: 255})
	buf := &bytes.Buffer{}
	jpeg.Encode(buf, img, &jpeg.Options{Quality: 80})
	return buf.Bytes()
}

func doUpload(t *testing.T, filenames ...string) string {
	t.Helper()

	body := &bytes.Buffer{}
	writer := multipart.NewWriter(body)
	imgData := tinyJPEG()

	for _, name := range filenames {
		part, err := writer.CreateFormFile("images", filepath.Base(name))
		if err != nil {
			t.Fatalf("create form file: %v", err)
		}
		part.Write(imgData)
	}

	if err := writer.Close(); err != nil {
		t.Fatalf("close writer: %v", err)
	}

	req := httptest.NewRequest("POST", "/api/upload", body)
	req.Header.Set("Content-Type", writer.FormDataContentType())
	w := httptest.NewRecorder()
	router.ServeHTTP(w, req)

	if w.Code != 200 {
		t.Fatalf("upload failed: code=%d body=%s", w.Code, w.Body.String())
	}

	var resp struct {
		Code    int    `json:"code"`
		Message string `json:"message"`
		Data    struct {
			TaskID string `json:"task_id"`
		} `json:"data"`
	}
	json.Unmarshal(w.Body.Bytes(), &resp)

	if resp.Data.TaskID == "" {
		t.Fatal("task_id is empty")
	}
	return resp.Data.TaskID
}

func doGet(t *testing.T, path string) *httptest.ResponseRecorder {
	t.Helper()
	req := httptest.NewRequest("GET", path, nil)
	w := httptest.NewRecorder()
	router.ServeHTTP(w, req)
	return w
}

// ---------- 测试用例 ----------

// TestUploadAndTaskFlow 上传 → 轮询 → 结果图 → 缩略图 → 分析图 全链路
func TestUploadAndTaskFlow(t *testing.T) {
	// 1. 上传 3 张图片
	taskID := doUpload(t, "img1.jpg", "img2.jpg", "img3.jpg")
	t.Logf("task_id = %s", taskID)

	// 2. 等待 Mock Engine 处理完成（sleep 1s + analysis 0.5s）
	time.Sleep(2 * time.Second)

	// 3. 轮询任务状态
	w := doGet(t, "/api/task/"+taskID)
	if w.Code != 200 {
		t.Fatalf("get task failed: code=%d", w.Code)
	}

	var taskResp struct {
		Code int `json:"code"`
		Data struct {
			TaskID       string   `json:"task_id"`
			Status       string   `json:"status"`
			CostMs       int64    `json:"cost_ms"`
			Keypoints    int      `json:"keypoints"`
			ImageCount   int      `json:"image_count"`
			ResultURL    string   `json:"result_url"`
			ThumbnailURL string   `json:"thumbnail_url"`
			AnalysisURLs []string `json:"analysis_urls"`
		} `json:"data"`
	}
	json.Unmarshal(w.Body.Bytes(), &taskResp)

	if taskResp.Data.Status != "completed" {
		t.Fatalf("expected completed, got %s", taskResp.Data.Status)
	}
	if taskResp.Data.ImageCount != 3 {
		t.Fatalf("expected image_count=3, got %d", taskResp.Data.ImageCount)
	}
	if taskResp.Data.CostMs == 0 {
		t.Error("cost_ms should > 0")
	}
	if taskResp.Data.Keypoints == 0 {
		t.Error("keypoints should > 0")
	}
	if taskResp.Data.ResultURL == "" {
		t.Error("result_url is empty")
	}
	if taskResp.Data.ThumbnailURL == "" {
		t.Error("thumbnail_url is empty")
	}
	if len(taskResp.Data.AnalysisURLs) == 0 {
		t.Error("analysis_urls is empty")
	}
	t.Logf("status=%s cost_ms=%d keypoints=%d analysis_urls=%v",
		taskResp.Data.Status, taskResp.Data.CostMs, taskResp.Data.Keypoints, taskResp.Data.AnalysisURLs)

	// 4. 获取结果原图
	w = doGet(t, taskResp.Data.ResultURL)
	if w.Code != 200 {
		t.Fatalf("get result failed: code=%d", w.Code)
	}
	if w.Header().Get("Content-Type") == "" {
		t.Error("result Content-Type is empty")
	}
	t.Logf("result size = %d bytes, Content-Type = %s", w.Body.Len(), w.Header().Get("Content-Type"))

	// 5. 获取缩略图
	w = doGet(t, taskResp.Data.ThumbnailURL)
	if w.Code != 200 {
		t.Fatalf("get thumbnail failed: code=%d", w.Code)
	}
	if w.Body.Len() == 0 {
		t.Error("thumbnail body is empty")
	}
	t.Logf("thumbnail size = %d bytes", w.Body.Len())

	// 6. 获取分析图表
	if len(taskResp.Data.AnalysisURLs) > 0 {
		w = doGet(t, taskResp.Data.AnalysisURLs[0])
		if w.Code != 200 {
			t.Fatalf("get analysis failed: code=%d", w.Code)
		}
		t.Logf("analysis chart size = %d bytes", w.Body.Len())
	}
}

// TestHistory 测试历史记录分页
func TestHistory(t *testing.T) {
	// 先上传一个任务确保有数据
	doUpload(t, "img.jpg")
	time.Sleep(2 * time.Second)

	w := doGet(t, "/api/history?page=1&size=5")
	if w.Code != 200 {
		t.Fatalf("get history failed: code=%d", w.Code)
	}

	var resp struct {
		Code int `json:"code"`
		Data struct {
			Total int64 `json:"total"`
			Page  int   `json:"page"`
			Size  int   `json:"size"`
			Items []struct {
				TaskID       string   `json:"task_id"`
				Status       string   `json:"status"`
				ThumbnailURL string   `json:"thumbnail_url"`
				AnalysisURLs []string `json:"analysis_urls"`
				Error        string   `json:"error"`
			} `json:"items"`
		} `json:"data"`
	}
	json.Unmarshal(w.Body.Bytes(), &resp)

	if resp.Data.Total == 0 {
		t.Error("history total is 0")
	}
	if len(resp.Data.Items) == 0 {
		t.Error("history items is empty")
	}

	// 验证已完成任务的字段
	for _, item := range resp.Data.Items {
		if item.Status == "completed" {
			if item.ThumbnailURL == "" {
				t.Error("completed task missing thumbnail_url")
			}
			t.Logf("task=%s status=%s thumbnail=%s analysis=%v",
				item.TaskID, item.Status, item.ThumbnailURL, item.AnalysisURLs)
		}
	}
}

// TestTaskNotFound 测试不存在的任务
func TestTaskNotFound(t *testing.T) {
	w := doGet(t, "/api/task/non-existent-id")
	if w.Code != 404 {
		t.Fatalf("expected 404, got %d", w.Code)
	}
}

// TestResultNotReady 测试未完成任务的结果图
func TestResultNotReady(t *testing.T) {
	w := doGet(t, "/api/result/non-existent-id")
	if w.Code != 404 {
		t.Fatalf("expected 404, got %d", w.Code)
	}
}

// TestUploadNoImages 测试空上传
func TestUploadNoImages(t *testing.T) {
	body := &bytes.Buffer{}
	writer := multipart.NewWriter(body)
	writer.Close()

	req := httptest.NewRequest("POST", "/api/upload", body)
	req.Header.Set("Content-Type", writer.FormDataContentType())
	w := httptest.NewRecorder()
	router.ServeHTTP(w, req)

	if w.Code != 400 {
		t.Fatalf("expected 400, got %d: %s", w.Code, w.Body.String())
	}
}

// TestConcurrentUpload 并发上传：10 个任务同时提交，验证互不干扰
func TestConcurrentUpload(t *testing.T) {
	const N = 10
	taskIDs := make(chan string, N)
	errs := make(chan error, N)

	for i := 0; i < N; i++ {
		go func(idx int) {
			body := &bytes.Buffer{}
			writer := multipart.NewWriter(body)
			part, _ := writer.CreateFormFile("images", fmt.Sprintf("img_%d.jpg", idx))
			io.WriteString(part, "fake-image-data")
			writer.Close()

			req := httptest.NewRequest("POST", "/api/upload", body)
			req.Header.Set("Content-Type", writer.FormDataContentType())
			w := httptest.NewRecorder()
			router.ServeHTTP(w, req)

			if w.Code != 200 {
				errs <- fmt.Errorf("idx=%d code=%d body=%s", idx, w.Code, w.Body.String())
				return
			}

			var resp struct {
				Data struct {
					TaskID string `json:"task_id"`
				} `json:"data"`
			}
			json.Unmarshal(w.Body.Bytes(), &resp)
			taskIDs <- resp.Data.TaskID
		}(i)
	}

	// 收集结果
	ids := make([]string, 0, N)
	for i := 0; i < N; i++ {
		select {
		case id := <-taskIDs:
			ids = append(ids, id)
		case err := <-errs:
			t.Error(err)
		}
	}

	// 验证所有 task_id 唯一
	seen := make(map[string]bool)
	for _, id := range ids {
		if seen[id] {
			t.Errorf("duplicate task_id: %s", id)
		}
		seen[id] = true
	}
	t.Logf("%d concurrent uploads OK, all task_ids unique", len(ids))

	// 等待处理
	time.Sleep(3 * time.Second)

	// 验证所有任务都完成了
	for _, id := range ids {
		w := doGet(t, "/api/task/"+id)
		var resp struct {
			Data struct {
				Status string `json:"status"`
			} `json:"data"`
		}
		json.Unmarshal(w.Body.Bytes(), &resp)
		if resp.Data.Status != "completed" {
			t.Errorf("task %s status=%s, expected completed (may be timeout with large queue)", id, resp.Data.Status)
		}
	}
}

// TestAnalysisNotFound 测试不存在的分析文件
func TestAnalysisNotFound(t *testing.T) {
	w := doGet(t, "/api/analysis/non-existent/chart.png")
	if w.Code != 404 {
		t.Fatalf("expected 404, got %d", w.Code)
	}
}

// TestHistoryPagination 测试分页边界
func TestHistoryPagination(t *testing.T) {
	// 默认值
	w := doGet(t, "/api/history")
	if w.Code != 200 {
		t.Fatalf("get history failed: code=%d", w.Code)
	}

	// 非法值应回退默认
	w = doGet(t, "/api/history?page=-1&size=999")
	if w.Code != 200 {
		t.Fatalf("get history failed: code=%d", w.Code)
	}

	var resp struct {
		Data struct {
			Size int `json:"size"`
		} `json:"data"`
	}
	json.Unmarshal(w.Body.Bytes(), &resp)
	if resp.Data.Size != 10 {
		t.Errorf("expected size=10 (clamped), got %d", resp.Data.Size)
	}
}
