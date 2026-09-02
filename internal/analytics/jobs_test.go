package analytics

import (
	"context"
	"path/filepath"
	"testing"

	"github.com/cbaguilar/svwatergo/internal/database"
)

func TestSQLStoreJobLifecycle(t *testing.T) {
	ctx := context.Background()
	dbPath := filepath.Join(t.TempDir(), "analytics.db")
	client, err := database.NewSQLiteClient(dbPath)
	if err != nil {
		t.Fatalf("open sqlite: %v", err)
	}
	defer client.DB.Close()

	store := NewSQLStore(client)
	if err := store.EnsureSchema(ctx); err != nil {
		t.Fatalf("ensure schema: %v", err)
	}

	created, err := store.CreateJob(ctx, JobTypeAudioInference, "bluerock", "tester", map[string]any{"ok": true})
	if err != nil {
		t.Fatalf("create job: %v", err)
	}
	if created.Status != JobStatusQueued {
		t.Fatalf("expected queued, got %s", created.Status)
	}

	running, err := store.MarkRunning(ctx, created.ID)
	if err != nil {
		t.Fatalf("mark running: %v", err)
	}
	if running.StartedAt == nil || running.Status != JobStatusRunning {
		t.Fatalf("expected running with started_at, got %+v", running)
	}

	succeeded, err := store.MarkSucceeded(ctx, created.ID, map[string]any{"label": "positive"})
	if err != nil {
		t.Fatalf("mark succeeded: %v", err)
	}
	if succeeded.FinishedAt == nil || succeeded.Status != JobStatusSucceeded {
		t.Fatalf("expected succeeded with finished_at, got %+v", succeeded)
	}
	if succeeded.Result["label"] != "positive" {
		t.Fatalf("unexpected result: %+v", succeeded.Result)
	}

	got, ok := store.GetJob(ctx, created.ID)
	if !ok {
		t.Fatalf("expected persisted job")
	}
	if got.ID != created.ID || got.Status != JobStatusSucceeded {
		t.Fatalf("unexpected fetched job: %+v", got)
	}

	list := store.ListJobs(ctx, 10, 0)
	if len(list) != 1 || list[0].ID != created.ID {
		t.Fatalf("unexpected job list: %+v", list)
	}
}
