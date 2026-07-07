package middleware

import (
	"time"

	"github.com/gin-gonic/gin"
	"go.uber.org/zap"
	"go.uber.org/zap/zapcore"
)

// RequestLogger 请求日志中间件，同时输出到文件和控制台
func RequestLogger(logger *zap.Logger) gin.HandlerFunc {
	return func(c *gin.Context) {
		start := time.Now()
		rawPath := c.Request.URL.Path
		rawQuery := c.Request.URL.RawQuery

		c.Next()

		latency := time.Since(start)
		statusCode := c.Writer.Status()

		fullPath := rawPath
		if rawQuery != "" {
			fullPath = rawPath + "?" + rawQuery
		}

		logger.Info("",
			zap.String("method", c.Request.Method),
			zap.String("path", fullPath),
			zap.Int("status", statusCode),
			zap.Duration("duration", latency),
		)
	}
}

// InitAccessLogger 创建访问日志 Logger，同时输出到文件和标准输出
func InitAccessLogger(path string) *zap.Logger {
	cfg := zap.NewProductionConfig()
	cfg.Encoding = "console"
	cfg.EncoderConfig.TimeKey = "time"
	cfg.EncoderConfig.EncodeTime = zapcore.TimeEncoderOfLayout("2006-01-02 15:04:05")
	cfg.EncoderConfig.EncodeDuration = zapcore.StringDurationEncoder
	cfg.OutputPaths = []string{path, "stdout"}
	cfg.DisableStacktrace = true

	logger, err := cfg.Build()
	if err != nil {
		panic(err)
	}
	return logger
}

// InitTaskLogger 创建任务日志 Logger，同时输出到文件和标准输出
func InitTaskLogger(path string) *zap.Logger {
	cfg := zap.NewProductionConfig()
	cfg.Encoding = "console"
	cfg.EncoderConfig.TimeKey = "time"
	cfg.EncoderConfig.EncodeTime = zapcore.TimeEncoderOfLayout("2006-01-02 15:04:05")
	cfg.OutputPaths = []string{path, "stdout"}
	cfg.DisableStacktrace = true

	logger, err := cfg.Build()
	if err != nil {
		panic(err)
	}
	return logger
}
