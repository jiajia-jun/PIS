package engine

import (
	"context"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
)

type PythonAnalysisEngine struct {
	PythonPath  string
	ScriptPath  string
	AnalysisDir string
}

func (p *PythonAnalysisEngine) Name() string { return "python-analysis" }

func (p *PythonAnalysisEngine) Run(ctx context.Context, taskDir string) (*Meta, error) {
	taskID := filepath.Base(taskDir)
	analysisDir := filepath.Join(p.AnalysisDir, taskID)

	// 后端创建分析输出目录，Python 脚本直接写入即可
	if err := os.MkdirAll(analysisDir, 0755); err != nil {
		return nil, fmt.Errorf("创建分析目录失败: %w", err)
	}

	// 命令行: {python} {script} {taskDir} {analysisDir}
	cmd := exec.CommandContext(ctx, p.PythonPath, p.ScriptPath, taskDir, analysisDir)

	output, err := cmd.CombinedOutput()
	if err != nil {
		if ctx.Err() != nil {
			return nil, fmt.Errorf("analysis timeout: %w", ctx.Err())
		}
		return nil, fmt.Errorf("analysis failed: %w\noutput: %s", err, string(output))
	}

	return &Meta{Status: "ok", Error: ""}, nil
}
