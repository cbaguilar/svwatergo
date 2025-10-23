package bluerock

import (
	"encoding/json"
	"time"

	"github.com/cbaguilar/svwatergo/internal/util"
)

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

func FromRawData(rawData []byte) (*BluerockState, error) {
	var raw RawBluerockState
	//unmarshal rawData into raw
	err := json.Unmarshal(rawData, &raw)
	if err != nil {
		return nil, err
	}

	parsedTime, err := util.ParsePlcTime(raw.PLCTime)
	if err != nil {
		print("Error parsing time")
		return nil, err
	}

	//parse raw into parsed
	parsed := BluerockState{
		Location:                 raw.Location,
		TotalROFlow:              util.ParseStringToInt(raw.TotalROFlow),
		TotalFeedFlow:            util.ParseStringToInt(raw.TotalFeedFlow),
		TotalRecycleFlow:         util.ParseStringToInt(raw.TotalRecycleFlow),
		TotalDelFlow:             util.ParseStringToInt(raw.TotalDelFlow),
		DumpProduct:              util.ParseStringToBool(raw.DumpProduct),
		WellPumpRun:              util.ParseStringToBool(raw.WellPumpRun),
		WellPumpAuto:             util.ParseStringToBool(raw.WellPumpAuto),
		FeedPumpRun:              util.ParseStringToBool(raw.FeedPumpRun),
		ROPumpRun:                util.ParseStringToBool(raw.ROPumpRun),
		DeliveryRun:              util.ParseStringToBool(raw.DeliveryRun),
		DeliveryAuto:             util.ParseStringToBool(raw.DeliveryAuto),
		InletRun:                 util.ParseStringToBool(raw.InletRun),
		ConcBypassRun:            util.ParseStringToBool(raw.ConcBypassRun),
		ProdDiversionRun:         util.ParseStringToBool(raw.ProdDiversionRun),
		PLCTime:                  parsedTime,
		PermeateFlow:             util.ParseStringToInt(raw.PermeateFlow),
		DeliveryFlow:             util.ParseStringToInt(raw.DeliveryFlow),
		FeedFlow:                 util.ParseStringToFloat(raw.FeedFlow),
		ConcentrateFlow:          util.ParseStringToFloat(raw.ConcentrateFlow),
		RecycleFlow:              util.ParseStringToInt(raw.RecycleFlow),
		FeedTankLevel:            util.ParseStringToFloat(raw.FeedTankLevel),
		DailyPermFlow:            util.ParseStringToFloat(raw.DailyPermFlow),
		Alarm:                    util.ParseStringToBool(raw.Alarm),
		AlarmWord:                util.ParseStringToInt(raw.AlarmWord),
		ROStandby:                util.ParseStringToBool(raw.ROStandby),
		State:                    util.ParseStringToInt(raw.State),
		Lockout:                  util.ParseStringToBool(raw.Lockout),
		RunFlush:                 util.ParseStringToBool(raw.RunFlush),
		WarnWord0:                util.ParseStringToInt(raw.WarnWord0),
		WarnWord1:                util.ParseStringToInt(raw.WarnWord1),
		TotalHrs:                 util.ParseStringToInt(raw.TotalHrs),
		PermTDS:                  util.ParseStringToFloat(raw.PermTDS),
		FeedTDS:                  util.ParseStringToFloat(raw.FeedTDS),
		PermNitrate:              util.ParseStringToFloat(raw.PermNitrate),
		PermTemp:                 util.ParseStringToFloat(raw.PermTemp),
		ProdTankLevel:            util.ParseStringToFloat(raw.ProdTankLevel),
		ProdTankDisable:          util.ParseStringToBool(raw.ProdTankDisable),
		ProdTankDepth:            util.ParseStringToFloat(raw.ProdTankDepth),
		FeedTankDepth:            util.ParseStringToFloat(raw.FeedTankDepth),
		ResidualTankDepth:        util.ParseStringToFloat(raw.ResidualTankDepth),
		InletPressure:            util.ParseStringToFloat(raw.InletPressure),
		ConcentratePressure:      util.ParseStringToFloat(raw.ConcentratePressure),
		PermeatePressure:         util.ParseStringToFloat(raw.PermeatePressure),
		ROPressure:               util.ParseStringToFloat(raw.ROPressure),
		DeliveryPressure:         util.ParseStringToFloat(raw.DeliveryPressure),
		FeedPressure:             util.ParseStringToFloat(raw.FeedPressure),
		RecycleValvePosition:     util.ParseStringToInt(raw.RecycleValvePosition),
		ROPressCtrlValvePosition: util.ParseStringToInt(raw.ROPressCtrlValvePosition),
		ROPumpSpeed:              util.ParseStringToInt(raw.ROPumpSpeed),
		PowerMeter:               util.ParseStringToInt(raw.PowerMeter),
		FlushDuret:               util.ParseStringToInt(raw.FlushDuret),
		ProductTDS:               util.ParseStringToFloat(raw.ProductTDS),
		ChlorinePumpRun:          util.ParseStringToBool(raw.ChlorinePumpRun),
		ResidTankValveRun:        util.ParseStringToBool(raw.ResidTankValveRun),
		ResidualTankLevel:        util.ParseStringToFloat(raw.ResidualTankLevel),
		RecordTime:               time.Now(),
		FlushRun:                 util.ParseStringToBool(raw.FlushRun),
	}
	return &parsed, nil
}
