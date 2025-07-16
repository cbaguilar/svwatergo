package bluerock

// RawBluerockState schema for raw ingestion data has the same fields as BluerockState
// but all the data are strings

type RawBluerockState struct {
	Location                 string `json:"location"`
	TotalROFlow              string `json:"totalroflow"`
	TotalFeedFlow            string `json:"totalfeedflow"`
	TotalRecycleFlow         string `json:"totalrecycleflow"`
	TotalDelFlow             string `json:"totaldelflow"`
	DumpProduct              string `json:"dumpproduct"`
	WellPumpRun              string `json:"wellpumprun"`
	WellPumpAuto             string `json:"wellpumpauto"`
	FeedPumpRun              string `json:"feedpumprun"`
	ROPumpRun                string `json:"ropumprun"`
	DeliveryRun              string `json:"deliveryrun"`
	DeliveryAuto             string `json:"deliveryauto"`
	InletRun                 string `json:"inletrun"`
	ConcBypassRun            string `json:"concbypassrun"`
	ProdDiversionRun         string `json:"proddiversionrun"`
	PLCTime                  string `json:"plctime"`
	PermeateFlow             string `json:"permeateflow"`
	DeliveryFlow             string `json:"deliveryflow"`
	FeedFlow                 string `json:"feedflow"`
	ConcentrateFlow          string `json:"concentrateflow"`
	RecycleFlow              string `json:"recycleflow"`
	FeedTankLevel            string `json:"feedtanklevel"`
	DailyPermFlow            string `json:"dailypermflow"`
	Alarm                    string `json:"alarm"`
	AlarmWord                string `json:"alarmword"`
	ROStandby                string `json:"rostandby"`
	State                    string `json:"state"`
	Lockout                  string `json:"lockout"`
	RunFlush                 string `json:"runflush"`
	WarnWord0                string `json:"warnword0"`
	WarnWord1                string `json:"warnword1"`
	TotalHrs                 string `json:"totalhrs"`
	PermTDS                  string `json:"permtds"`
	FeedTDS                  string `json:"feedtds"`
	PermNitrate              string `json:"permnitrate"`
	PermTemp                 string `json:"permtemp"`
	ProdTankLevel            string `json:"prodtanklevel"`
	ProdTankDisable          string `json:"prodtankdisable"`
	ProdTankDepth            string `json:"prodtankdepth"`
	FeedTankDepth            string `json:"feedtankdepth"`
	ResidualTankDepth        string `json:"residualtankdepth"`
	InletPressure            string `json:"inletpressure"`
	ConcentratePressure      string `json:"concentratepressure"`
	PermeatePressure         string `json:"permeatepressure"`
	ROPressure               string `json:"ropressure"`
	DeliveryPressure         string `json:"deliverypressure"`
	FeedPressure             string `json:"feedpressure"`
	RecycleValvePosition     string `json:"recyclevalveposition"`
	ROPressCtrlValvePosition string `json:"ropressctrlvalveposition"`
	ROPumpSpeed              string `json:"ropumpspeed"`
	PowerMeter               string `json:"powermeter"`
	FlushDuret               string `json:"flushduret"`
	ProductTDS               string `json:"producttds"`
	ChlorinePumpRun          string `json:"chlorinepumprun"`
	ResidTankValveRun        string `json:"residtankvalverun"`
	ResidualTankLevel        string `json:"residualtanklevel"`
	RecordTime               string `json:"recordtime"`
	SchemaVersion            string `json:"schema_version"`
	Extras                   string `json:"extras"`
	FlushRun                 string `json:"flushrun"`
}
