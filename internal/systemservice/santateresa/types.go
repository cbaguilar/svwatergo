package santateresa

import (
	"fmt"
	"time"

	"github.com/cbaguilar/svwatergo/internal/util"
)

// If a producer sends numeric/boolean JSON, keep your existing ingestion client sending strings,
// or add a shim to coerce to strings before unmarshaling into this type.
type RawSantaTeresaState struct {
	Location                 string `json:"location"`
	TotalROFlow              string `json:"totalroflow"`
	TotalInletFlow           string `json:"totalinletflow"`
	TotalConcFlow            string `json:"totalconcflow"`
	TotalDelFlow             string `json:"totaldelflow"`
	DumpProduct              string `json:"dumpproduct"`
	WellPumpRun              string `json:"wellpumprun"`
	WellPumpAuto             string `json:"wellpumpauto"`
	FeedPumpRun              string `json:"feedpumprun"`
	ROPumpRun                string `json:"ropumprun"`
	DeliveryRun              string `json:"deliveryrun"`
	DeliveryAuto             string `json:"deliveryauto"`
	InletRun                 string `json:"inletrun"`
	FlushRun                 string `json:"flushrun"`
	ConcBypassRun            string `json:"concbypassrun"`
	ProdDiversionRun         string `json:"proddiversionrun"`
	FlushDiversionRun        string `json:"flushdiversionrun"`
	PLCTime                  string `json:"plctime"`
	PermeateFlow             string `json:"permeateflow"`
	DeliveryFlow             string `json:"deliveryflow"`
	InletFlow                string `json:"inletflow"`
	ConcentrateFlow          string `json:"concentrateflow"`
	RecycleFlow              string `json:"recycleflow"`
	FeedTankLevel            string `json:"feedtanklevel"`
	DailyPermFlow            string `json:"dailypermflow"`
	DailyInletFlow           string `json:"dailyinletflow"`
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
	FlushTankLevel           string `json:"flushtanklevel"`
	FlushTankDepth           string `json:"flushtankdepth"`
	FlushTankFull            string `json:"flushtankfull"`
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
	FlushDurET               string `json:"flushduret"`
	ProductTDS               string `json:"producttds"`
}

type SantaTeresaState struct {
	ID                       *int64    `json:"id,omitempty" db:"id"` // <— NEW, optional
	Location                 string    `json:"location" db:"location"`
	TotalROFlow              int64     `json:"totalroflow" db:"totalroflow"`
	TotalInletFlow           int64     `json:"totalinletflow" db:"totalinletflow"`
	TotalConcFlow            int64     `json:"totalconcflow" db:"totalconcflow"`
	TotalDelFlow             int64     `json:"totaldelflow" db:"totaldelflow"`
	DumpProduct              bool      `json:"dumpproduct" db:"dumpproduct"`
	WellPumpRun              bool      `json:"wellpumprun" db:"wellpumprun"`
	WellPumpAuto             bool      `json:"wellpumpauto" db:"wellpumpauto"`
	FeedPumpRun              bool      `json:"feedpumprun" db:"feedpumprun"`
	ROPumpRun                bool      `json:"ropumprun" db:"ropumprun"`
	DeliveryRun              bool      `json:"deliveryrun" db:"deliveryrun"`
	DeliveryAuto             bool      `json:"deliveryauto" db:"deliveryauto"`
	InletRun                 bool      `json:"inletrun" db:"inletrun"`
	FlushRun                 bool      `json:"flushrun" db:"flushrun"`
	ConcBypassRun            bool      `json:"concbypassrun" db:"concbypassrun"`
	ProdDiversionRun         bool      `json:"proddiversionrun" db:"proddiversionrun"`
	FlushDiversionRun        bool      `json:"flushdiversionrun" db:"flushdiversionrun"`
	PLCTime                  time.Time `json:"plctime" db:"plctime"`
	PermeateFlow             float64   `json:"permeateflow" db:"permeateflow"`
	DeliveryFlow             float64   `json:"deliveryflow" db:"deliveryflow"`
	InletFlow                float64   `json:"inletflow" db:"inletflow"`
	ConcentrateFlow          float64   `json:"concentrateflow" db:"concentrateflow"`
	RecycleFlow              int64     `json:"recycleflow" db:"recycleflow"`
	FeedTankLevel            float64   `json:"feedtanklevel" db:"feedtanklevel"`
	DailyPermFlow            float64   `json:"dailypermflow" db:"dailypermflow"`
	DailyInletFlow           float64   `json:"dailyinletflow" db:"dailyinletflow"`
	Alarm                    bool      `json:"alarm" db:"alarm"`
	AlarmWord                int64     `json:"alarmword" db:"alarmword"`
	ROStandby                bool      `json:"rostandby" db:"rostandby"`
	State                    int64     `json:"state" db:"state"`
	Lockout                  bool      `json:"lockout" db:"lockout"`
	RunFlush                 bool      `json:"runflush" db:"runflush"`
	WarnWord0                int64     `json:"warnword0" db:"warnword0"`
	WarnWord1                int64     `json:"warnword1" db:"warnword1"`
	TotalHrs                 int64     `json:"totalhrs" db:"totalhrs"`
	PermTDS                  float64   `json:"permtds" db:"permtds"`
	FeedTDS                  float64   `json:"feedtds" db:"feedtds"`
	PermNitrate              float64   `json:"permnitrate" db:"permnitrate"`
	PermTemp                 float64   `json:"permtemp" db:"permtemp"`
	ProdTankLevel            float64   `json:"prodtanklevel" db:"prodtanklevel"`
	ProdTankDisable          bool      `json:"prodtankdisable" db:"prodtankdisable"`
	ProdTankDepth            float64   `json:"prodtankdepth" db:"prodtankdepth"`
	FeedTankDepth            float64   `json:"feedtankdepth" db:"feedtankdepth"`
	FlushTankLevel           float64   `json:"flushtanklevel" db:"flushtanklevel"`
	FlushTankDepth           float64   `json:"flushtankdepth" db:"flushtankdepth"`
	FlushTankFull            bool      `json:"flushtankfull" db:"flushtankfull"`
	InletPressure            float64   `json:"inletpressure" db:"inletpressure"`
	ConcentratePressure      float64   `json:"concentratepressure" db:"concentratepressure"`
	PermeatePressure         float64   `json:"permeatepressure" db:"permeatepressure"`
	ROPressure               float64   `json:"ropressure" db:"ropressure"`
	DeliveryPressure         float64   `json:"deliverypressure" db:"deliverypressure"`
	FeedPressure             float64   `json:"feedpressure" db:"feedpressure"`
	RecycleValvePosition     int64     `json:"recyclevalveposition" db:"recyclevalveposition"`
	ROPressCtrlValvePosition int64     `json:"ropressctrlvalveposition" db:"ropressctrlvalveposition"`
	ROPumpSpeed              int64     `json:"ropumpspeed" db:"ropumpspeed"`
	PowerMeter               int64     `json:"powermeter" db:"powermeter"`
	FlushDuret               int64     `json:"flushduret" db:"flushduret"`
	ProductTDS               float64   `json:"producttds" db:"producttds"`
	RecordTime               time.Time `json:"recordtime" db:"recordtime"`
}

func (s *SantaTeresaState) ValidateState() error {
	// TODO: add site-specific checks
	return nil
}

func FromRawData(rawData []byte) (*SantaTeresaState, error) {
	var raw RawSantaTeresaState
	if err := util.UnmarshalCaseInsensitive(rawData, &raw, nil); err != nil {
		return nil, err
	}

	parsedTime, err := util.ParsePlcTime(raw.PLCTime)
	if err != nil {
		return nil, fmt.Errorf("failed to parse time %s, %w ", raw.PLCTime, err)
	}

	out := SantaTeresaState{
		Location:                 raw.Location,
		TotalROFlow:              util.ParseStringToInt(raw.TotalROFlow),
		TotalInletFlow:           util.ParseStringToInt(raw.TotalInletFlow),
		TotalConcFlow:            util.ParseStringToInt(raw.TotalConcFlow),
		TotalDelFlow:             util.ParseStringToInt(raw.TotalDelFlow),
		DumpProduct:              util.ParseStringToBool(raw.DumpProduct),
		WellPumpRun:              util.ParseStringToBool(raw.WellPumpRun),
		WellPumpAuto:             util.ParseStringToBool(raw.WellPumpAuto),
		FeedPumpRun:              util.ParseStringToBool(raw.FeedPumpRun),
		ROPumpRun:                util.ParseStringToBool(raw.ROPumpRun),
		DeliveryRun:              util.ParseStringToBool(raw.DeliveryRun),
		DeliveryAuto:             util.ParseStringToBool(raw.DeliveryAuto),
		InletRun:                 util.ParseStringToBool(raw.InletRun),
		FlushRun:                 util.ParseStringToBool(raw.FlushRun),
		ConcBypassRun:            util.ParseStringToBool(raw.ConcBypassRun),
		ProdDiversionRun:         util.ParseStringToBool(raw.ProdDiversionRun),
		FlushDiversionRun:        util.ParseStringToBool(raw.FlushDiversionRun),
		PLCTime:                  parsedTime,
		PermeateFlow:             util.ParseStringToFloat(raw.PermeateFlow),
		DeliveryFlow:             util.ParseStringToFloat(raw.DeliveryFlow),
		InletFlow:                util.ParseStringToFloat(raw.InletFlow),
		ConcentrateFlow:          util.ParseStringToFloat(raw.ConcentrateFlow),
		RecycleFlow:              util.ParseStringToInt(raw.RecycleFlow),
		FeedTankLevel:            util.ParseStringToFloat(raw.FeedTankLevel),
		DailyPermFlow:            util.ParseStringToFloat(raw.DailyPermFlow),
		DailyInletFlow:           util.ParseStringToFloat(raw.DailyInletFlow),
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
		FlushTankLevel:           util.ParseStringToFloat(raw.FlushTankLevel),
		FlushTankDepth:           util.ParseStringToFloat(raw.FlushTankDepth),
		FlushTankFull:            util.ParseStringToBool(raw.FlushTankFull),
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
		FlushDuret:               util.ParseStringToInt(raw.FlushDurET),
		ProductTDS:               util.ParseStringToFloat(raw.ProductTDS),
		RecordTime:               time.Now().UTC(),
	}
	return &out, nil
}
