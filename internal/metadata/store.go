package metadata

import (
	"fmt"
	"os"
	"path/filepath"
	"strings"

	"gopkg.in/yaml.v3"
)

type Store struct {
	Sites map[string]*SiteConfig
}

func LoadDir(dir string) (*Store, error) {
	entries, err := os.ReadDir(dir)
	if err != nil {
		return nil, fmt.Errorf("read dir %s: %w", dir, err)
	}

	store := &Store{Sites: map[string]*SiteConfig{}}
	for _, ent := range entries {
		if ent.IsDir() {
			continue
		}
		name := ent.Name()
		ext := strings.ToLower(filepath.Ext(name))
		if ext != ".yaml" && ext != ".yml" {
			continue
		}

		path := filepath.Join(dir, name)
		raw, err := os.ReadFile(path)
		if err != nil {
			return nil, fmt.Errorf("read file %s: %w", path, err)
		}

		var cfg SiteConfig
		if err := yaml.Unmarshal(raw, &cfg); err != nil {
			return nil, fmt.Errorf("parse yaml %s: %w", path, err)
		}

		key := strings.ToLower(strings.TrimSpace(cfg.Site))
		if key == "" {
			return nil, fmt.Errorf("missing site in %s", path)
		}
		store.Sites[key] = &cfg
	}

	return store, nil
}

func (s *Store) Get(site string) (*SiteConfig, bool) {
	if s == nil {
		return nil, false
	}
	cfg, ok := s.Sites[strings.ToLower(strings.TrimSpace(site))]
	return cfg, ok
}
