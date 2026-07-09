package app

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
	"go.uber.org/zap"
)

// App 应用程序，持有所有顶层依赖
type App struct {
	cfg         *config.Config
	accessLog   *zap.Logger
	taskLog     *zap.Logger
	stitchEng   engine.AlgorithmEngine
	analysisEng engine.AlgorithmEngine
	taskSvc     *service.TaskService
	pool        *worker.Pool
	router      *gin.Engine
	ctx         context.Context
	cancel      context.CancelFunc
}

// New 加载配置，初始化所有组件
func New(configPath string) (*App, error) {
	cfg, err := config.Load(configPath)
	if err != nil {
		return nil, fmt.Errorf("加载配置失败: %w", err)
	}

	if cfg.DSN == "" {
		return nil, fmt.Errorf("环境变量 DATABASE_PIS 未设置")
	}

	app := &App{cfg: cfg}
	app.ctx, app.cancel = context.WithCancel(context.Background())

	app.initLoggers()
	app.initDatabase()
	app.initEngines()
	app.initService()
	app.initWorkerPool()
	app.initRouter()

	return app, nil
}

func (a *App) initLoggers() {
	os.MkdirAll("logs", 0755)
	a.accessLog = middleware.InitAccessLogger("logs/access.log")
	a.taskLog = middleware.InitTaskLogger("logs/task.log")
}

func (a *App) initDatabase() {
	if err := database.Init(a.cfg.DSN); err != nil {
		log.Fatalf("数据库初始化失败: %v", err)
	}
}

func (a *App) initEngines() {
	a.stitchEng = newStitchEngine(a.cfg)
	a.analysisEng = newAnalysisEngine(a.cfg)
	fmt.Printf("拼接引擎: %s, 分析引擎: %s\n", a.stitchEng.Name(), a.analysisEng.Name())
}

func newStitchEngine(cfg *config.Config) engine.AlgorithmEngine {
	switch cfg.Engine.StitchType {
	case "python":
		return &engine.PythonEngine{
			PythonPath: cfg.Engine.PythonPath,
			ScriptPath: cfg.Engine.StitchScriptPath,
		}
	case "cpp":
		return &engine.CppEngine{BinaryPath: cfg.Engine.CppBinary}
	default:
		return &engine.MockEngine{}
	}
}

func newAnalysisEngine(cfg *config.Config) engine.AlgorithmEngine {
	switch cfg.Engine.AnalysisType {
	case "python":
		return &engine.PythonAnalysisEngine{
			PythonPath:  cfg.Engine.PythonPath,
			ScriptPath:  cfg.Engine.AnalysisScriptPath,
			AnalysisDir: cfg.Store.AnalysisDir,
		}
	default:
		return &engine.MockAnalysisEngine{AnalysisDir: cfg.Store.AnalysisDir}
	}
}

func (a *App) initService() {
	a.taskSvc = service.NewTaskService(
		database.DB,
		a.taskLog,
		a.cfg.Store.UploadDir,
		a.cfg.Store.AnalysisDir,
	)
}

func (a *App) initWorkerPool() {
	a.pool = worker.NewPool(
		a.cfg.Worker.PoolSize,
		a.cfg.Worker.TimeoutSeconds,
		a.taskSvc,
		a.taskLog,
	)
	a.pool.Start(a.ctx)
}

func (a *App) initRouter() {
	gin.SetMode(gin.ReleaseMode)
	r := gin.New()
	r.Use(middleware.RequestLogger(a.accessLog))

	a.registerAPI(r)
	a.registerStatic(r)

	a.router = r
}

func (a *App) registerAPI(r *gin.Engine) {
	api := r.Group("/api")
	{
		uploadH := handler.NewUploadHandler(a.taskSvc, a.pool, a.stitchEng, a.analysisEng, a.cfg.Store.UploadDir)
		taskH := handler.NewTaskHandler(a.taskSvc, a.cfg.Store.UploadDir, a.cfg.Store.AnalysisDir)
		historyH := handler.NewHistoryHandler(a.taskSvc, a.cfg.Store.AnalysisDir)
		resultH := handler.NewResultHandler(a.taskSvc, a.cfg.Store.UploadDir)
		analysisH := handler.NewAnalysisHandler(a.cfg.Store.AnalysisDir)
		thumbH := handler.NewThumbnailHandler(a.taskSvc, a.cfg.Store.UploadDir)
		inputH := handler.NewInputHandler(a.taskSvc, a.cfg.Store.UploadDir)
		inputThumbH := handler.NewInputThumbHandler(a.taskSvc, a.cfg.Store.UploadDir)

		api.POST("/upload", middleware.BodyLimit(a.cfg.Server.UploadMaxSizeMB), uploadH.Upload)
			api.POST("/upload/sample", uploadH.UploadSample)
		api.GET("/task/:task_id", taskH.GetTask)
		api.GET("/history", historyH.GetHistory)
		api.GET("/result/:task_id", resultH.GetResult)
		api.GET("/analysis/:task_id/:filename", analysisH.GetAnalysis)
		api.GET("/thumbnail/:task_id", thumbH.GetThumbnail)
		api.GET("/input/:task_id/:filename", inputH.GetInput)
		api.GET("/input-thumb/:task_id/:filename", inputThumbH.GetInputThumb)
	}
}

func (a *App) registerStatic(r *gin.Engine) {
	r.Static("/assets", "./frontend/dist/assets")
	r.Static("/avatars", "./frontend/dist/avatars")
	r.StaticFile("/favicon.svg", "./frontend/dist/favicon.svg")
	r.NoRoute(func(c *gin.Context) {
		c.File("./frontend/dist/index.html")
	})
}

// Run 启动服务并等待退出信号
func (a *App) Run() {
	defer a.shutdown()

	host := a.cfg.Server.Host
	if host == "" {
		host = "0.0.0.0"
	}
	addr := fmt.Sprintf("%s:%d", a.cfg.Server.Host, a.cfg.Server.Port)
	fmt.Printf("服务启动: http://%s:%d\n", host, a.cfg.Server.Port)

	go func() {
		if err := a.router.Run(addr); err != nil {
			log.Fatalf("服务启动失败: %v", err)
		}
	}()

	quit := make(chan os.Signal, 1)
	signal.Notify(quit, syscall.SIGINT, syscall.SIGTERM)
	<-quit
}

func (a *App) shutdown() {
	fmt.Println("\n正在关闭服务...")
	a.cancel()
	time.Sleep(500 * time.Millisecond)

	a.accessLog.Sync()
	a.taskLog.Sync()
	fmt.Println("服务已停止")
}
