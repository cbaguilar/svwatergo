package datamodels

/*
 remote system data model, generic that
 can be inherited by any remote system
*/

// RemoteSystemState defines the state of a remote system
type RemoteSystemState struct {
	Location   string `json:"location"`
	PLCtime    string `json:"plctime"`
	RecordTime string `json:"recordtime"`

	// Flow Measurements
	TotalROFlow     int64   `json:"totalroflow"`
	TotalDelFlow    int64   `json:"totaldelflow"`
	PermeateFlow    float64 `json:"permeateflow"`
	DeliveryFlow    float64 `json:"deliveryflow"`
	ConcentrateFlow float64 `json:"concentrateflow"`
	RecycleFlow     float64 `json:"recycleflow"`

	// Tank Measurements
	FeedTankLevel   float64 `json:"feedtanklevel"`
	ProdTankLevel   float64 `json:"prodtanklevel"`
	ProdTankDisable bool    `json:"prodtankdisable"`
	ProdTankDepth   float64 `json:"prodtankdepth"`

	// Pressure Measurements
	InletPressure       float64 `json:"inletpressure"`
	ConcentratePressure float64 `json:"concentratepressure"`
	PermeatePressure    float64 `json:"permeatepressure"`
	ROPressure          float64 `json:"ropressure"`
	DeliveryPressure    float64 `json:"deliverypressure"`
	FeedPressure        float64 `json:"feedpressure"`

	// Operational States
	DumpProduct      bool `json:"dumpproduct"`
	WellPumpRun      bool `json:"wellpumprun"`
	WellPumpAuto     bool `json:"wellpumpauto"`
	FeedPumpRun      bool `json:"feedpumprun"`
	ROPumpRun        bool `json:"ropumprun"`
	DeliveryRun      bool `json:"deliveryrun"`
	DeliveryAuto     bool `json:"deliveryauto"`
	ConcBypassRun    bool `json:"concbypassrun"`
	ProdDiversionRun bool `json:"proddiversionrun"`
	FlushRun         bool `json:"flushrun"`
	ROStandby        bool `json:"rostandby"`
	Lockout          bool `json:"lockout"`

	// Alarms and Warnings
	Alarm     bool  `json:"alarm"`
	AlarmWord int64 `json:"alarmword"`
	WarnWord0 int64 `json:"warnword0"`
	WarnWord1 int64 `json:"warnword1"`

	// Diagnostics
	State      int64 `json:"state"`
	TotalHrs   int64 `json:"totalhrs"`
	PowerMeter int64 `json:"powermeter"`

	// Water Quality
	PermTDS     float64 `json:"permtds"`
	FeedTDS     float64 `json:"feedtds"`
	PermNitrate float64 `json:"permnitrate"`
	PermTemp    float64 `json:"permtemp"`
	ProductTDS  float64 `json:"producttds"`
}
