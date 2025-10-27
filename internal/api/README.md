# Route examples


```
curl -X POST -d "{\"noodle\":3}" localhost:8080/uploadSensorDataNew
```


```
curl -X POST "http://localhost:8080/uploadSensorDataNew" \
  -H "Content-Type: application/json" \
  -d '[
    {
      "location": "bluerock",
      "totalroflow": "12345",
      "plctime": "PLC#2025-10-26T20:31:00Z",
      "deliveryflow": "10",
      "feedflow": "1.5",
      "alarm": "0"
    }
  ]'
```