package middleware

import (
	"net/http"

	"github.com/gin-gonic/gin"
)

// BodyLimit 请求体大小限制中间件
func BodyLimit(maxSizeMB int) gin.HandlerFunc {
	maxSizeBytes := int64(maxSizeMB) * 1024 * 1024
	return func(c *gin.Context) {
		if c.Request.ContentLength > maxSizeBytes {
			c.AbortWithStatusJSON(http.StatusRequestEntityTooLarge, gin.H{
				"code":    413,
				"message": "图像不得大于50MB",
			})
			return
		}
		c.Request.Body = http.MaxBytesReader(c.Writer, c.Request.Body, maxSizeBytes)
		c.Next()
	}
}
