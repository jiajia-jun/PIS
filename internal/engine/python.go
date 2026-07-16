package engine

import (
	"context"
	"fmt"
	"os/exec"
	"path/filepath"
	"strings"
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
		if ctx.Err() != nil {
			return nil, fmt.Errorf("图像处理超时，请稍后重试")
		}
		// 只取最后一行的实际错误信息，丢弃 traceback 堆栈
		msg := sanitizePythonError(string(output))
		return nil, fmt.Errorf("图像处理异常: %s", msg)
	}

	resultDir := filepath.Join(inputDir, "result")
	meta, err := ReadMetaJSON(resultDir)
	if err != nil {
		return nil, fmt.Errorf("读取处理结果失败，请稍后重试")
	}

	return meta, nil
}

// sanitizePythonError 提取 Python stderr 中最后一行有意义的信息，丢弃 traceback 堆栈
func sanitizePythonError(raw string) string {
	lines := strings.Split(strings.TrimSpace(raw), "\n")
	// 从最后一行往前找第一个非空且不包含 "File " 的行
	for i := len(lines) - 1; i >= 0; i-- {
		line := strings.TrimSpace(lines[i])
		if line == "" {
			continue
		}
		// 跳过 traceback 的 "File ..." 行和 "Traceback" 行
		if strings.HasPrefix(line, "File ") || strings.HasPrefix(line, "Traceback") {
			continue
		}
		return line
	}
	// 兜底：返回最后一行非空内容
	if len(lines) > 0 {
		return lines[len(lines)-1]
	}
	return raw
}
