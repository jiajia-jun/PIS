package config

import (
	"os"

	"gopkg.in/yaml.v3"
)

// Config 应用配置
type Config struct {
	DSN    string       // 从环境变量 DATABASE_PATH 读取，非 yaml 字段
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
	Port            int `yaml:"port"`
	UploadMaxSizeMB int `yaml:"upload_max_size_mb"`
}

// WorkerConfig Worker Pool 配置
type WorkerConfig struct {
	PoolSize       int `yaml:"pool_size"`
	TimeoutSeconds int `yaml:"timeout_seconds"`
	CleanupMinutes int `yaml:"cleanup_minutes"`
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

	// 从环境变量读取 MySQL 连接串（在环境变量里面气不气）
	cfg.DSN = os.Getenv("DATABASE_PIS")

	return cfg, nil
}
