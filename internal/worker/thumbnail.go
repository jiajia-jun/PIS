package worker

import (
	"fmt"
	"os"

	"pisweb/internal/tool"
)

// generateThumbnail 从 result.jpg 生成缩略图存入 thumb.jpg
func generateThumbnail(srcPath, dstPath string) error {
	src, err := os.Open(srcPath)
	if err != nil {
		return fmt.Errorf("打开原图失败: %w", err)
	}
	defer src.Close()

	dst, err := os.Create(dstPath)
	if err != nil {
		return fmt.Errorf("创建缩略图失败: %w", err)
	}
	defer dst.Close()

	return tool.ResizeToJPEG(src, dst, tool.ThumbnailWidth)
}
