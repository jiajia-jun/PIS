package engine

import (
	"context"
	"fmt"
)

// CppEngine C++ 引擎占位，后续扩展
type CppEngine struct {
	BinaryPath string // C++ 可执行文件路径
}

func (c *CppEngine) Name() string { return "cpp" }

func (c *CppEngine) Run(ctx context.Context, inputDir string) (*Meta, error) {
	// TODO: 实现 C++ 调用逻辑
	return nil, fmt.Errorf("c++引擎待开发")
}
