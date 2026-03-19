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
	Site               string       `yaml:"site" json:"site"`
	DisplayName        string       `yaml:"display_name,omitempty" json:"display_name,omitempty"`
	FormalName         string       `yaml:"formal_name,omitempty" json:"formal_name,omitempty"`
	AlertStreetAddr    string       `yaml:"alert_street_addr,omitempty" json:"alert_street_addr,omitempty"`
	StateWaterSystemID string       `yaml:"state_water_system_id,omitempty" json:"state_water_system_id,omitempty"`
	AlertContactNames  string       `yaml:"alert_contact_names,omitempty" json:"alert_contact_names,omitempty"`
	AlertContactPhone  string       `yaml:"alert_contact_phone,omitempty" json:"alert_contact_phone,omitempty"`
	Sensors            []SensorMeta `yaml:"sensors" json:"sensors"`
	SoftSensors        []SoftSensor `yaml:"soft_sensors,omitempty" json:"soft_sensors,omitempty"`
}
