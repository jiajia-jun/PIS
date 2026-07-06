package handler

import (
	"net/http"
	"os"
	"path/filepath"

	"github.com/gin-gonic/gin"
)

// AnalysisHandler 分析图表处理器
type AnalysisHandler struct {
	analysisDir string
}

// NewAnalysisHandler 创建 AnalysisHandler
func NewAnalysisHandler(analysisDir string) *AnalysisHandler {
	return &AnalysisHandler{analysisDir: analysisDir}
}

// GetAnalysis 返回分析图表 PNG 文件 GET /api/analysis/:task_id/:filename
func (h *AnalysisHandler) GetAnalysis(c *gin.Context) {
	taskID := c.Param("task_id")
	filename := c.Param("filename")

	if taskID == "" || filename == "" {
		c.JSON(http.StatusBadRequest, gin.H{"code": 400, "message": "缺少参数"})
		return
	}

	filePath := filepath.Join(h.analysisDir, taskID, filename)
	if _, err := os.Stat(filePath); os.IsNotExist(err) {
		c.JSON(http.StatusNotFound, gin.H{"code": 404, "message": "分析文件不存在"})
		return
	}

	c.File(filePath)
}
