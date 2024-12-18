/*
Utility functions that are used by the datamodels package.
*/
package datamodels

import "strconv"

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
