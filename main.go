package main

import (
	"context"
	"fmt"
	"log"
	"os"
	"os/signal"
	"syscall"
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

func main() {
	// 1. 加载配置
	cfg, err := config.Load("config.yaml")
	if err != nil {
		log.Fatalf("config load failed: %v", err)
	}

	if cfg.DSN == "" {
		log.Fatal("env DATABASE_PIS not set")
	}

	// 2. 初始化日志
	os.MkdirAll("logs", 0755)
	accessLogger := middleware.InitAccessLogger("logs/access.log")
	taskLogger := middleware.InitTaskLogger("logs/task.log")
	defer accessLogger.Sync()
	defer taskLogger.Sync()

	// 3. 初始化数据库
	if err := database.Init(cfg.DSN); err != nil {
		log.Fatalf("db init failed: %v", err)
	}

	// 4. 创建拼接引擎
	var stitchEngine engine.AlgorithmEngine
	switch cfg.Engine.StitchType {
	case "python":
		stitchEngine = &engine.PythonEngine{
			PythonPath: cfg.Engine.PythonPath,
			ScriptPath: cfg.Engine.StitchScriptPath,
		}
	case "cpp":
		stitchEngine = &engine.CppEngine{
			BinaryPath: cfg.Engine.CppBinary,
		}
	default:
		stitchEngine = &engine.MockEngine{}
	}

	// 5. 创建分析引擎
	var analysisEngine engine.AlgorithmEngine
	switch cfg.Engine.AnalysisType {
	case "python":
		analysisEngine = &engine.PythonAnalysisEngine{
			PythonPath:  cfg.Engine.PythonPath,
			ScriptPath:  cfg.Engine.AnalysisScriptPath,
			AnalysisDir: cfg.Store.AnalysisDir,
		}
	default:
		analysisEngine = &engine.MockAnalysisEngine{
			AnalysisDir: cfg.Store.AnalysisDir,
		}
	}

	fmt.Printf("stitch engine: %s, analysis engine: %s\n", stitchEngine.Name(), analysisEngine.Name())

	// 6. 初始化 TaskService
	taskSvc := service.NewTaskService(
		database.DB,
		taskLogger,
		cfg.Store.UploadDir,
		cfg.Store.AnalysisDir,
	)

	// 7. 创建 Worker Pool
	pool := worker.NewPool(cfg.Worker.PoolSize, cfg.Worker.TimeoutSeconds, taskSvc, taskLogger)
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()
	pool.Start(ctx)

	// 8. 初始化 Handler
	uploadH := handler.NewUploadHandler(taskSvc, pool, stitchEngine, analysisEngine, cfg.Store.UploadDir)
	taskH := handler.NewTaskHandler(taskSvc, cfg.Store.AnalysisDir)
	historyH := handler.NewHistoryHandler(taskSvc, cfg.Store.AnalysisDir)
	resultH := handler.NewResultHandler(taskSvc, cfg.Store.UploadDir)
	analysisH := handler.NewAnalysisHandler(cfg.Store.AnalysisDir)
	thumbH := handler.NewThumbnailHandler(taskSvc, cfg.Store.UploadDir)

	// 9. 初始化 Gin 路由
	gin.SetMode(gin.ReleaseMode)
	r := gin.New()
	r.Use(middleware.RequestLogger(accessLogger))

	api := r.Group("/api")
	{
		api.POST("/upload", middleware.BodyLimit(cfg.Server.UploadMaxSizeMB), uploadH.Upload)
		api.GET("/task/:task_id", taskH.GetTask)
		api.GET("/history", historyH.GetHistory)
		api.GET("/result/:task_id", resultH.GetResult)
		api.GET("/analysis/:task_id/:filename", analysisH.GetAnalysis)
		api.GET("/thumbnail/:task_id", thumbH.GetThumbnail)
	}

	// 10. 启动服务器
	addr := fmt.Sprintf(":%d", cfg.Server.Port)
	fmt.Printf("server starting on http://localhost%s\n", addr)

	go func() {
		if err := r.Run(addr); err != nil {
			log.Fatalf("server start failed: %v", err)
		}
	}()

	// 11. 优雅退出
	quit := make(chan os.Signal, 1)
	signal.Notify(quit, syscall.SIGINT, syscall.SIGTERM)
	<-quit

	fmt.Println("\nshutting down...")
	cancel()
	time.Sleep(500 * time.Millisecond)
	fmt.Println("server stopped")
}
