package bluerock

import "time"

type BluerockState struct {
	Location                 string    `json:"location"`
	TotalROFlow              int64     `json:"totalroflow"`
	TotalFeedFlow            int64     `json:"totalfeedflow"`
	TotalRecycleFlow         int64     `json:"totalrecycleflow"`
	TotalDelFlow             int64     `json:"totaldelflow"`
	DumpProduct              bool      `json:"dumpproduct"`
	WellPumpRun              bool      `json:"wellpumprun"`
	WellPumpAuto             bool      `json:"wellpumpauto"`
	FeedPumpRun              bool      `json:"feedpumprun"`
	ROPumpRun                bool      `json:"ropumprun"`
	DeliveryRun              bool      `json:"deliveryrun"`
	DeliveryAuto             bool      `json:"deliveryauto"`
	InletRun                 bool      `json:"inletrun"`
	ConcBypassRun            bool      `json:"concbypassrun"`
	ProdDiversionRun         bool      `json:"proddiversionrun"`
	PLCTime                  time.Time `json:"plctime"`
	PermeateFlow             int64     `json:"permeateflow"`
	DeliveryFlow             int64     `json:"deliveryflow"`
	FeedFlow                 float64   `json:"feedflow"`
	ConcentrateFlow          float64   `json:"concentrateflow"`
	RecycleFlow              int64     `json:"recycleflow"`
	FeedTankLevel            float64   `json:"feedtanklevel"`
	DailyPermFlow            float64   `json:"dailypermflow"`
	Alarm                    bool      `json:"alarm"`
	AlarmWord                int64     `json:"alarmword"`
	ROStandby                bool      `json:"rostandby"`
	State                    int64     `json:"state"`
	Lockout                  bool      `json:"lockout"`
	RunFlush                 bool      `json:"runflush"`
	WarnWord0                int64     `json:"warnword0"`
	WarnWord1                int64     `json:"warnword1"`
	TotalHrs                 int64     `json:"totalhrs"`
	PermTDS                  float64   `json:"permtds"`
	FeedTDS                  float64   `json:"feedtds"`
	PermNitrate              float64   `json:"permnitrate"`
	PermTemp                 float64   `json:"permtemp"`
	ProdTankLevel            float64   `json:"prodtanklevel"`
	ProdTankDisable          bool      `json:"prodtankdisable"`
	ProdTankDepth            float64   `json:"prodtankdepth"`
	FeedTankDepth            float64   `json:"feedtankdepth"`
	ResidualTankDepth        float64   `json:"residualtankdepth"`
	InletPressure            float64   `json:"inletpressure"`
	ConcentratePressure      float64   `json:"concentratepressure"`
	PermeatePressure         float64   `json:"permeatepressure"`
	ROPressure               float64   `json:"ropressure"`
	DeliveryPressure         float64   `json:"deliverypressure"`
	FeedPressure             float64   `json:"feedpressure"`
	RecycleValvePosition     int64     `json:"recyclevalveposition"`
	ROPressCtrlValvePosition int64     `json:"ropressctrlvalveposition"`
	ROPumpSpeed              int64     `json:"ropumpspeed"`
	PowerMeter               int64     `json:"powermeter"`
	FlushDuret               int64     `json:"flushduret"`
	ProductTDS               float64   `json:"producttds"`
	ChlorinePumpRun          bool      `json:"chlorinepumprun"`
	ResidTankValveRun        bool      `json:"residtankvalverun"`
	ResidualTankLevel        float64   `json:"residualtanklevel"`
	RecordTime               time.Time `json:"recordtime"`
	FlushRun                 bool      `json:"flushrun"`
}

func (b *BluerockState) ValidateState() error {
	// Validate the state
	// TODO: Do rule-based checking for this
	return nil
}
