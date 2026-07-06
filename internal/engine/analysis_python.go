package engine

import (
	"context"
	"fmt"
	"os/exec"
)

// PythonAnalysisEngine 通过 os/exec 调用 Python 分析脚本
type PythonAnalysisEngine struct {
	PythonPath string
	ScriptPath string
}

func (p *PythonAnalysisEngine) Name() string { return "python-analysis" }

func (p *PythonAnalysisEngine) Run(ctx context.Context, taskDir string) (*Meta, error) {
	// 命令行: {python_path} {script_path} {taskDir}
	cmd := exec.CommandContext(ctx, p.PythonPath, p.ScriptPath, taskDir)

	output, err := cmd.CombinedOutput()
	if err != nil {
		if ctx.Err() != nil {
			return nil, fmt.Errorf("分析脚本执行超时: %w", ctx.Err())
		}
		return nil, fmt.Errorf("分析脚本执行失败: %w\n输出: %s", err, string(output))
	}

	return &Meta{Status: "ok", Error: ""}, nil
}
