package engine

import (
	"context"
	"encoding/json"
	"os"
	"path/filepath"
)

// Meta Python 脚本返回的执行结果
type Meta struct {
	Status    string `json:"status"`    // "ok" | "error"
	Keypoints int    `json:"keypoints"` // 特征点匹配总数
	CostMs    int64  `json:"cost_ms"`   // 执行耗时（毫秒）
	Error     string `json:"error"`     // 错误信息
}

// AlgorithmEngine 算法引擎统一接口（策略模式）
type AlgorithmEngine interface {
	// Run 执行拼接算法，ctx 由调用方传入（带超时），inputDir 为图片输入目录
	Run(ctx context.Context, inputDir string) (*Meta, error)
	// Name 返回引擎名称，用于日志
	Name() string
}

// writeMetaJSON 将 Meta 写入 result 目录下的 meta.json
func writeMetaJSON(resultDir string, meta *Meta) error {
	data, err := json.MarshalIndent(meta, "", "  ")
	if err != nil {
		return err
	}
	return os.WriteFile(filepath.Join(resultDir, "meta.json"), data, 0644)
}

// ReadMetaJSON 从 result 目录读取 meta.json
func ReadMetaJSON(resultDir string) (*Meta, error) {
	data, err := os.ReadFile(filepath.Join(resultDir, "meta.json"))
	if err != nil {
		return nil, err
	}
	meta := &Meta{}
	if err := json.Unmarshal(data, meta); err != nil {
		return nil, err
	}
	return meta, nil
}
