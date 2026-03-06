package analytics

import (
	"fmt"
	"strings"
)

type AudioInferenceRequest struct {
	Site      string                    `json:"site,omitempty"`
	Model     AudioInferenceModel       `json:"model"`
	Outputs   AudioInferenceOutputs     `json:"outputs,omitempty"`
	Batch     AudioInferenceBatch       `json:"batch,omitempty"`
	Execution AudioInferenceExecution   `json:"execution,omitempty"`
	Inputs    []AudioInferenceInputItem `json:"inputs"`
	Tags      map[string]string         `json:"tags,omitempty"`
}

type AudioInferenceModel struct {
	ModelID   string `json:"model_id,omitempty"`
	Version   string `json:"version,omitempty"`
	ModelPath string `json:"model_path,omitempty"`
	ModelURI  string `json:"model_uri,omitempty"`
	ModelKind string `json:"model_kind,omitempty"` // auto | tiny_cnn | pca_svm
}

type AudioInferenceOutputs struct {
	Predictions bool `json:"predictions,omitempty"`
	Embeddings  bool `json:"embeddings,omitempty"`
	Metadata    bool `json:"metadata,omitempty"`
}

type AudioInferenceBatch struct {
	Mode     string `json:"mode,omitempty"` // sync | async
	MaxItems int    `json:"max_items,omitempty"`
}

type AudioInferenceExecution struct {
	DeviceHint string `json:"device_hint,omitempty"` // auto | cpu | cuda
	TimeoutSec int    `json:"timeout_sec,omitempty"`
}

type AudioInferenceInputItem struct {
	InputID   string `json:"input_id"`
	Type      string `json:"type"` // upload | s3_uri | local_path | staged_ref
	URI       string `json:"uri,omitempty"`
	Path      string `json:"path,omitempty"`
	StagedRef string `json:"staged_ref,omitempty"`
}

func (r *AudioInferenceRequest) Normalize() {
	r.Site = strings.ToLower(strings.TrimSpace(r.Site))
	r.Model.ModelID = strings.TrimSpace(r.Model.ModelID)
	r.Model.Version = strings.TrimSpace(r.Model.Version)
	r.Model.ModelPath = strings.TrimSpace(r.Model.ModelPath)
	r.Model.ModelURI = strings.TrimSpace(r.Model.ModelURI)
	r.Model.ModelKind = strings.ToLower(strings.TrimSpace(r.Model.ModelKind))
	r.Batch.Mode = strings.ToLower(strings.TrimSpace(r.Batch.Mode))
	r.Execution.DeviceHint = strings.ToLower(strings.TrimSpace(r.Execution.DeviceHint))
	for i := range r.Inputs {
		r.Inputs[i].InputID = strings.TrimSpace(r.Inputs[i].InputID)
		r.Inputs[i].Type = strings.ToLower(strings.TrimSpace(r.Inputs[i].Type))
		r.Inputs[i].URI = strings.TrimSpace(r.Inputs[i].URI)
		r.Inputs[i].Path = strings.TrimSpace(r.Inputs[i].Path)
		r.Inputs[i].StagedRef = strings.TrimSpace(r.Inputs[i].StagedRef)
	}
	if r.Batch.Mode == "" {
		r.Batch.Mode = "async"
	}
	if r.Batch.MaxItems <= 0 {
		r.Batch.MaxItems = 512
	}
	if r.Execution.DeviceHint == "" {
		r.Execution.DeviceHint = "auto"
	}
	if r.Model.ModelKind == "" {
		r.Model.ModelKind = "auto"
	}
	// Default response payload includes predictions + metadata.
	if !r.Outputs.Predictions && !r.Outputs.Embeddings && !r.Outputs.Metadata {
		r.Outputs.Predictions = true
		r.Outputs.Metadata = true
	}
}

func (r AudioInferenceRequest) Validate() error {
	if strings.TrimSpace(r.Model.ModelID) == "" && strings.TrimSpace(r.Model.ModelPath) == "" && strings.TrimSpace(r.Model.ModelURI) == "" {
		return fmt.Errorf("provide model.model_id or model.model_path/model.model_uri")
	}
	if len(r.Inputs) == 0 {
		return fmt.Errorf("inputs required")
	}
	if r.Batch.Mode != "sync" && r.Batch.Mode != "async" {
		return fmt.Errorf("batch.mode must be sync or async")
	}
	if r.Batch.MaxItems <= 0 || r.Batch.MaxItems > 10000 {
		return fmt.Errorf("batch.max_items must be between 1 and 10000")
	}
	if len(r.Inputs) > r.Batch.MaxItems {
		return fmt.Errorf("inputs exceeds batch.max_items")
	}
	if r.Execution.DeviceHint != "auto" && r.Execution.DeviceHint != "cpu" && r.Execution.DeviceHint != "cuda" {
		return fmt.Errorf("execution.device_hint must be auto|cpu|cuda")
	}
	if r.Model.ModelKind != "auto" && r.Model.ModelKind != "tiny_cnn" && r.Model.ModelKind != "pca_svm" {
		return fmt.Errorf("model.model_kind must be auto|tiny_cnn|pca_svm")
	}
	seen := make(map[string]struct{}, len(r.Inputs))
	for i, in := range r.Inputs {
		if in.InputID == "" {
			return fmt.Errorf("inputs[%d].input_id required", i)
		}
		if _, ok := seen[in.InputID]; ok {
			return fmt.Errorf("duplicate input_id: %s", in.InputID)
		}
		seen[in.InputID] = struct{}{}
		switch in.Type {
		case "upload":
			// Upload payload is staged separately and referenced via staged_ref.
			if in.StagedRef == "" {
				return fmt.Errorf("inputs[%d].staged_ref required for type=upload", i)
			}
		case "s3_uri":
			if in.URI == "" {
				return fmt.Errorf("inputs[%d].uri required for type=s3_uri", i)
			}
		case "local_path":
			if in.Path == "" {
				return fmt.Errorf("inputs[%d].path required for type=local_path", i)
			}
		case "staged_ref":
			if in.StagedRef == "" {
				return fmt.Errorf("inputs[%d].staged_ref required for type=staged_ref", i)
			}
		default:
			return fmt.Errorf("inputs[%d].type unsupported: %s", i, in.Type)
		}
	}
	return nil
}
