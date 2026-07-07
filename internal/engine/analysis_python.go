package engine

import (
	"context"
	"fmt"
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
