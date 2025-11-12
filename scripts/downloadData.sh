#!/bin/bash


curl -X GET "http://localhost:8080/api/v1/sites/pryorfarm/state/latest"


curl -X GET "http://localhost:8080/api/v1/sites/santateresa/state?start=2024-06-01T00:00:00Z&end=2024-06-02T00:00:00Z"