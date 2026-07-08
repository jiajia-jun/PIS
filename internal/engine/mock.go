package engine

import (
	"context"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"time"
)

// MockEngine 模拟引擎，用于开发测试，不依赖 Python 环境
type MockEngine struct{}

func (m *MockEngine) Name() string { return "mock" }

func (m *MockEngine) Run(ctx context.Context, taskDir string) (*Meta, error) {
	// 模拟拼接耗时
	select {
	case <-time.After(1 * time.Second):
	case <-ctx.Done():
		return nil, ctx.Err()
	}

	inputDir := filepath.Join(taskDir, "input")
	resultDir := filepath.Join(taskDir, "result")

	// 取 input 目录第一张图，复制为 result.jpg，模拟完整链路
	inputFiles, err := os.ReadDir(inputDir)
	if err != nil {
		return nil, fmt.Errorf("读取上传图片失败: %w", err)
	}

	var copied bool
	for _, f := range inputFiles {
		if !f.IsDir() && isImageExt(f.Name()) {
			src := filepath.Join(inputDir, f.Name())
			dst := filepath.Join(resultDir, "result.jpg")
			if err := copyFile(src, dst); err != nil {
				return nil, fmt.Errorf("生成结果图失败: %w", err)
			}
			copied = true
			break
		}
	}

	if !copied {
		return nil, fmt.Errorf("上传目录中未找到图片文件")
	}

	// 写入 meta.json
	meta := &Meta{
		Status:    "ok",
		Keypoints: 150,
		CostMs:    1000,
		Error:     "",
	}
	if err := writeMetaJSON(resultDir, meta); err != nil {
		return nil, err
	}

	return meta, nil
}

// isImageExt 判断是否为图片后缀（大小写不敏感）
func isImageExt(name string) bool {
	ext := filepath.Ext(name)
	switch ext {
	case ".jpg", ".jpeg", ".png", ".JPG", ".JPEG", ".PNG":
		return true
	}
	return false
}

// copyFile 复制文件
func copyFile(src, dst string) error {
	s, err := os.Open(src)
	if err != nil {
		return err
	}
	defer s.Close()

	d, err := os.Create(dst)
	if err != nil {
		return err
	}
	defer d.Close()

	_, err = io.Copy(d, s)
	return err
}
