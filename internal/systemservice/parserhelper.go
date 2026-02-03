package systemservice

import (
	"fmt"
	"reflect"
	"time"

	"github.com/cbaguilar/svwatergo/internal/util"
)

var utcTimeType = reflect.TypeOf(util.UTCTime{})

// ParseRawInto copies values from a raw (string) struct into a typed struct.
// It matches fields by name and applies basic type conversions.
func ParseRawInto(raw any, out any) error {
	rv := reflect.ValueOf(raw)
	if rv.Kind() == reflect.Ptr {
		rv = rv.Elem()
	}
	if rv.Kind() != reflect.Struct {
		return fmt.Errorf("raw must be a struct")
	}

	ov := reflect.ValueOf(out)
	if ov.Kind() != reflect.Ptr || ov.IsNil() {
		return fmt.Errorf("out must be a non-nil pointer to struct")
	}
	ov = ov.Elem()
	if ov.Kind() != reflect.Struct {
		return fmt.Errorf("out must be a pointer to struct")
	}

	ot := ov.Type()
	for i := 0; i < ov.NumField(); i++ {
		f := ov.Field(i)
		ft := ot.Field(i)
		if !f.CanSet() {
			continue
		}
		name := ft.Name
		if name == "ID" {
			continue
		}

		if f.Type() == utcTimeType {
			if name == "RecordTime" {
				f.Set(reflect.ValueOf(util.UTCTime{Time: time.Now().UTC()}))
				continue
			}
			rawField := rv.FieldByName(name)
			if !rawField.IsValid() || rawField.Kind() != reflect.String {
				continue
			}
			parsed, err := util.ParsePlcTime(rawField.String())
			if err != nil {
				return err
			}
			f.Set(reflect.ValueOf(util.UTCTime{Time: parsed}))
			continue
		}

		rawField := rv.FieldByName(name)
		if !rawField.IsValid() || rawField.Kind() != reflect.String {
			continue
		}
		rawStr := rawField.String()

		switch f.Kind() {
		case reflect.String:
			f.SetString(rawStr)
		case reflect.Int, reflect.Int64, reflect.Int32, reflect.Int16, reflect.Int8:
			f.SetInt(util.ParseStringToInt(rawStr))
		case reflect.Uint, reflect.Uint64, reflect.Uint32, reflect.Uint16, reflect.Uint8:
			f.SetUint(uint64(util.ParseStringToInt(rawStr)))
		case reflect.Float32, reflect.Float64:
			f.SetFloat(util.ParseStringToFloat(rawStr))
		case reflect.Bool:
			f.SetBool(util.ParseStringToBool(rawStr))
		}
	}

	return nil
}
