package engine

import (
	"context"
	"encoding/base64"
	"os"
	"path/filepath"
	"time"
)

// MockAnalysisEngine 模拟分析引擎，用于开发测试
type MockAnalysisEngine struct {
	AnalysisDir string
}

func (m *MockAnalysisEngine) Name() string { return "mock-analysis" }

func (m *MockAnalysisEngine) Run(ctx context.Context, taskDir string) (*Meta, error) {
	// 模拟分析耗时
	select {
	case <-time.After(500 * time.Millisecond):
	case <-ctx.Done():
		return nil, ctx.Err()
	}

	// 从 taskDir 提取 task_id（最后一段路径名）
	taskID := filepath.Base(taskDir)
	outDir := filepath.Join(m.AnalysisDir, taskID)
	if err := os.MkdirAll(outDir, 0755); err != nil {
		return nil, err
	}

	// 生成一个占位 PNG 文件，验证链路
	minPNG, _ := base64.StdEncoding.DecodeString("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==")
	placeholder := filepath.Join(outDir, "mock_chart.png")
	if err := os.WriteFile(placeholder, minPNG, 0644); err != nil {
		return nil, err
	}

	return &Meta{Status: "ok", CostMs: 500, Error: ""}, nil
}
