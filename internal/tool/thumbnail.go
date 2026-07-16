package tool

import (
	"image"
	"image/jpeg"
	"io"

	"github.com/disintegration/imaging"
)

const ThumbnailWidth = 800

// ResizeToJPEG 从 reader 读取图片，缩放到指定宽度，以 JPEG 格式写入 writer（纯内存操作，不落盘）
func ResizeToJPEG(src io.Reader, dst io.Writer, width int) error {
	img, _, err := image.Decode(src)
	if err != nil {
		return err
	}

	// 兰索斯算法
	thumb := imaging.Resize(img, width, 0, imaging.Lanczos)

	return jpeg.Encode(dst, thumb, &jpeg.Options{Quality: 85})
}
