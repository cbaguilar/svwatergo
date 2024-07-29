# svwatergo
A Golang rewrite of the Salinas Valley Distributed water project with an emphasis on reliability and scalability.


## Critical needs:

- Collect data from an abritrary number of sites, store it in a database
- Serve basic HTTP endpoints to support querying point and range data for front-end dashboards
- Monitor incoming data and report any abnormalities
- Have behavior verified and testable
- MQTT support

## Cool things:
- Create alerts dynamically without having to recompile
- Support being distributed across several hosts
- Support dynamically defining water system objects (sensors, systems, etc)

  
