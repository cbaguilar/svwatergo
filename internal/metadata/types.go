package metadata

type SensorMeta struct {
	Key   string `yaml:"key" json:"key"`
	Name  string `yaml:"name" json:"name"`
	Units string `yaml:"units" json:"units,omitempty"`
	Abbr  string `yaml:"abbr" json:"abbr,omitempty"`
}

type SoftSensor struct {
	Key   string `yaml:"key" json:"key"`
	Name  string `yaml:"name" json:"name"`
	Units string `yaml:"units" json:"units,omitempty"`
	Note  string `yaml:"note,omitempty" json:"note,omitempty"`
}

type SiteConfig struct {
	Site        string       `yaml:"site" json:"site"`
	Sensors     []SensorMeta `yaml:"sensors" json:"sensors"`
	SoftSensors []SoftSensor `yaml:"soft_sensors,omitempty" json:"soft_sensors,omitempty"`
}
