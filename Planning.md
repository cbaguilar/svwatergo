# Split into primary services:

## API Edge

Required legacy support:

`POST /UploadSensorDataNew`

Zip uploads! Let's see how often we hit these...


### New API Design:
We will support general RESTful verbs for the following endpoints:

`GET /health` : Health check for live monitoring. Can also probably give database stats perhaps...

`GET /api/v1/sites/:site/state/latest`: Get latest system site state. Currently pulls from database. TODO: 
we can probably store this in immediate memory.

`GET /api/v1/sites/:site/state?start=&end=&fields=&sample=&max_points=&smooth=&window=` Get range, useful for dashboards.

`POST /api/v1/sites/:site/state` : Post new sensor data. Accepts JSON array of objects.

## MQTT Edge
Can also pass to same data intake.

(2025: Not a priority since the native sites don't support it yet...

## Data intake:

any data cleaning that is needed + saving in postgresql

## Database layer:

for inserting data. Needs to handle various schemas and not be hard-coded.

Current approach: Each system is self-contained in a little package. Avoid duplicating code when possible

## Initialization:
allow us to define a config file for a water treatment system with all appropriate objects. Yaml?

## Alerts:
Schedule alerts and send out email informations
Basic idea: place scheduled alert check on postgres, inspect it every so often, claim posesison, make alert


## Communications
Send emails, maybe SMS messages

## Amazon layer:
 - Handle backups in S3 bucket

Secrets in .env for now.

## System monitoring logs

## Database API
 - Basic queries, ranged stuff, done
 - 
 - Calculations
 - Hard stuff passed off to Python libraries? Maybe not
