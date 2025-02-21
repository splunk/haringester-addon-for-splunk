import logging
import splunk.admin as admin
from solnlib import log
from har_utils import get_account_config, make_session, fetch_data


ADDON_NAME = "haringester_addon_for_splunk"

logger = log.Logs().get_logger(f"{ADDON_NAME.lower()}_get_tests")
logger.setLevel(logging.DEBUG)


class SyntheticTests(admin.MConfigHandler):
    param = "account"

    def setup(self):
        self.supportedArgs.addOptArg(self.param)

    def handleList(self, conf_info):
        next_page = 1
        session_key = self.getSessionKey()
        account_name = getattr(self.callerArgs, "data").get("account")[0]
        account_config = get_account_config(session_key, logger).get(account_name)
        access_token = account_config.get("access_token")
        o11y_realm = account_config.get("so_realm", 0)
        o11y_url = f"https://api.{o11y_realm}.signalfx.com"
        checks_url = f"{o11y_url}/v2/synthetics/tests"
        params = {"active": True, "testType": "browser", "page": next_page}
        header = {
            "Content-Type": "application/json",
            "X-SF-TOKEN": access_token,
        }
        session = make_session(header)

        results = fetch_data(session, checks_url, params, logger)

        if not results.get("tests"):
            return None

        if "tests" in results:
            if not results.get("nextPageLink"):
                next_page = 0
            else:
                next_page = results.get("nextPageLink")
            # logger.debug(f"next page after api call is {next_page}")
            for test in results.get("tests"):

                if not test["lastRunAt"]:
                    logger.warning(f'No run history for {test["id"]}')
                    continue
                test_name = test["name"]

                conf_info[test_name].append("name", test_name)
        # for attr in dir(conf_info):
        #    logger.debug(f"conf_info.{attr}={getattr(conf_info, attr)}")


def main():
    admin.init(SyntheticTests, admin.CONTEXT_NONE)
