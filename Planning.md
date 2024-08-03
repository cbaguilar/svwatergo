# Split into primary services:

## API Edg

## MQTT Edge
Can also pass to same data intake.

## Data intake:

any data cleaning that is needed + saving in postgresql

## Database layer:

for inserting data. Needs to handle various schemas and not be hard-coded.

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
 - Basic queries, ranged stuff
 - 
 - Calculations
 - Hard stuff passed off to Python libraries
