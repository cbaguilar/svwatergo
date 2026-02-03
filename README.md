# svwatergo
A Golang rewrite of the Salinas Valley Distributed water project with an emphasis on reliability and scalability.

## Monorepo

- Backend: `svwatergo/`
- Frontend (React): `svwatergo/frontend/bluerockfrontend/`


## Critical needs:

- [x] Collect data from an abritrary number of sites, store it in a database
- [x] Serve basic HTTP endpoints to support querying point and range data for front-end dashboards
- [] Monitor incoming data and report any abnormalities
- - [] Rule-based validation for each system that clearly defines acceptable ranges for each sensor
- [] Tight coupling between front-end and backend datatypes
   - [] JSON schema definitions for data types, human-readable names, ranges, chart-types, etc
   - []  API endpoint that gives dashboard-ready data (including soft sensors)
   - 
- [] Have behavior verified and testable ()
- [] MQTT support


## Cool things:
- Create alerts dynamically without having to recompile
- Support being distributed across several hosts
- Support dynamically defining water system objects (sensors, systems, etc)

  
