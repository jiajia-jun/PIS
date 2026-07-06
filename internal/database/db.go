package database

import (
	"fmt"
	"pisweb/internal/model"

	"gorm.io/driver/mysql"
	"gorm.io/gorm"
)

var DB *gorm.DB

// Init 初始化 MySQL 连接并自动建表
func Init(dsn string) error {
	var err error
	DB, err = gorm.Open(mysql.Open(dsn), &gorm.Config{})
	if err != nil {
		return fmt.Errorf("数据库连接失败: %w", err)
	}

	if err := DB.AutoMigrate(&model.Task{}); err != nil {
		return fmt.Errorf("自动建表失败: %w", err)
	}

	return nil
}
