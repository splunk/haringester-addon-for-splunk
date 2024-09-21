import requests, sys, time, traceback
from datetime import datetime
from har_utils import write_events

EPOCH = datetime(1970, 1, 1)

NOW_EPOCH = int(time.time())
LAST_HALF_HOUR = int(NOW_EPOCH - 1800)


class HarIngester(object):
    """
    This class is an object that contains all API requests required to get a HAR file
    """

    def __init__(self, config, logger) -> None:
        self.access_token = config["access_token"]
        self.header = {
            "Content-Type": "application/json",
            "X-SF-TOKEN": self.access_token,
        }
        self.o11y_url = config["o11y_url"]
        self.org_id = config["org_id"]
        self.realm = config["realm"]
        self._logger = logger
        self._counter = 1

    def make_session(self):
        with requests.Session() as s:
            s.headers = self.header
            return s

    def fetch_data(self, session: requests.Session, url, params) -> dict:
        try:
            response = session.get(url, params=params)
            # if response.status_code not in (200, 201):
            #    return None

            response.raise_for_status()
            self._counter += 1
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

    def get_artifacts(self, session: requests.Session, active_tests: dict) -> list:
        """
        This function queries the Artifacts endpoint for each possible location for the runtime given
        """
        test_id = active_tests.get("test_id")
        run_epoch = active_tests.get("last_test_run")
        location_list = active_tests.get("location_list")

        for location in location_list:
            artifact_url = f"{self.o11y_url}/v2/synthetics/tests/{test_id}/artifacts?locationId={location}&timestamp={run_epoch}"

            artifacts = self.fetch_data(session, artifact_url, "")

            if not artifacts.get("artifacts"):
                continue
            self._logger.debug(f"Artifacts found: {artifacts}")

            for artifact in artifacts.get("artifacts"):
                if artifact.get("type") != "har":
                    continue

                self._logger.debug(f"Found har artifact: {artifact['url']}")

                artifact["location"] = location
                # Returns the artifact URL, corresponding Synthetics location, and Synthetics run time in epoch as a list

                return [artifact["url"], artifact["location"], run_epoch]

        self._logger.debug(f"No artifacts found for {test_id} and {run_epoch}.")
        return None

    def get_har(
        self, session: requests.Session, test_id: int, test_name: str, har_url: list
    ) -> list:
        """
        This function fetches the HAR file from the url collected in the get_artifacts function
        """
        full_har_url = f"{self.o11y_url}{har_url[0]}"

        har_data = self.fetch_data(session, full_har_url, "")

        if not har_data:
            sys.exit()

        synthetics_detail_location = har_url[1]
        synthetics_detail_run_time = har_url[2]
        deep_link = f"https://app.{self.realm}.signalfx.com/#/synthetics/run/browser/{test_id}/{synthetics_detail_location}/{synthetics_detail_run_time}"

        if self.org_id:
            deep_link = f"{deep_link}?orgID={self.org_id}"

        # The below code extracts required elements from the HAR file to store in a dict to ingest in to Splunk

        # This extracts each page reference (i.e page 1 in the Synthetic check) and it's url
        har_page_data = [
            {"page_ref": page["id"], "page_url": page["title"]}
            for page in har_data["log"]["pages"]
        ]

        har_data_arr = []
        # The "entries" section in the HAR file is where each request is stored
        for request in har_data["log"]["entries"]:
            start_time = (
                datetime.strptime(request["startedDateTime"], "%Y-%m-%dT%H:%M:%S.%fZ")
                - EPOCH
            )
            start_time_epoch = int(start_time.total_seconds() * 1000)
            har_data_dict = {
                "time": start_time_epoch,
                "resource": request["request"]["url"],
                "content_type": request["response"]["content"].get("mimeType", ""),
                "content_size": request["response"]["content"].get("size", 0),
                "http_method": request["request"]["method"],
                "http_status": request["response"]["status"],
                "http_status_description": request["response"]["statusText"],
                "page_ref": request["pageref"],
                "page_url": next(
                    (
                        page["page_url"]
                        for page in har_page_data
                        if page["page_ref"] == request["pageref"]
                    ),
                    "",
                ),
                "redirect_url": request["response"].get("redirectURL", ""),
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
                "time_taken": request["time"],
                "synthetics_detail": {
                    "id": test_id,
                    "name": test_name,
                    "location": synthetics_detail_location,
                    "org_id": self.org_id,
                    "realm": self.realm,
                    "run_time": synthetics_detail_run_time,
                    "deep_link": deep_link,
                },
            }

            har_data_arr.append(har_data_dict)
        # Each dict holding each request is then put back in to a giant list and returned

        return har_data_arr

    def get_active_checks(self, session: requests.Session) -> list:
        """
        Returns all active Browser tests as dict objects in a list
        """

        checks_url = f"{self.o11y_url}/v2/synthetics/tests"
        params = {"active": True, "testType": "browser", "lastRunStatus": "success"}

        response = self.fetch_data(session, checks_url, params)
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
                                - EPOCH
                            ).total_seconds()
                            * 1000
                        ),
                        "location_list": test["locationIds"],
                    }
                )

        return test_list

    def get_counter(self):
        return self._counter

    def reset_counter(self):
        self._counter = 1


def run_poll(checkpointer, config, logger, event_writer):
    """
    Main function that creates a HARIngester object
    """
    client = HarIngester(config, logger)
    session = client.make_session()

    get_active = client.get_active_checks(session)

    if not get_active:
        logger.error("No active checks found.")
        sys.exit()

    # For each active check, find available artifacts
    for test in get_active:
        har_url = client.get_artifacts(session, test)

        # If the HAR artifact exists, get artifact and write it to Splunk
        if har_url:
            test_id = test.get("test_id")

            synthetics_location = har_url[1]
            synthetics_lastrun = har_url[2]
            checkpoint_name = f"{test_id}_{synthetics_location}"

            recent_checkpoint = checkpointer.get(checkpoint_name)
            logger.debug(f"Checkpoint data: {recent_checkpoint}")

            if recent_checkpoint is not None:
                recent_checkpoint = recent_checkpoint.get("checkpoint")
            else:
                recent_checkpoint = 0

            logger.debug(
                f"synthetics_lastrun={synthetics_lastrun} recent_checkpoint={recent_checkpoint}"
            )

            if synthetics_lastrun > recent_checkpoint:
                test_id = test.get("test_id")
                test_name = test.get("test_name")
                data = client.get_har(session, test_id, test_name, har_url)

                write_events(data, config, logger, event_writer)

                checkpointer.update(checkpoint_name, {"checkpoint": synthetics_lastrun})
            else:
                logger.debug(
                    f"Already written data for test={test_id} location={har_url[1]} runtime={synthetics_lastrun}"
                )
            counter = client.get_counter()
            logger.debug(
                f"For test={test_id} at location={synthetics_location}, there were count={counter} API calls"
            )
            client.reset_counter()
    session.close()
