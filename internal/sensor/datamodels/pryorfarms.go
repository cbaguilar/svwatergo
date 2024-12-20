package datamodels

/*
 Data models for our API for sending and receiveing
*/

import (
	"encoding/json"
	"time"

	"github.com/cbaguilar/svwatergo/internal/sensor"
)

// PryorFarmSystemManager

// Define the struct with string fields
type PryorFarmRawJSON struct {
	Location                 string `json:"location"`
	TotalRoFlow              string `json:"totalRoFlow"`
	TotalInletFlow           string `json:"totalInletFlow"`
	TotalConcFlow            string `json:"totalConcFlow"`
	TotalDelFlow             string `json:"totalDelFlow"`
	DumpProduct              string `json:"dumpProduct"`
	WellPumpRun              string `json:"wellPumpRun"`
	WellPumpAuto             string `json:"wellPumpAuto"`
	FeedPumpRun              string `json:"feedPumpRun"`
	RoPumpRun                string `json:"roPumpRun"`
	DeliveryRun              string `json:"deliveryRun"`
	DeliveryAuto             string `json:"deliveryAuto"`
	InletRun                 string `json:"inletRun"`
	FlushRun                 string `json:"flushRun"`
	ConcBypassRun            string `json:"concBypassRun"`
	ProdDiversionRun         string `json:"prodDiversionRun"`
	FlushDiversionRun        string `json:"flushDiversionRun"`
	PlcTime                  string `json:"plcTime"`
	PermeateFlow             string `json:"permeateFlow"`
	DeliveryFlow             string `json:"deliveryFlow"`
	InletFlow                string `json:"inletFlow"`
	ConcentrateFlow          string `json:"concentrateFlow"`
	RecycleFlow              string `json:"recycleFlow"`
	FeedTankLevel            string `json:"feedTankLevel"`
	DailyPermFlow            string `json:"dailyPermFlow"`
	DailyInletFlow           string `json:"dailyinletFlow"`
	Alarm                    string `json:"alarm"`
	AlarmWord                string `json:"alarmWord"`
	RoStandby                string `json:"roStandby"`
	State                    string `json:"state"`
	Lockout                  string `json:"lockout"`
	RunFlush                 string `json:"runFlush"`
	WarnWord0                string `json:"warnWord0"`
	WarnWord1                string `json:"warnWord1"`
	TotalHrs                 string `json:"totalHrs"`
	PermTds                  string `json:"permTds"`
	FeedTds                  string `json:"feedTds"`
	PermNitrate              string `json:"permNitrate"`
	PermTemp                 string `json:"permTemp"`
	ProdTankLevel            string `json:"prodTankLevel"`
	ProdTankDisable          string `json:"prodTankDisable"`
	ProdTankDepth            string `json:"prodTankDepth"`
	FeedTankDepth            string `json:"feedTankDepth"`
	FlushTankLevel           string `json:"flushTankLevel"`
	FlushTankDepth           string `json:"flushTankDepth"`
	FlushTankFull            string `json:"flushTankFull"`
	InletPressure            string `json:"inletPressure"`
	ConcentratePressure      string `json:"concentratePressure"`
	PermeatePressure         string `json:"permeatePressure"`
	RoPressure               string `json:"roPressure"`
	DeliveryPressure         string `json:"deliveryPressure"`
	FeedPressure             string `json:"feedPressure"`
	RecycleValvePosition     string `json:"recycleValvePosition"`
	RoPressCtrlValvePosition string `json:"roPressCtrlValvePosition"`
	RoPumpSpeed              string `json:"roPumpSpeed"`
	PowerMeter               string `json:"powerMeter"`
	FlushDurET               string `json:"flushDurET"`
	ProductTds               string `json:"productTds"`
}

// Struct for parsed data
type PryorFarmSystemState struct {
	Location                 string  `json:"location"`
	TotalRoFlow              int64   `json:"totalRoFlow"`
	TotalInletFlow           int64   `json:"totalInletFlow"`
	TotalConcFlow            int64   `json:"totalConcFlow"`
	TotalDelFlow             int64   `json:"totalDelFlow"`
	DumpProduct              bool    `json:"dumpProduct"`
	WellPumpRun              bool    `json:"wellPumpRun"`
	WellPumpAuto             bool    `json:"wellPumpAuto"`
	FeedPumpRun              bool    `json:"feedPumpRun"`
	RoPumpRun                bool    `json:"roPumpRun"`
	DeliveryRun              bool    `json:"deliveryRun"`
	DeliveryAuto             bool    `json:"deliveryAuto"`
	InletRun                 bool    `json:"inletRun"`
	FlushRun                 bool    `json:"flushRun"`
	ConcBypassRun            bool    `json:"concBypassRun"`
	ProdDiversionRun         bool    `json:"prodDiversionRun"`
	FlushDiversionRun        bool    `json:"flushDiversionRun"`
	PlcTime                  string  `json:"plcTime"`
	PermeateFlow             float64 `json:"permeateFlow"`
	DeliveryFlow             float64 `json:"deliveryFlow"`
	InletFlow                float64 `json:"inletFlow"`
	ConcentrateFlow          float64 `json:"concentrateFlow"`
	RecycleFlow              float64 `json:"recycleFlow"`
	FeedTankLevel            float64 `json:"feedTankLevel"`
	DailyPermFlow            float64 `json:"dailyPermFlow"`
	DailyInletFlow           float64 `json:"dailyinletFlow"`
	Alarm                    bool    `json:"alarm"`
	AlarmWord                int64   `json:"alarmWord"`
	RoStandby                bool    `json:"roStandby"`
	State                    int64   `json:"state"`
	Lockout                  bool    `json:"lockout"`
	RunFlush                 bool    `json:"runFlush"`
	WarnWord0                int64   `json:"warnWord0"`
	WarnWord1                int64   `json:"warnWord1"`
	TotalHrs                 int64   `json:"totalHrs"`
	PermTds                  float64 `json:"permTds"`
	FeedTds                  float64 `json:"feedTds"`
	PermNitrate              float64 `json:"permNitrate"`
	PermTemp                 float64 `json:"permTemp"`
	ProdTankLevel            float64 `json:"prodTankLevel"`
	ProdTankDisable          bool    `json:"prodTankDisable"`
	ProdTankDepth            float64 `json:"prodTankDepth"`
	FeedTankDepth            float64 `json:"feedTankDepth"`
	FlushTankLevel           float64 `json:"flushTankLevel"`
	FlushTankDepth           float64 `json:"flushTankDepth"`
	FlushTankFull            bool    `json:"flushTankFull"`
	InletPressure            float64 `json:"inletPressure"`
	ConcentratePressure      float64 `json:"concentratePressure"`
	PermeatePressure         float64 `json:"permeatePressure"`
	RoPressure               float64 `json:"roPressure"`
	DeliveryPressure         float64 `json:"deliveryPressure"`
	FeedPressure             float64 `json:"feedPressure"`
	RecycleValvePosition     int64   `json:"recycleValvePosition"`
	RoPressCtrlValvePosition int64   `json:"roPressCtrlValvePosition"`
	RoPumpSpeed              int64   `json:"roPumpSpeed"`
	PowerMeter               int64   `json:"powerMeter"`
	FlushDurET               string  `json:"flushDurET"`
	ProductTds               float64 `json:"productTds"`
}

// Constructor for PryorFarmSystemManager

func NewPryorFarmsSystemManager() sensor.SystemManager {
	return &sensor.SystemManager{
		
}

// Implement RemoteSystem interface for PryorFarmParsedPost
func (p *PryorFarmSystemState) FromJSON(jsonData []byte) error {
	// We must first unmarshal jsonData into a PryorFarmRawJSON object,
	// then we can convert it to a PryorFarmSystemState object

	// Unmarshal the JSON data into a PryorFarmRawJSON object
	var raw PryorFarmRawJSON
	if err := json.Unmarshal(jsonData, &raw); err != nil {
		return err
	}

	// Convert PryorFarmRawJSON to PryorFarmSystemState
	*p = PryorFarmSystemState{
		Location:                 raw.Location,
		TotalRoFlow:              parseStringToInt(raw.TotalRoFlow),
		TotalInletFlow:           parseStringToInt(raw.TotalInletFlow),
		TotalConcFlow:            parseStringToInt(raw.TotalConcFlow),
		TotalDelFlow:             parseStringToInt(raw.TotalDelFlow),
		DumpProduct:              parseStringToBool(raw.DumpProduct),
		WellPumpRun:              parseStringToBool(raw.WellPumpRun),
		WellPumpAuto:             parseStringToBool(raw.WellPumpAuto),
		FeedPumpRun:              parseStringToBool(raw.FeedPumpRun),
		RoPumpRun:                parseStringToBool(raw.RoPumpRun),
		DeliveryRun:              parseStringToBool(raw.DeliveryRun),
		DeliveryAuto:             parseStringToBool(raw.DeliveryAuto),
		InletRun:                 parseStringToBool(raw.InletRun),
		FlushRun:                 parseStringToBool(raw.FlushRun),
		ConcBypassRun:            parseStringToBool(raw.ConcBypassRun),
		ProdDiversionRun:         parseStringToBool(raw.ProdDiversionRun),
		FlushDiversionRun:        parseStringToBool(raw.FlushDiversionRun),
		PlcTime:                  raw.PlcTime,
		PermeateFlow:             parseStringToFloat(raw.PermeateFlow),
		DeliveryFlow:             parseStringToFloat(raw.DeliveryFlow),
		InletFlow:                parseStringToFloat(raw.InletFlow),
		ConcentrateFlow:          parseStringToFloat(raw.ConcentrateFlow),
		RecycleFlow:              parseStringToFloat(raw.RecycleFlow),
		FeedTankLevel:            parseStringToFloat(raw.FeedTankLevel),
		DailyPermFlow:            parseStringToFloat(raw.DailyPermFlow),
		DailyInletFlow:           parseStringToFloat(raw.DailyInletFlow),
		Alarm:                    parseStringToBool(raw.Alarm),
		AlarmWord:                parseStringToInt(raw.AlarmWord),
		RoStandby:                parseStringToBool(raw.RoStandby),
		State:                    parseStringToInt(raw.State),
		Lockout:                  parseStringToBool(raw.Lockout),
		RunFlush:                 parseStringToBool(raw.RunFlush),
		WarnWord0:                parseStringToInt(raw.WarnWord0),
		WarnWord1:                parseStringToInt(raw.WarnWord1),
		TotalHrs:                 parseStringToInt(raw.TotalHrs),
		PermTds:                  parseStringToFloat(raw.PermTds),
		FeedTds:                  parseStringToFloat(raw.FeedTds),
		PermNitrate:              parseStringToFloat(raw.PermNitrate),
		PermTemp:                 parseStringToFloat(raw.PermTemp),
		ProdTankLevel:            parseStringToFloat(raw.ProdTankLevel),
		ProdTankDisable:          parseStringToBool(raw.ProdTankDisable),
		ProdTankDepth:            parseStringToFloat(raw.ProdTankDepth),
		FeedTankDepth:            parseStringToFloat(raw.FeedTankDepth),
		FlushTankLevel:           parseStringToFloat(raw.FlushTankLevel),
		FlushTankDepth:           parseStringToFloat(raw.FlushTankDepth),
		FlushTankFull:            parseStringToBool(raw.FlushTankFull),
		InletPressure:            parseStringToFloat(raw.InletPressure),
		ConcentratePressure:      parseStringToFloat(raw.ConcentratePressure),
		PermeatePressure:         parseStringToFloat(raw.PermeatePressure),
		RoPressure:               parseStringToFloat(raw.RoPressure),
		DeliveryPressure:         parseStringToFloat(raw.DeliveryPressure),
		FeedPressure:             parseStringToFloat(raw.FeedPressure),
		RecycleValvePosition:     parseStringToInt(raw.RecycleValvePosition),
		RoPressCtrlValvePosition: parseStringToInt(raw.RoPressCtrlValvePosition),
		RoPumpSpeed:              parseStringToInt(raw.RoPumpSpeed),
		PowerMeter:               parseStringToInt(raw.PowerMeter),
		FlushDurET:               raw.FlushDurET,
		ProductTds:               parseStringToFloat(raw.ProductTds),
	}

	return nil
}

func (p *PryorFarmSystemState) SaveState() error {
	// Implement the logic to save the current state to the database
	return nil
}

func (p *PryorFarmSystemState) ToWebRepresentation() map[string]interface{} {
	return map[string]interface{}{
		"location": p.Location,
		// Add other fields as needed
	}
}

func (p *PryorFarmSystemState) GetCurrentState() (*PryorFarmSystemState, error) {
	// Implement the logic to retrieve the current state from the database
	return &PryorFarmSystemState{
		Location: p.Location,
		PlcTime:  time.Now().Format(time.RFC3339),
	}, nil
}

func (p *PryorFarmSystemState) GetStateRange(startTime, endTime string) ([]*RemoteSystemState, error) {
	// Implement the logic to retrieve a range of states from the database
	return nil, nil
}

func (p *PryorFarmSystemState) CheckState() error {
	// alarm
	return nil
}
