import json
import logging
import sys
import traceback

from har_client import run_poll

import import_declare_test
from solnlib import conf_manager, log
from splunklib import modularinput as smi

ADDON_NAME = "haringester_addon_for_splunk"


def logger_for_input(input_name: str) -> logging.Logger:
    return log.Logs().get_logger(f"{ADDON_NAME.lower()}_{input_name}")


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


class Input(smi.Script):
    def __init__(self):
        super().__init__()

    def get_scheme(self):
        scheme = smi.Scheme("har_ingester")
        scheme.description = "har_ingester input"
        scheme.use_external_validation = True
        scheme.streaming_mode_xml = True
        scheme.use_single_instance = False
        scheme.add_argument(
            smi.Argument(
                "name", title="Name", description="Name", required_on_create=True
            )
        )
        return scheme

    def validate_input(self, definition: smi.ValidationDefinition):
        return

    def stream_events(self, inputs: smi.InputDefinition, event_writer: smi.EventWriter):
        # inputs.inputs is a Python dictionary object like:
        # {
        #   "har_ingester://<input_name>": {
        #     "account": "<account_name>",
        #     "disabled": "0",
        #     "host": "$decideOnStartup",
        #     "index": "<index_name>",
        #     "interval": "<interval_value>",
        #     "python.version": "python3",
        #   },
        # }
        for input_name, input_item in inputs.inputs.items():
            normalized_input_name = input_name.split("/")[-1]
            logger = logger_for_input(normalized_input_name)
            try:
                session_key = self._input_definition.metadata["session_key"]
                log_level = conf_manager.get_log_level(
                    logger=logger,
                    session_key=session_key,
                    app_name=ADDON_NAME,
                    conf_name=f"{ADDON_NAME}_settings",
                )
                logger.setLevel(log_level)
                log.modular_input_start(logger, normalized_input_name)
                account_name = input_item.get("account")
                account_config = get_account_config(session_key, logger).get(
                    account_name
                )
                access_token = account_config.get("access_token")
                o11y_realm = account_config.get("so_realm")
                o11y_url = f"https://api.{o11y_realm}.signalfx.com"
                synthetics_test_id = input_item.get("requestedId")
                synthetics_runlocation = input_item.get("run_location")

                config = {
                    "o11y_url": o11y_url,
                    "access_token": access_token,
                    "synthetics_test_id": synthetics_test_id,
                    "synthetics_runlocation": synthetics_runlocation,
                }

                data = run_poll(config, logger)

                sourcetype = "splunk:synthetics:har"
                if len(data) > 0:
                    for line in data:
                        event_writer.write_event(
                            smi.Event(
                                data=json.dumps(line, ensure_ascii=False, default=str),
                                index=input_item.get("index"),
                                sourcetype=sourcetype,
                            )
                        )
                    log.events_ingested(
                        logger,
                        input_name,
                        sourcetype,
                        len(data),
                        input_item.get("index"),
                    )
                    log.modular_input_end(logger, input_name)
                else:
                    logger.warn("No data found.")
            except Exception as e:
                logger.error(
                    f"Exception raised while ingesting data for "
                    f"har_ingester: {e}. Traceback: "
                    f"{traceback.format_exc()}"
                )


if __name__ == "__main__":
    exit_code = Input().run(sys.argv)
    sys.exit(exit_code)
