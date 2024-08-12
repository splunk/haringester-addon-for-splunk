import requests, sys, time, traceback
from datetime import datetime
from har_utils import write_events

epoch = datetime(1970, 1, 1)

NOW_EPOCH = int(time.time())
LAST_HALF_HOUR = int(NOW_EPOCH - 1800)


class HarIngester(object):

    def __init__(self, config, logger) -> None:
        self.access_token = config["access_token"]
        self.header = {
            "Content-Type": "application/json",
            "X-SF-TOKEN": self.access_token,
        }
        self.o11y_url = config["o11y_url"]
        self._logger = logger

    def batch_location_artifacts(
        self, test_id: int, locations: list, epoch_time: int
    ) -> dict:
        with requests.Session() as s:
            s.headers = self.header
            for location in locations:
                artifact_url = f"{self.o11y_url}/v2/synthetics/tests/{test_id}/artifacts?locationId={location}&timestamp={epoch_time}"
                artifacts_req = s.get(artifact_url)
                artifacts = artifacts_req.json()
                if not artifacts.get("artifacts"):
                    continue
                artifacts["location"] = location
                return artifacts

    def fetch_data(self, url, params) -> dict:
        try:
            response = requests.get(url, headers=self.header, params=params)
            # if response.status_code not in (200, 201):
            #    return None
            response.raise_for_status()
            return response.json()

        except requests.exceptions.HTTPError as e:
            self._logger.error(f"HTTP error occurred: {e}")
            sys.exit()
        except Exception:
            self._logger.error(
                f"Failure occurred while connecting to {url}.\nTraceback: {traceback.format_exc()}"
            )
            sys.exit()
        return None

    def get_artifacts(self, active_tests: dict) -> list:
        test_id = active_tests.get("test_id")
        run_epoch = active_tests.get("last_test_run")
        location_list = active_tests.get("location_list")
        artifact_list = self.batch_location_artifacts(test_id, location_list, run_epoch)

        for artifact in artifact_list["artifacts"]:
            if artifact.get("type") != "har":
                continue
            # if artifact["type"] == "har":
            self._logger.debug(f"Found har artifact: {artifact['url']}")
            return [artifact["url"], artifact_list["location"]]

        return None

    def get_har(self, test_id, test_name, har_url) -> list:
        full_har_url = f"{self.o11y_url}{har_url[0]}"
        har_data = self.fetch_data(full_har_url, "")
        if not har_data:
            sys.exit()

        har_page_data = [
            {"page_ref": page["id"], "page_url": page["title"]}
            for page in har_data["log"]["pages"]
        ]

        har_data_arr = []
        for request in har_data["log"]["entries"]:
            start_time = (
                datetime.strptime(request["startedDateTime"], "%Y-%m-%dT%H:%M:%S.%fZ")
                - epoch
            )
            start_time_epoch = int(start_time.total_seconds() * 1000)
            har_data_dict = {
                "time": start_time_epoch,
                "time_taken": request["time"],
                "test_id": test_id,
                "test_name": test_name,
                "test_location": har_url[1],
                "resource": request["request"]["url"],
                "content_type": request["response"]["content"].get("mimeType", ""),
                "content_size": request["response"]["content"].get("size", 0),
                "http_method": request["request"]["method"],
                "http_status": request["response"]["status"],
                "http_status_description": request["response"]["statusText"],
                "page_ref": request["pageref"],
                "response_headers": (
                    [
                        {header["name"]: header["value"]}
                        for header in request["response"]["headers"]
                    ]
                    if request["response"]["headers"]
                    else ["null"]
                ),
                "response_cookies": request["response"]["cookies"],
                "server_ip": request.get("serverIPAddress", ""),
                "timings": request["timings"],
                "redirect_url": request["response"].get("redirectURL", ""),
                "page_url": next(
                    (
                        page["page_url"]
                        for page in har_page_data
                        if page["page_ref"] == request["pageref"]
                    ),
                    "",
                ),
            }

            har_data_arr.append(har_data_dict)

        return har_data_arr

    def get_active_checks(self) -> list:
        checks_url = f"{self.o11y_url}/v2/synthetics/tests"
        params = {"active": True, "testType": "browser", "lastRunStatus": "success"}

        response = self.fetch_data(checks_url, params)
        test_list = []
        if not response.get("tests"):
            return None

        if "tests" in response:

            for test in response.get("tests"):
                if not test["lastRunAt"]:
                    self._logger.warning(f'No run history for {test["id"]}')
                    continue
                test_list.append(
                    {
                        "test_id": int(test["id"]),
                        "test_name": test["name"],
                        "last_test_run": round(
                            (
                                datetime.strptime(
                                    test["lastRunAt"], "%Y-%m-%dT%H:%M:%S.%fZ"
                                )
                                - epoch
                            ).total_seconds()
                            * 1000
                        ),
                        "location_list": test["locationIds"],
                    }
                )

        return test_list


def run_poll(config, logger, event_writer):
    client = HarIngester(config, logger)
    get_active = client.get_active_checks()
    # get_active = client.get_single_test()
    if not get_active:
        logger.error("No active checks found.")
        sys.exit()
    for test in get_active:
        har_url = client.get_artifacts(test)
        if len(har_url) > 0:
            test_id = test.get("test_id")
            test_name = test.get("test_name")
            data = client.get_har(test_id, test_name, har_url)
            write_events(data, config, logger, event_writer)
