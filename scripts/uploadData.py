#!/usr/bin/env python3
import requests
import json
from datetime import datetime, timezone

URL = "http://localhost:8080/uploadSensorDataNew"

def make_payload():
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    plctime = f"PLC#{now}"

    return [
        {
            "location": "bluerock",
            "totalroflow": "2321518",
            "totalfeedflow": "3193038",
            "totalrecycleflow": "1977203",
            "totaldelflow": "1859992",
            "dumpproduct": "0",
            "wellpumprun": "0",
            "wellpumpauto": "1",
            "feedpumprun": "1",
            "ropumprun": "1",
            "deliveryrun": "0",
            "deliveryauto": "1",
            "inletrun": "1",
            "concbypassrun": "0",
            "proddiversionrun": "1",
            "plctime": plctime,
            "permeateflow": "3.12",
            "deliveryflow": "0",
            "feedflow": "5.16",
            "concentrateflow": "1.92",
            "recycleflow": "0",
            "feedtanklevel": "67.32244",
            "dailypermflow": "663.1326",
            "alarm": "0",
            "alarmword": "4",
            "rostandby": "1",
            "state": "2",
            "lockout": "0",
            "runflush": "0",
            "warnword0": "4",
            "warnword1": "2048",
            "totalhrs": "18926",
            "permtds": "35.62645",
            "feedtds": "2464.844",
            "permnitrate": "3.804977",
            "permtemp": "19.75188",
            "prodtanklevel": "67.1521",
            "prodtankdisable": "0",
            "prodtankdepth": "1.9",
            "feedtankdepth": "3.3",
            "residualtankdepth": "1.3",
            "inletpressure": "71.79905",
            "concentratepressure": "207.3025",
            "permeatepressure": "2.49566",
            "ropressure": "223.5062",
            "deliverypressure": "52.64757",
            "feedpressure": "75.08681",
            "recyclevalveposition": "0",
            "ropressctrlvalveposition": "85",
            "ropumpspeed": "42",
            "powermeter": "40734279",
            "flushduret": "0",
            "producttds": "104.4398",
            "chlorinepumprun": "0",
            "residtankvalverun": "0",
            "residualtanklevel": "455.857",
            "recordtime": now,
            "flushrun": "0"
        }
    ]

def main():
    payload = make_payload()
    try:
        response = requests.post(URL, json=payload, headers={"Content-Type": "application/json"})
        response.raise_for_status()
        print("Request succeeded:")
        print(json.dumps(response.json(), indent=2))
    except requests.exceptions.RequestException as e:
        print("Request failed:", e)
        if e.response is not None:
            print("Response:", e.response.text)

if __name__ == "__main__":
    main()
