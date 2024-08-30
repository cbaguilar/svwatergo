package api

/*
 Data models for our API for sending and receiveing
 */

 package main

import (
	"encoding/json"
	"fmt"
	"log"
	"strconv"
)

// Define the struct with string fields
type PryorFarmRawPost struct {
	Location                   string `json:"location"`
	TotalRoFlow                string `json:"totalRoFlow"`
	TotalInletFlow             string `json:"totalInletFlow"`
	TotalConcFlow              string `json:"totalConcFlow"`
	TotalDelFlow               string `json:"totalDelFlow"`
	DumpProduct                string `json:"dumpProduct"`
	WellPumpRun                string `json:"wellPumpRun"`
	WellPumpAuto               string `json:"wellPumpAuto"`
	FeedPumpRun                string `json:"feedPumpRun"`
	RoPumpRun                  string `json:"roPumpRun"`
	DeliveryRun                string `json:"deliveryRun"`
	DeliveryAuto               string `json:"deliveryAuto"`
	InletRun                   string `json:"inletRun"`
	FlushRun                   string `json:"flushRun"`
	ConcBypassRun              string `json:"concBypassRun"`
	ProdDiversionRun           string `json:"prodDiversionRun"`
	FlushDiversionRun          string `json:"flushDiversionRun"`
	PlcTime                    string `json:"plcTime"`
	PermeateFlow               string `json:"permeateFlow"`
	DeliveryFlow               string `json:"deliveryFlow"`
	InletFlow                  string `json:"inletFlow"`
	ConcentrateFlow            string `json:"concentrateFlow"`
	RecycleFlow                string `json:"recycleFlow"`
	FeedTankLevel              string `json:"feedTankLevel"`
	DailyPermFlow              string `json:"dailyPermFlow"`
	DailyInletFlow             string `json:"dailyinletFlow"`
	Alarm                      string `json:"alarm"`
	AlarmWord                  string `json:"alarmWord"`
	RoStandby                  string `json:"roStandby"`
	State                      string `json:"state"`
	Lockout                    string `json:"lockout"`
	RunFlush                   string `json:"runFlush"`
	WarnWord0                  string `json:"warnWord0"`
	WarnWord1                  string `json:"warnWord1"`
	TotalHrs                   string `json:"totalHrs"`
	PermTds                    string `json:"permTds"`
	FeedTds                    string `json:"feedTds"`
	PermNitrate                string `json:"permNitrate"`
	PermTemp                   string `json:"permTemp"`
	ProdTankLevel              string `json:"prodTankLevel"`
	ProdTankDisable            string `json:"prodTankDisable"`
	ProdTankDepth              string `json:"prodTankDepth"`
	FeedTankDepth              string `json:"feedTankDepth"`
	FlushTankLevel             string `json:"flushTankLevel"`
	FlushTankDepth             string `json:"flushTankDepth"`
	FlushTankFull              string `json:"flushTankFull"`
	InletPressure              string `json:"inletPressure"`
	ConcentratePressure        string `json:"concentratePressure"`
	PermeatePressure           string `json:"permeatePressure"`
	RoPressure                 string `json:"roPressure"`
	DeliveryPressure           string `json:"deliveryPressure"`
	FeedPressure               string `json:"feedPressure"`
	RecycleValvePosition       string `json:"recycleValvePosition"`
	RoPressCtrlValvePosition   string `json:"roPressCtrlValvePosition"`
	RoPumpSpeed                string `json:"roPumpSpeed"`
	PowerMeter                 string `json:"powerMeter"`
	FlushDurET                 string `json:"flushDurET"`
	ProductTds                 string `json:"productTds"`
}

// Struct for parsed data
type PryorFarmParsedPost struct {
	Location                   string  `json:"location"`
	TotalRoFlow                int64   `json:"totalRoFlow"`
	TotalInletFlow             int64   `json:"totalInletFlow"`
	TotalConcFlow              int64   `json:"totalConcFlow"`
	TotalDelFlow               int64   `json:"totalDelFlow"`
	DumpProduct                bool    `json:"dumpProduct"`
	WellPumpRun                bool    `json:"wellPumpRun"`
	WellPumpAuto               bool    `json:"wellPumpAuto"`
	FeedPumpRun                bool    `json:"feedPumpRun"`
	RoPumpRun                  bool    `json:"roPumpRun"`
	DeliveryRun                bool    `json:"deliveryRun"`
	DeliveryAuto               bool    `json:"deliveryAuto"`
	InletRun                   bool    `json:"inletRun"`
	FlushRun                   bool    `json:"flushRun"`
	ConcBypassRun              bool    `json:"concBypassRun"`
	ProdDiversionRun           bool    `json:"prodDiversionRun"`
	FlushDiversionRun          bool    `json:"flushDiversionRun"`
	PlcTime                    string  `json:"plcTime"`
	PermeateFlow               float64 `json:"permeateFlow"`
	DeliveryFlow               float64 `json:"deliveryFlow"`
	InletFlow                  float64 `json:"inletFlow"`
	ConcentrateFlow            float64 `json:"concentrateFlow"`
	RecycleFlow                float64 `json:"recycleFlow"`
	FeedTankLevel              float64 `json:"feedTankLevel"`
	DailyPermFlow              float64 `json:"dailyPermFlow"`
	DailyInletFlow             float64 `json:"dailyinletFlow"`
	Alarm                      bool    `json:"alarm"`
	AlarmWord                  int64   `json:"alarmWord"`
	RoStandby                  bool    `json:"roStandby"`
	State                      int64   `json:"state"`
	Lockout                    bool    `json:"lockout"`
	RunFlush                   bool    `json:"runFlush"`
	WarnWord0                  int64   `json:"warnWord0"`
	WarnWord1                  int64   `json:"warnWord1"`
	TotalHrs                   int64   `json:"totalHrs"`
	PermTds                    float64 `json:"permTds"`
	FeedTds                    float64 `json:"feedTds"`
	PermNitrate                float64 `json:"permNitrate"`
	PermTemp                   float64 `json:"permTemp"`
	ProdTankLevel              float64 `json:"prodTankLevel"`
	ProdTankDisable            bool    `json:"prodTankDisable"`
	ProdTankDepth              float64 `json:"prodTankDepth"`
	FeedTankDepth              float64 `json:"feedTankDepth"`
	FlushTankLevel             float64 `json:"flushTankLevel"`
	FlushTankDepth             float64 `json:"flushTankDepth"`
	FlushTankFull              bool    `json:"flushTankFull"`
	InletPressure              float64 `json:"inletPressure"`
	ConcentratePressure        float64 `json:"concentratePressure"`
	PermeatePressure           float64 `json:"permeatePressure"`
	RoPressure                 float64 `json:"roPressure"`
	DeliveryPressure           float64 `json:"deliveryPressure"`
	FeedPressure               float64 `json:"feedPressure"`
	RecycleValvePosition       int64   `json:"recycleValvePosition"`
	RoPressCtrlValvePosition   int64   `json:"roPressCtrlValvePosition"`
	RoPumpSpeed                int64   `json:"roPumpSpeed"`
	PowerMeter                 int64   `json:"powerMeter"`
	FlushDurET                 string  `json:"flushDurET"`
	ProductTds                 float64 `json:"productTds"`
}

func parseStringToBool(s string) bool {
	return s == "1"
}

func parseStringToInt(s string) int64 {
	v, _ := strconv.ParseInt(s, 10, 64)
	return v
}

func parseStringToFloat(s string) float64 {
	v, _ := strconv.ParseFloat(s, 64)
	return v
}

func 

func 

var parsedData []PryorFarmDataParsed
	for _, d := range data {
		pd := PryorFarmDataParsed{
			Location:                 d.Location,
			TotalRoFlow:              parseStringToInt(d.TotalRoFlow),
			TotalInletFlow:           parseStringToInt(d.TotalInletFlow),
			TotalConcFlow:            parseStringToInt(d.TotalConcFlow),
			TotalDelFlow:             parseStringToInt(d.TotalDelFlow),
			DumpProduct:              parseStringToBool(d.DumpProduct),
			WellPumpRun:              parseStringToBool(d.WellPumpRun),
			WellPumpAuto:             parseStringToBool(d.WellPumpAuto),
			FeedPumpRun:              parseStringToBool(d.FeedPumpRun),
			RoPumpRun:                parseStringToBool(d.RoPumpRun),
			DeliveryRun:              parseStringToBool(d.DeliveryRun),
			DeliveryAuto:             parseStringToBool(d.DeliveryAuto),
			InletRun:                 parseStringToBool(d.InletRun),
			FlushRun:                 parseStringToBool(d.FlushRun),
			ConcBypassRun:            parseStringToBool(d.ConcBypassRun),
			ProdDiversionRun:         parseStringToBool(d.ProdDiversionRun),
			FlushDiversionRun:        parseStringToBool(d.FlushDiversionRun),
			PlcTime:                  d.PlcTime,
			PermeateFlow:             parseStringToFloat(d.PermeateFlow),
			DeliveryFlow:             parseStringToFloat(d.DeliveryFlow),
			InletFlow:                parseStringToFloat(d.InletFlow),
			ConcentrateFlow:          parseStringToFloat(d.ConcentrateFlow),
			RecycleFlow:              parseStringToFloat(d.RecycleFlow),
			FeedTankLevel:            parseStringToFloat(d.FeedTankLevel),
			DailyPermFlow:            parseStringToFloat(d.DailyPermFlow),
			DailyInletFlow:           parseStringToFloat(d.DailyInletFlow),
			Alarm:                    parseStringToBool(d.Alarm),
			AlarmWord:                parseStringToInt(d.AlarmWord),
			RoStandby:                parseStringToBool(d.RoStandby),
			State:                    parseStringToInt(d.State),
			Lockout:                  parseStringToBool(d.Lockout),
			RunFlush:                 parseStringToBool(d.RunFlush),
			WarnWord0:                parseStringToInt(d.WarnWord0),
			WarnWord1:                parseStringToInt(d.WarnWord1),
			TotalHrs:                 parseStringToInt(d.TotalHrs),
			PermTds:                  parseStringToFloat(d.PermTds),
			FeedTds:                  parseStringToFloat(d.FeedTds),
			PermNitrate:              parseStringToFloat(d.PermNitrate),
			PermTemp:                 parseStringToFloat(d.PermTemp),
			ProdTankLevel:            parseStringToFloat(d.ProdTankLevel),
			ProdTankDisable:          parseStringToBool(d.ProdTankDisable),
			ProdTankDepth:            parseStringToFloat(d.ProdTankDepth),
			FeedTankDepth:            parseStringToFloat(d.FeedTankDepth),
			FlushTankLevel:           parseStringToFloat(d.FlushTankLevel),
			FlushTankDepth:           parseStringToFloat(d.FlushTankDepth),
			FlushTankFull:            parseStringToBool(d.FlushTankFull),
			InletPressure:            parseStringToFloat(d.InletPressure),
			ConcentratePressure:      parseStringToFloat(d.ConcentratePressure),
			PermeatePressure:         parseStringToFloat(d.PermeatePressure),
			RoPressure:               parseStringToFloat(d.RoPressure),
			DeliveryPressure:         parseStringToFloat(d.DeliveryPressure),
			FeedPressure:             parseStringToFloat(d.FeedPressure),
			RecycleValvePosition:     parseStringToInt(d.RecycleValvePosition),
			RoPressCtrlValvePosition: parseStringToInt(d.RoPressCtrlValvePosition),
			RoPumpSpeed:              parseStringToInt(d.RoPumpSpeed),
			PowerMeter:               parseStringToInt(d.PowerMeter),
			FlushDurET:               d.FlushDurET,
			ProductTds:               parseStringToFloat(d.ProductTds),
		}
		parsedData = append(parsedData, pd)
	}