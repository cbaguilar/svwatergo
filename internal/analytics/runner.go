package analytics

import (
	"context"
	"encoding/json"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"time"
)

type Runner struct {
	Store          *Store
	PythonBin      string
	WorkerScript   string
	ArtifactsRoot  string
	ExtraEnv       []string
	CommandTimeout time.Duration
}

type workerJobSpec struct {
	JobID          string                   `json:"job_id"`
	JobType        JobType                  `json:"job_type"`
	FeatureRun     *FeatureRunRequest       `json:"feature_run,omitempty"`
	PCARun         *PCARunRequest           `json:"pca_run,omitempty"`
	AudioAlignPLC  *AudioAlignPLCRunRequest `json:"audio_align_plc,omitempty"`
	AudioInference *AudioInferenceRequest   `json:"audio_inference,omitempty"`
	ArtifactsDir   string                   `json:"artifacts_dir"`
}

func NewRunner(store *Store) *Runner {
	return &Runner{
		Store:          store,
		PythonBin:      envOr("ANALYTICS_PYTHON_BIN", "python3"),
		WorkerScript:   envOr("ANALYTICS_WORKER_SCRIPT", filepath.Join("python", "analytics", "worker_main.py")),
		ArtifactsRoot:  envOr("ANALYTICS_ARTIFACTS_ROOT", filepath.Join("data", "analytics")),
		CommandTimeout: 30 * time.Minute,
	}
}

func (r *Runner) EnqueueFeature(ctx context.Context, req FeatureRunRequest, createdBy string) (Job, error) {
	if r == nil || r.Store == nil {
		return Job{}, fmt.Errorf("analytics runner not configured")
	}
	job, err := r.Store.CreateJob(ctx, JobTypeFeatureEngineering, req.Site, createdBy, req)
	if err != nil {
		return Job{}, err
	}
	go r.runFeatureJob(job.ID, req)
	return job, nil
}

func (r *Runner) EnqueuePCA(ctx context.Context, req PCARunRequest, createdBy string) (Job, error) {
	if r == nil || r.Store == nil {
		return Job{}, fmt.Errorf("analytics runner not configured")
	}
	job, err := r.Store.CreateJob(ctx, JobTypePCA, req.Site, createdBy, req)
	if err != nil {
		return Job{}, err
	}
	go r.runPCAJob(job.ID, req)
	return job, nil
}

func (r *Runner) EnqueueAudioAlignPLC(ctx context.Context, req AudioAlignPLCRunRequest, createdBy string) (Job, error) {
	if r == nil || r.Store == nil {
		return Job{}, fmt.Errorf("analytics runner not configured")
	}
	job, err := r.Store.CreateJob(ctx, JobTypeAudioAlignPLC, req.Site, createdBy, req)
	if err != nil {
		return Job{}, err
	}
	go r.runAudioAlignPLCJob(job.ID, req)
	return job, nil
}

func (r *Runner) EnqueueAudioInference(ctx context.Context, req AudioInferenceRequest, createdBy string) (Job, error) {
	if r == nil || r.Store == nil {
		return Job{}, fmt.Errorf("analytics runner not configured")
	}
	job, err := r.Store.CreateJob(ctx, JobTypeAudioInference, req.Site, createdBy, req)
	if err != nil {
		return Job{}, err
	}
	go r.runAudioInferenceJob(job.ID, req)
	return job, nil
}

func (r *Runner) runFeatureJob(jobID string, req FeatureRunRequest) {
	r.runWorkerJob(context.Background(), jobID, workerJobSpec{
		JobID:        jobID,
		JobType:      JobTypeFeatureEngineering,
		FeatureRun:   &req,
		ArtifactsDir: filepath.Join(r.ArtifactsRoot, "jobs", jobID),
	})
}

func (r *Runner) runPCAJob(jobID string, req PCARunRequest) {
	r.runWorkerJob(context.Background(), jobID, workerJobSpec{
		JobID:        jobID,
		JobType:      JobTypePCA,
		PCARun:       &req,
		ArtifactsDir: filepath.Join(r.ArtifactsRoot, "jobs", jobID),
	})
}

func (r *Runner) runAudioAlignPLCJob(jobID string, req AudioAlignPLCRunRequest) {
	r.runWorkerJob(context.Background(), jobID, workerJobSpec{
		JobID:         jobID,
		JobType:       JobTypeAudioAlignPLC,
		AudioAlignPLC: &req,
		ArtifactsDir:  filepath.Join(r.ArtifactsRoot, "jobs", jobID),
	})
}

func (r *Runner) runAudioInferenceJob(jobID string, req AudioInferenceRequest) {
	r.runWorkerJob(context.Background(), jobID, workerJobSpec{
		JobID:          jobID,
		JobType:        JobTypeAudioInference,
		AudioInference: &req,
		ArtifactsDir:   filepath.Join(r.ArtifactsRoot, "jobs", jobID),
	})
}

func (r *Runner) runWorkerJob(ctx context.Context, jobID string, spec workerJobSpec) {
	if _, err := r.Store.MarkRunning(ctx, jobID); err != nil {
		return
	}
	timeout := r.CommandTimeout
	if timeout <= 0 {
		timeout = 30 * time.Minute
	}
	cmdCtx, cancel := context.WithTimeout(ctx, timeout)
	defer cancel()

	jobDir := spec.ArtifactsDir
	if err := os.MkdirAll(jobDir, 0o755); err != nil {
		_, _ = r.Store.MarkFailed(ctx, jobID, fmt.Errorf("create job dir: %w", err), nil)
		return
	}

	specPath := filepath.Join(jobDir, "job_spec.json")
	resultPath := filepath.Join(jobDir, "result.json")
	if err := writeJSONFile(specPath, spec); err != nil {
		_, _ = r.Store.MarkFailed(ctx, jobID, fmt.Errorf("write job spec: %w", err), nil)
		return
	}

	cmd := exec.CommandContext(cmdCtx, r.PythonBin, r.WorkerScript, "--job-spec", specPath, "--result", resultPath)
	cmd.Env = append(os.Environ(), r.ExtraEnv...)
	cmd.Dir = "."
	out, err := cmd.CombinedOutput()

	result := map[string]any{
		"artifacts_dir": jobDir,
		"worker": map[string]any{
			"python_bin":    r.PythonBin,
			"worker_script": r.WorkerScript,
			"result_path":   resultPath,
		},
	}
	if txt := strings.TrimSpace(string(out)); txt != "" {
		result["worker_output"] = txt
	}

	if parsed, parseErr := readJSONMap(resultPath); parseErr == nil && parsed != nil {
		result["worker_result"] = parsed
		if arts, ok := parsed["artifacts"]; ok {
			result["artifacts"] = arts
		}
	}

	if err != nil {
		_, _ = r.Store.MarkFailed(ctx, jobID, fmt.Errorf("worker failed: %w", err), result)
		return
	}
	_, _ = r.Store.MarkSucceeded(ctx, jobID, result)
}

func writeJSONFile(path string, v any) error {
	b, err := json.MarshalIndent(v, "", "  ")
	if err != nil {
		return err
	}
	b = append(b, '\n')
	return os.WriteFile(path, b, 0o644)
}

func readJSONMap(path string) (map[string]any, error) {
	b, err := os.ReadFile(path)
	if err != nil {
		return nil, err
	}
	var out map[string]any
	if err := json.Unmarshal(b, &out); err != nil {
		return nil, err
	}
	return out, nil
}

func envOr(key, fallback string) string {
	if v := strings.TrimSpace(os.Getenv(key)); v != "" {
		return v
	}
	return fallback
}
