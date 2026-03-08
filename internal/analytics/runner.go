package analytics

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
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
	InferenceURL   string
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
		InferenceURL:   strings.TrimRight(envOr("ANALYTICS_INFERENCE_SERVICE_URL", ""), "/"),
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
	if strings.TrimSpace(r.InferenceURL) != "" {
		r.runAudioInferenceServiceJob(context.Background(), jobID, req)
		return
	}
	r.runWorkerJob(context.Background(), jobID, workerJobSpec{
		JobID:          jobID,
		JobType:        JobTypeAudioInference,
		AudioInference: &req,
		ArtifactsDir:   filepath.Join(r.ArtifactsRoot, "jobs", jobID),
	})
}

func (r *Runner) runAudioInferenceServiceJob(ctx context.Context, jobID string, req AudioInferenceRequest) {
	if _, err := r.Store.MarkRunning(ctx, jobID); err != nil {
		return
	}
	timeout := r.CommandTimeout
	if timeout <= 0 {
		timeout = 30 * time.Minute
	}
	reqCtx, cancel := context.WithTimeout(ctx, timeout)
	defer cancel()

	u := strings.TrimRight(strings.TrimSpace(r.InferenceURL), "/") + "/api/v1/inference/audio"
	b, err := json.Marshal(req)
	if err != nil {
		_, _ = r.Store.MarkFailed(ctx, jobID, fmt.Errorf("marshal inference request: %w", err), nil)
		return
	}
	httpReq, err := http.NewRequestWithContext(reqCtx, http.MethodPost, u, bytes.NewReader(b))
	if err != nil {
		_, _ = r.Store.MarkFailed(ctx, jobID, fmt.Errorf("build inference request: %w", err), nil)
		return
	}
	httpReq.Header.Set("Content-Type", "application/json")
	resp, err := http.DefaultClient.Do(httpReq)
	if err != nil {
		_, _ = r.Store.MarkFailed(ctx, jobID, fmt.Errorf("inference service request failed: %w", err), nil)
		return
	}
	defer resp.Body.Close()
	body, _ := io.ReadAll(resp.Body)
	var parsed map[string]any
	if len(body) > 0 {
		_ = json.Unmarshal(body, &parsed)
	}
	result := map[string]any{
		"inference_service_url": u,
		"http_status":           resp.StatusCode,
	}
	if parsed != nil {
		result["inference_response"] = parsed
		if p, ok := parsed["payload"]; ok {
			result["worker_result"] = p
		}
		if a, ok := parsed["artifacts"]; ok {
			result["artifacts"] = a
		}
	}
	if resp.StatusCode >= 400 {
		msg := strings.TrimSpace(string(body))
		if msg == "" {
			msg = resp.Status
		}
		_, _ = r.Store.MarkFailed(ctx, jobID, fmt.Errorf("inference service error: %s", msg), result)
		return
	}
	_, _ = r.Store.MarkSucceeded(ctx, jobID, result)
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
