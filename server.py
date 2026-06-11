from flask import Flask, jsonify, request
from flask_cors import CORS
import meraki
import os
app = Flask(__name__)
CORS(app)

API_KEY = os.environ.get("MERAKI_API_KEY")
ORG_ID = os.environ.get("MERAKI_ORG_ID")

dashboard = meraki.DashboardAPI(
    API_KEY,
    suppress_logging=True,
    single_request_timeout=180
)


def extract_metrics(readings):

    result = {
        "iaq": 0,
        "temperature": 0,
        "humidity": 0,
        "noise": 0,
        "tvoc": 0,
        "pm25": 0,
        "co2": 0,
        "battery": 0
    }

    for reading in readings:

        metric = reading.get("metric")

        try:

            if metric == "indoorAirQuality":
                result["iaq"] = reading["indoorAirQuality"]["score"]

            elif metric == "temperature":
                result["temperature"] = reading["temperature"]["celsius"]

            elif metric == "rawTemperature":
                if result["temperature"] == 0:
                    result["temperature"] = reading["rawTemperature"]["celsius"]

            elif metric == "humidity":
                result["humidity"] = reading["humidity"]["relativePercentage"]

            elif metric == "noise":
                result["noise"] = reading["noise"]["ambient"]["level"]

            elif metric == "tvoc":
                result["tvoc"] = reading["tvoc"]["concentration"]

            elif metric == "pm25":
                result["pm25"] = reading["pm25"]["concentration"]

            elif metric == "co2":
                result["co2"] = reading["co2"]["concentration"]

            elif metric == "battery":
                result["battery"] = reading["battery"]["percentage"]

        except Exception:
            pass

    return result


def get_floor(sensor_name):

    if not sensor_name:
        return "Unknown"

    words = sensor_name.split()

    if len(words) >= 2:

        if words[0].isdigit():
            return f"{words[0]} Floor"

        if words[0].lower() == "ground":
            return "Ground Floor"

    return "Other"


def load_sensor_data():

    latest = dashboard.sensor.getOrganizationSensorReadingsLatest(
        ORG_ID
    )

    devices = {}

    networks = dashboard.organizations.getOrganizationNetworks(
        ORG_ID
    )

    for network in networks:

        try:

            network_devices = dashboard.networks.getNetworkDevices(
                network["id"]
            )

            for device in network_devices:

                devices[device["serial"]] = {

                    "name":
                        device.get(
                            "name",
                            device["serial"]
                        ),

                    "address":
                        device.get(
                            "address",
                            ""
                        ),

                    "model":
                        device.get(
                            "model",
                            ""
                        )
                }

        except Exception:
            continue

    response = []

    for sensor in latest:

        serial = sensor.get("serial")

        metrics = extract_metrics(
            sensor.get("readings", [])
        )

        device = devices.get(
            serial,
            {}
        )

        sensor_name = device.get(
            "name",
            serial
        )

        response.append({

            "serial": serial,

            "name": sensor_name,

            "floor": get_floor(
                sensor_name
            ),

            "network":
                sensor.get(
                    "network",
                    {}
                ).get(
                    "name",
                    "Unknown"
                ),

            "model":
                device.get(
                    "model",
                    ""
                ),

            "address":
                device.get(
                    "address",
                    ""
                ),

            "iaq":
                metrics["iaq"],

            "temperature":
                metrics["temperature"],

            "humidity":
                metrics["humidity"],

            "noise":
                metrics["noise"],

            "tvoc":
                metrics["tvoc"],

            "pm25":
                metrics["pm25"],

            "co2":
                metrics["co2"],

            "battery":
                metrics["battery"]
        })

    return response

from datetime import datetime, timedelta
@app.route("/api/history")
def history():

    days = min(
        int(request.args.get("days", 1)),
        3
    )

    end_time = datetime.utcnow()

    start_time = (
        end_time -
        timedelta(days=days)
    )

    readings = dashboard.sensor.getOrganizationSensorReadingsHistory(
        ORG_ID,
        t0=start_time.isoformat() + "Z",
        t1=end_time.isoformat() + "Z"
    )

    history = []

    for item in readings:

        metric = item.get("metric")

        value = None

        try:

            if metric == "indoorAirQuality":

                value = item["indoorAirQuality"]["score"]

            elif metric == "temperature":

                value = item["temperature"]["celsius"]

            elif metric == "humidity":

                value = item["humidity"]["relativePercentage"]

            elif metric == "co2":

                value = item["co2"]["concentration"]

            else:

                continue

            history.append({

                "timestamp": item["ts"],
                "metric": metric,
                "value": value

            })

        except Exception:

            continue

    return jsonify(history)
@app.route("/")
def home():
    return "ASB Meraki Dashboard API Running"


@app.route("/api/health")
def health():
    return {
        "status": "UP"
    }


@app.route("/api/sensors")
def sensors():
    return jsonify(
        load_sensor_data()
    )


@app.route("/api/summary")
def summary():

    sensors = load_sensor_data()

    count = len(sensors)

    if count == 0:
        return jsonify({})

    return jsonify({

        "sensorCount":
            count,

        "avgIAQ":
            round(
                sum(
                    s["iaq"]
                    for s in sensors
                ) / count,
                1
            ),

        "avgTemperature":
            round(
                sum(
                    s["temperature"]
                    for s in sensors
                ) / count,
                1
            ),

        "avgHumidity":
            round(
                sum(
                    s["humidity"]
                    for s in sensors
                ) / count,
                1
            ),

        "avgCO2":
            round(
                sum(
                    s["co2"]
                    for s in sensors
                ) / count,
                1
            )
    })


@app.route("/api/toprooms")
def top_rooms():

    sensors = sorted(
        load_sensor_data(),
        key=lambda x: x["iaq"],
        reverse=True
    )

    return jsonify(
        sensors[:5]
    )


@app.route("/api/worstrooms")
def worst_rooms():

    sensors = sorted(
        load_sensor_data(),
        key=lambda x: x["iaq"]
    )

    return jsonify(
        sensors[:5]
    )


@app.route("/api/floors")
def floors():

    sensors = load_sensor_data()

    floor_map = {}

    for sensor in sensors:

        floor = sensor["floor"]

        if floor not in floor_map:

            floor_map[floor] = {
                "total": 0,
                "count": 0
            }

        floor_map[floor]["total"] += sensor["iaq"]

        floor_map[floor]["count"] += 1

    response = []

    for floor, data in floor_map.items():

        response.append({

            "floor": floor,

            "iaq":
                round(
                    data["total"] /
                    data["count"],
                    1
                )
        })

    return jsonify(response)


if __name__ == "__main__":

    app.run(
        host="0.0.0.0",
        port=8080,
        debug=True
    )