package middleware

import (
	"time"

	"github.com/gin-gonic/gin"
	"go.uber.org/zap"
	"go.uber.org/zap/zapcore"
)

// RequestLogger 请求日志中间件，使用 zap 记录 method、path、状态码、耗时
func RequestLogger(logger *zap.Logger) gin.HandlerFunc {
	return func(c *gin.Context) {
		start := time.Now()
		path := c.Request.URL.Path
		rawQuery := c.Request.URL.RawQuery

		c.Next()

		latency := time.Since(start)
		statusCode := c.Writer.Status()

		// 拼接完整路径
		fullPath := path
		if rawQuery != "" {
			fullPath = path + "?" + rawQuery
		}

		logger.Info("",
			zap.String("method", c.Request.Method),
			zap.String("path", fullPath),
			zap.Int("status", statusCode),
			zap.Duration("duration", latency),
		)
	}
}

// InitAccessLogger 创建 access.log 的 zap Logger，ConsoleEncoder 格式
func InitAccessLogger(path string) *zap.Logger {
	cfg := zap.NewProductionConfig()
	cfg.Encoding = "console"
	cfg.EncoderConfig.TimeKey = "time"
	cfg.EncoderConfig.EncodeTime = zapcore.TimeEncoderOfLayout("2006-01-02 15:04:05")
	cfg.EncoderConfig.EncodeDuration = zapcore.StringDurationEncoder
	cfg.OutputPaths = []string{path}
	cfg.DisableStacktrace = true

	logger, err := cfg.Build()
	if err != nil {
		panic(err)
	}
	return logger
}

// InitTaskLogger 创建 task.log 的 zap Logger，ConsoleEncoder 格式
func InitTaskLogger(path string) *zap.Logger {
	cfg := zap.NewProductionConfig()
	cfg.Encoding = "console"
	cfg.EncoderConfig.TimeKey = "time"
	cfg.EncoderConfig.EncodeTime = zapcore.TimeEncoderOfLayout("2006-01-02 15:04:05")
	cfg.OutputPaths = []string{path}
	cfg.DisableStacktrace = true

	logger, err := cfg.Build()
	if err != nil {
		panic(err)
	}
	return logger
}
