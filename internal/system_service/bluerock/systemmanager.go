package bluerock

import (
	"encoding/json"
	"time"

	"github.com/cbaguilar/svwatergo/internal/system_contract"
	"github.com/cbaguilar/svwatergo/internal/util"
)

type BluerockManager struct {
	Datastore system_contract.Datastore
}

func (b *BluerockManager) RawToParsed(rawData []byte) (*BluerockState, error) {
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

func (b *BluerockManager) GetLatest() BluerockState {
	return BluerockState{}
}

func (b *BluerockManager) ConsumeData(rawData []byte) error { //unmarshal rawData into raw

	state, err := b.RawToParsed(rawData)
	if err != nil {
		return err
	}
	return b.Datastore.SaveState(state)
}
