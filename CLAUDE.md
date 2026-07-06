# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

PIS-web (Panoramic Image Stitching) is a Go web backend for a panoramic image stitching system. Users upload multiple overlapping images via a web frontend; the backend processes them asynchronously and returns a stitched panorama, with history browsing.

## Commands

```bash
# Run the application
go run .

# Build
go build -o pis-web .

# Run all tests
go test ./...

# Run tests for a specific package
go test ./internal/engine/...
```

## Tech Stack & Conventions

- **Go 1.25.5** with Go modules
- **Gin** for HTTP routing and handlers
- **GORM** + MySQL for persistence
- **Redis** (planned, deferred — use in-memory storage initially)
- Configuration via `config.yaml`
- GoLand (IntelliJ) as IDE — workspace configured in `.idea/`

## Architecture (Planned)

The project follows a layered architecture with the Strategy pattern for swappable algorithm engines:

```
cmd/server/ or main.go     Entry point — config loading, DB init, router setup, worker pool startup
internal/
  handler/                  Gin HTTP handlers (upload, task status polling, history)
  service/                  Business logic layer
  model/                    GORM data models (Task, etc.)
  engine/                   Algorithm engine interface + implementations (Mock, Python, C++)
  worker/                   Fixed-size goroutine worker pool consuming from a task channel
  middleware/               Gin middleware (file size limit, etc.)
  config/                   config.yaml loader
  imaging/                  Image processing utilities (WebP conversion, thumbnail generation)
store/uploads/              Uploaded image storage (organized by task_id)
store/analysis/             Data analysis results stored as JSON files
```

### Strategy Pattern — AlgorithmEngine

The core design constraint: the image stitching engine must use the **Strategy Pattern** with a unified `AlgorithmEngine` interface. Three implementations are required, selectable via `config.yaml`:

| Engine | Purpose |
|---|---|
| `MockEngine` | Returns fake results for testing/development without Python |
| `PythonEngine` | Calls Python stitching scripts via `os/exec` |
| `CppEngine` | Calls C++ binaries via `os/exec` |

### Go ↔ Python IPC Protocol

Communication is **file-system + JSON only** — no base64, no complex objects through stdin/stdout:

- **Input**: Go saves uploaded images to `./store/uploads/{task_id}/`, passes the directory path to Python as a CLI argument.
- **Output**: Python writes two files into the same directory:
  - `meta.json` — `{status, keypoints, cost_ms, error}`
  - `result.jpg` — the stitched output image
- Go workers parse `meta.json` and update the database.

### Optimizations

- **Binary stream transfer**: Images are transferred as binary streams (not Base64).
- **WebP storage**: Uploaded images should be converted to WebP format for storage efficiency. Implemented in a dedicated `internal/imaging/` package.
- **Thumbnail preloading**: Use the `imaging` library to generate thumbnails for fast preview. Thumbnails are served on first load and replaced by the full-resolution original image after. Originals **must** be preserved; thumbnails are discarded after use. Implemented in `internal/imaging/`.

### Data Analysis

Analysis data is stored as JSON files under `./store/analysis/`. An API endpoint serves this data for frontend visualization (charts, statistics about stitching tasks).

### Worker Pool

- Fixed size of **3 goroutines** consuming from a buffered channel (prevents OOM from too many concurrent Python processes).
- Each Python call is wrapped with `context.WithTimeout(30s)`.
- On timeout or error, the worker records the error message in the DB — the Go server must **not crash**.

### Constraints

- Upload file size limit: **50 MB**
- Upload files are auto-cleaned **10 minutes after task completion** via `time.AfterFunc`
- Task status is exposed via a polling endpoint (`GET /api/task/:task_id`) — the frontend polls for completion

### API Endpoints (Planned)

| Method | Path | Purpose |
|---|---|---|
| POST | `/api/upload` | Upload multiple images, returns `task_id` |
| GET | `/api/task/:task_id` | Poll task status and result |
| GET | `/api/history?page=&size=` | Paginated task history |
| GET | `/api/analysis` | Data analysis results (reads JSON from `store/analysis/`) |

## Current State

**Project is not yet initialized** — only `taget.md` (requirements) and `.idea/` (IDE config) exist. No `go.mod`, no source files, no directory structure. The requirements document lives at `taget.md` (note: filename is misspelled "taget" instead of "target").

## Sibling Projects

Several Go+Gin projects exist in the parent `Go_Project/` directory that can serve as reference for patterns and conventions:
- `Gallery/` — Gin + GORM + MySQL + JWT auth (most structurally relevant)
- `WebProject_demo/` — Gin with JSON-file persistence and JWT
- `WebProject/` — Simpler Gin web app
