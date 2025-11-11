package systemservice

type Registry interface {
	Get(site string) (SystemManager, bool)
	Sites() []string
}

type MapRegistry struct{ m map[string]SystemManager }

func NewRegistry(m map[string]SystemManager) *MapRegistry { return &MapRegistry{m: m} }

func (r *MapRegistry) Get(site string) (SystemManager, bool) { return r.m[site] }

func (r *MapRegistry) Sites() []string {
	out := make([]string, 0, len(r.m))
	for k := range r.m {
		out = append(out, k)
	}
	return out
}
