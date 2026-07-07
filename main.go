package main

import (
	"log"

	"pisweb/internal/app"
)

func main() {
	application, err := app.New("config.yaml")
	if err != nil {
		log.Fatalf("初始化失败: %v", err)
	}
	application.Run()
}
