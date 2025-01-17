import requests, sys, time, traceback
from datetime import datetime
from har_utils import write_events, make_session, fetch_data

EPOCH = datetime(1970, 1, 1)

NOW_EPOCH = int(time.time())
LAST_HALF_HOUR = int(NOW_EPOCH - 1800)


class SplunkSynthetics:
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
        self.select_tests = config["select_tests"]
        self._logger.debug(f"tests={self.select_tests}")

    def get_artifacts(self, session: requests.Session, active_tests: dict) -> list:
        """
        This function queries the Artifacts endpoint for each possible location for the runtime given
        """
        test_id = active_tests.get("test_id")
        run_epoch = active_tests.get("last_test_run")
        location_list = active_tests.get("location_list")

        for location in location_list:
            artifact_url = f"{self.o11y_url}/v2/synthetics/tests/{test_id}/artifacts?locationId={location}&timestamp={run_epoch}"

            artifacts = fetch_data(session, artifact_url, "", self._logger)

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

        har_data = fetch_data(session, full_har_url, "", self._logger)

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
            {
                "page_ref": page["id"],
                "page_url": page["title"],
                "startedDateTime": synthetics_detail_run_time,
                "web_vitals": page["_webVitals"],
            }
            for page in har_data["log"]["pages"]
        ]

        btransaction_data = []
        if har_data["log"]["_groupData"]:
            btransaction_data = [
                {
                    "pos": step["position"],
                    "name": step["name"],
                }
                for step in har_data["log"]["_groupData"]
            ]

        har_data_arr = []
        for page_data in har_page_data:
            har_data_arr.append(page_data)
        # The "entries" section in the HAR file is where each request is stored
        for request in har_data["log"]["entries"]:
            start_time = (
                datetime.strptime(request["startedDateTime"], "%Y-%m-%dT%H:%M:%S.%fZ")
                - EPOCH
            )
            start_time_epoch = int(start_time.total_seconds())

            page_url = next(
                (
                    page["page_url"]
                    for page in har_page_data
                    if page["page_ref"] == request["pageref"]
                ),
                "",
            )

            business_transaction = ""

            if "_btref" in request:
                business_transaction = next(
                    (
                        bt["name"]
                        for bt in btransaction_data
                        if bt["pos"] == request["_btref"]
                    ),
                    "",
                )

            if "postData" in request["request"]:
                request["request"]["postData"] = "REMOVED"
            # Splunk Synthetics adds additional job-related fields that don't appear to provide value.
            # To keep it consistent, I'm adding standard components only.
            har_data_dict = {
                "business_transaction": business_transaction,
                "page_url": page_url,
                "pageref": request["pageref"],
                "request": request["request"],
                "response": request["response"],
                "serverIPAddress": request.get("serverIPAddress", ""),
                "startedDateTime": start_time_epoch,
                "transaction_details": {
                    "id": test_id,
                    "name": test_name,
                    "location": synthetics_detail_location,
                    "org_id": self.org_id,
                    "realm": self.realm,
                    "run_time": synthetics_detail_run_time,
                    "deep_link": deep_link,
                },
                "time": request["time"],
                "timings": request["timings"],
            }

            har_data_arr.append(har_data_dict)
        # Each dict holding each request is then put back in to a giant list and returned

        return har_data_arr

    def get_active_checks(self, session: requests.Session) -> list:
        """
        Returns all active Browser tests as dict objects in a list
        """
        test_list = []
        next_page = 1
        checks_url = f"{self.o11y_url}/v2/synthetics/tests"
        params = {"active": True, "testType": "browser", "page": next_page}
        self._logger.debug(f"next page at initial call is {next_page}")
        while next_page > 0:
            response = fetch_data(session, checks_url, params, self._logger)

            if not response.get("tests"):
                return None

            if "tests" in response:
                if not response.get("nextPageLink"):
                    next_page = 0
                else:
                    next_page = response.get("nextPageLink")
                self._logger.debug(f"next page after api call is {next_page}")
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


def run_poll(checkpointer, config, logger, event_writer):
    """
    Main function that creates a Splunk Synthetics object
    """
    client = SplunkSynthetics(config, logger)
    session = make_session(client.header)
    get_active = client.get_active_checks(session)

    select_tests_only = config.get("select_tests")
    if not get_active:
        logger.error("No active checks found.")
        sys.exit()

    # For each active check, find available artifacts
    for test in get_active:
        test_name = test.get("test_name")
        if select_tests_only and test_name not in select_tests_only:
            continue
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

                data = client.get_har(session, test_id, test_name, har_url)

                write_events(data, config, logger, event_writer)

                checkpointer.update(checkpoint_name, {"checkpoint": synthetics_lastrun})
            else:
                logger.debug(
                    f"Already written data for test={test_id} location={har_url[1]} runtime={synthetics_lastrun}"
                )
    session.close()
