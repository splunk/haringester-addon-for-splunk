from har_utils import write_events, make_session, fetch_data
from datetime import datetime
import sys

EPOCH = datetime(1970, 1, 1)


class ThousandEyes:
    """
    This class handles all API requests for Thousand Eyes Web Transactions
    """

    def __init__(self, config, logger) -> None:
        self.access_token = config["access_token"]
        self.header = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.access_token}",
        }
        self.api_endpoint = config["api_endpoint"]
        self._logger = logger

    def get_har(self, session, test_id, page) -> list:
        har_results = []
        har_endpoints = []

        agent_id = page.get("agentId")
        round = page.get("roundId")
        page_num = page.get("pageNum")

        for p in range(0, page_num):
            har_endpoint = f"/test-results/{test_id}/web-transactions/agent/{agent_id}/round/{round}/page/{p}"
            har_url = f"{self.api_endpoint}{har_endpoint}"
            har_endpoints.append(har_url)

        for ep in har_endpoints:
            self._logger.debug(f"get_har looking for endpoint: {ep}")
            data = fetch_data(session, ep, "", self._logger)

            test_name = data["test"]["testName"]
            for result in data["results"]:
                deep_link = result["_links"]["appLink"]["href"]
                location = result["agent"]["agentName"]

                har = result["har"]["log"]

                for request in har["entries"]:
                    if "postData" in request["request"]:
                        request["request"]["postData"] = "REMOVED"
                    start_time = (
                        datetime.strptime(
                            request["startedDateTime"], "%Y-%m-%dT%H:%M:%S.%fZ"
                        )
                        - EPOCH
                    )
                    start_time_epoch = int(start_time.total_seconds())
                    request["startedDateTime"] = start_time_epoch
                    request["transaction_details"] = {
                        "id": test_id,
                        "name": test_name,
                        "location": location,
                        "run_time": round,
                        "deep_link": deep_link,
                    }

                    har_results.append(request)
        return har_results

    def get_page_count(self, session, testId, results) -> list:
        pages = []
        for result in results:
            agentId = result.get("agentId")
            round = result.get("roundId")
            pages_url = f"{self.api_endpoint}/test-results/{testId}/web-transactions/agent/{agentId}/round/{round}"
            get_page = fetch_data(session, pages_url, "", self._logger)
            for pr in get_page["results"]:
                pageNum = 1
                for page_list in pr["pages"]:
                    pageNum += page_list.get("pageNum")

                pages.append({"agentId": agentId, "roundId": round, "pageNum": pageNum})
        self._logger.debug(f"get_page_count returns: {pages}")
        return pages

    def get_test_results(self, session, testId) -> list:
        results_endpoint = f"/test-results/{testId}/web-transactions"
        results_url = f"{self.api_endpoint}{results_endpoint}"
        result_data = fetch_data(session, results_url, "", self._logger)
        agent_data = []
        for result in result_data["results"]:
            agent_data.append(
                {
                    "agentId": result["agent"].get("agentId"),
                    "agentName": result["agent"].get("agentName"),
                    "roundId": result.get("roundId"),
                }
            )
        return agent_data

    def get_tests(self, session) -> list:
        web_transactions_endpoint = "/tests/web-transactions"
        web_transactions_url = f"{self.api_endpoint}{web_transactions_endpoint}"
        web_transaction_data = fetch_data(
            session, web_transactions_url, "", self._logger
        )
        my_data = []
        if "tests" in web_transaction_data:
            for test in web_transaction_data["tests"]:

                my_data.append(
                    {
                        "testId": test.get("testId"),
                        "testName": test.get("testName"),
                    }
                )
            return my_data


def get_web_transactions(checkpointer, config, logger, event_writer):
    client = ThousandEyes(config, logger)
    session = make_session(client.header)

    test_inventory = client.get_tests(session)

    if not test_inventory:
        logger.error("No active checks found.")
        sys.exit()
    for test in test_inventory:
        test_id = test.get("testId")
        results = client.get_test_results(session, test_id)
        pages = client.get_page_count(session, test_id, results)

        for page in pages:
            transaction_location_id = page.get("agentId", 0)
            transaction_round = page.get("roundId", 0)

            checkpoint_name = f"{test_id}_{transaction_location_id}"
            recent_checkpoint = checkpointer.get(checkpoint_name)
            logger.debug(f"Checkpoint data: {recent_checkpoint}")

            if recent_checkpoint is not None:
                recent_checkpoint = recent_checkpoint.get("checkpoint")
            else:
                recent_checkpoint = 0

            logger.debug(
                f"web_transaction_lastrun={transaction_round} recent_checkpoint={recent_checkpoint}"
            )

            if transaction_round > recent_checkpoint:
                data = client.get_har(session, test_id, page)
                write_events(data, config, logger, event_writer)
                checkpointer.update(checkpoint_name, {"checkpoint": transaction_round})

            else:
                logger.debug(
                    f"Already written data for test={test_id} location={transaction_location_id} runtime={transaction_round}"
                )
    session.close()
