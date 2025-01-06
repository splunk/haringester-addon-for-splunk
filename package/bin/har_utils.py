import import_declare_test
from solnlib import conf_manager, log
from splunklib import modularinput as smi
import json, requests, sys, traceback

ADDON_NAME = "haringester_addon_for_splunk"


def get_account_config(session_key: str, logger):
    try:
        cfm = conf_manager.ConfManager(
            session_key,
            ADDON_NAME,
            realm=f"__REST_CREDENTIAL__#{ADDON_NAME}#configs/conf-haringester_addon_for_splunk_account",
        )
        account_conf_file = cfm.get_conf("haringester_addon_for_splunk_account")
        return account_conf_file
    except Exception:
        logger.error(
            f"Error occurred while reading haringester_addon_for_splunk_account.conf - {traceback.print_exc()}"
        )
        return None


def make_session(header):
    with requests.Session() as session:
        session.headers = header
        return session


def fetch_data(session: requests.Session, url, params, logger) -> dict:
    try:
        response = session.get(url, params=params)
        # if response.status_code not in (200, 201):
        #    return None

        response.raise_for_status()

        return response.json()

    except requests.exceptions.HTTPError as e:
        logger.error(f"HTTP error occurred: {e}")
        sys.exit()

    except Exception:
        logger.error(
            f"Failure occurred while connecting to {url}.\nTraceback: {traceback.format_exc()}"
        )
        sys.exit()
    return None


def write_events(data, config, logger, event_writer):
    sourcetype = config.get("sourcetype")
    index_name = config.get("index")
    input_name = config.get("input_name")
    source = config.get("platform")
    if len(data) > 0:
        for line in data:
            if len(line) >= 10000:
                testName = line["synthetics_detail"]["name"]
                resource = line["request"]["url"]
                logger.debug(
                    f"Truncation will occur for {testName} and resource {resource}."
                )
            ts = line.get("startedDateTime")
            event_writer.write_event(
                smi.Event(
                    data=json.dumps(line, ensure_ascii=False, default=str),
                    index=index_name,
                    source=source,
                    sourcetype=sourcetype,
                    time=ts,
                )
            )
        log.events_ingested(
            logger,
            input_name,
            sourcetype,
            len(data),
            index_name,
        )

    else:
        logger.warn("No data found.")
