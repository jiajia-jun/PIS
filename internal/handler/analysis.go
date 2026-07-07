package handler

import (
	"net/http"
	"os"
	"path/filepath"
	"sort"
	"strings"

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

// listChartFiles 扫描分析目录，返回该任务的 PNG 图表 URL 列表
func listChartFiles(analysisDir, taskID string) []string {
	return listFilesByExt(analysisDir, taskID, ".png")
}

// listTableFiles 扫描分析目录，返回该任务的 JSON 表格 URL 列表
func listTableFiles(analysisDir, taskID string) []string {
	return listFilesByExt(analysisDir, taskID, ".json")
}

// listFilesByExt 扫描分析目录，按扩展名过滤文件并返回 API URL 列表
func listFilesByExt(analysisDir, taskID, ext string) []string {
	dir := filepath.Join(analysisDir, taskID)
	entries, err := os.ReadDir(dir)
	if err != nil {
		return nil
	}

	var urls []string
	for _, e := range entries {
		if !e.IsDir() && strings.EqualFold(filepath.Ext(e.Name()), ext) {
			urls = append(urls, "/api/analysis/"+taskID+"/"+e.Name())
		}
	}
	sort.Strings(urls)
	return urls
}
