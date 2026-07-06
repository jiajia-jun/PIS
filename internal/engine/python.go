package engine

import (
	"context"
	"fmt"
	"os/exec"
)

// PythonEngine 通过 os/exec 调用 Python 脚本执行拼接
type PythonEngine struct {
	PythonPath string // Python 解释器路径
	ScriptPath string // Python 拼接脚本路径
}

func (p *PythonEngine) Name() string { return "python" }

func (p *PythonEngine) Run(ctx context.Context, inputDir string) (*Meta, error) {
	// 命令行: {python_path} {script_path} {inputDir}
	cmd := exec.CommandContext(ctx, p.PythonPath, p.ScriptPath, inputDir)

	output, err := cmd.CombinedOutput()
	if err != nil {
		// 区分超时和其他错误
		if ctx.Err() != nil {
			return nil, fmt.Errorf("Python 执行超时: %w", ctx.Err())
		}
		return nil, fmt.Errorf("Python 执行失败: %w\n输出: %s", err, string(output))
	}

	// 读取 Python 产出的 meta.json
	resultDir := inputDir + "/result"
	meta, err := ReadMetaJSON(resultDir)
	if err != nil {
		return nil, fmt.Errorf("读取 meta.json 失败: %w", err)
	}

	return meta, nil
}
