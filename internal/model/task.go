package model

import (
	"time"

	"github.com/google/uuid"
	"gorm.io/gorm"
)

// 任务状态常量
const (
	StatusPending    = "pending"
	StatusProcessing = "processing"
	StatusCompleted  = "completed"
	StatusFailed     = "failed"
)

// Task 拼接任务模型
type Task struct {
	ID         string    `gorm:"primaryKey;size:36" json:"task_id"`
	Status     string    `gorm:"size:20;index;default:pending" json:"status"`
	CostMs     int64     `gorm:"default:0" json:"cost_ms"`
	Keypoints  int       `gorm:"default:0" json:"keypoints"`
	ErrorMsg   string    `gorm:"size:500" json:"-"`
	ImageCount int       `gorm:"default:0" json:"image_count"`
	ResultPath string    `gorm:"size:255" json:"-"`
	CreatedAt  time.Time `json:"created_at"`
	UpdatedAt  time.Time `json:"updated_at"`
}

// BeforeCreate GORM 钩子：创建前自动生成 UUID
func (t *Task) BeforeCreate(tx *gorm.DB) error {
	if t.ID == "" {
		t.ID = uuid.New().String()
	}
	return nil
}
