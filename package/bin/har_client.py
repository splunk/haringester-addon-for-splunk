import requests, sys, time, traceback
from datetime import datetime

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
        self.synthetics_test_id = config["synthetics_test_id"]
        self.synthetics_runlocation = config["synthetics_runlocation"]
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

    def get_run_time(self, check_name) -> list:
        runtimes_url = f"{self.o11y_url}/v1/timeserieswindow?resolution=1000&startMs={LAST_HALF_HOUR}000&endMS={NOW_EPOCH}000&query=(sf_metric%3Asynthetics.run.duration.time.ms)%20AND%20(test_id%3A{self.synthetics_test_id})%20AND%20(location_id%3A{self.synthetics_runlocation})%20AND%20(sf_product%3Asynthetics)"
        test_list = []
        self._logger.debug(
            f"Collecting run times for {self.synthetics_test_id} using {runtimes_url}"
        )
        get_run_time = self.fetch_data(runtimes_url, "")
        if not get_run_time:
            self._logger.warning(f"No run data found, exiting.")
            sys.exit()
        if not get_run_time.get("data"):
            self._logger.warning(f"No run data found for {LAST_HALF_HOUR}, exiting.")
            sys.exit()
        for k, v in get_run_time["data"].items():

            ts = int(v[-1][0])
            test_list.append(
                {
                    "test_id": self.synthetics_test_id,
                    "test_name": check_name,
                    "last_test_run": ts,
                    "location_list": [self.synthetics_runlocation],
                }
            )
            return test_list

    def get_artifacts(self, active_tests: dict) -> list:
        test_id = active_tests.get("test_id")
        run_epoch = active_tests.get("last_test_run")
        location_list = active_tests.get("location_list")
        artifact_list = self.batch_location_artifacts(test_id, location_list, run_epoch)

        """
        for test in active_tests.get("location_list"):
            synthetics_runlocation = test
            artifacts_url = f"{self.o11y_url}/v2/synthetics/tests/{test_id}/artifacts?locationId={synthetics_runlocation}&timestamp={run_epoch}"
            artifacts_req = self.fetch_data(artifacts_url, "")
            artifact_list = artifacts_req

            if not artifact_list.get("artifacts"):
                continue
        """
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

        if not response.get("tests"):
            return None

        if "tests" in response:
            test_list = []
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

    def get_single_test(self) -> str:

        test_url = (
            f"{self.o11y_url}/v2/synthetics/tests/browser/{self.synthetics_test_id}"
        )
        browser_check = self.fetch_data(test_url, "")
        if not browser_check:
            self._logger.warning(
                "Check not found - please check Synthetics configuration in Splunk Observability Cloud"
            )
            return None
        if browser_check["test"].get(
            "active"
        ) and self.synthetics_runlocation in browser_check["test"].get("locationIds"):
            check_name = browser_check["test"].get("name")
            self._logger.info(browser_check)
            return f'"{check_name}"'
        else:
            self._logger.warning(
                "Check not active or location not matched - please check Synthetics configuration in Splunk Observability Cloud"
            )
            sys.exit()


def run_poll(config, logger):
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
            return client.get_har(test_id, test_name, har_url)
