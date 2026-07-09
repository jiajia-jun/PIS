package config

import (
	"os"
	"strings"

	"gopkg.in/yaml.v3"
)

// Config 应用配置
type Config struct {
	DSN    string       // 从环境变量 DATABASE_PIS 读取，非 yaml 字段
	Engine EngineConfig `yaml:"engine"`
	Server ServerConfig `yaml:"server"`
	Worker WorkerConfig `yaml:"worker"`
	Store  StoreConfig  `yaml:"store"`
}

// EngineConfig 算法引擎配置
type EngineConfig struct {
	StitchType         string `yaml:"stitch_type"`
	AnalysisType       string `yaml:"analysis_type"`
	PythonPath         string `yaml:"python_path"`
	StitchScriptPath   string `yaml:"stitch_script_path"`
	AnalysisScriptPath string `yaml:"analysis_script_path"`
	CppBinary          string `yaml:"cpp_binary"`
}

// ServerConfig HTTP 服务器配置
type ServerConfig struct {
	Host            string `yaml:"host"` // 监听地址，空字符串=监听所有接口
	Port            int    `yaml:"port"`
	UploadMaxSizeMB int    `yaml:"upload_max_size_mb"`
}

// WorkerConfig Worker Pool 配置
type WorkerConfig struct {
	PoolSize       int `yaml:"pool_size"`
	TimeoutSeconds int `yaml:"timeout_seconds"`
}

// StoreConfig 存储路径配置
type StoreConfig struct {
	UploadDir   string `yaml:"upload_dir"`
	AnalysisDir string `yaml:"analysis_dir"`
}

// Load 从文件路径加载配置
func Load(path string) (*Config, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		return nil, err
	}

	cfg := &Config{}
	if err := yaml.Unmarshal(data, cfg); err != nil {
		return nil, err
	}

	// 从环境变量读取 MySQL 连接串
	cfg.DSN = os.Getenv("DATABASE_PIS")

	// 自动补全时区参数：未指定 loc 时默认使用本地时区，避免时间偏移 8 小时
	if !strings.Contains(cfg.DSN, "loc=") {
		cfg.DSN += "&loc=Local"
	}

	return cfg, nil
}
