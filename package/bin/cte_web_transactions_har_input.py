import json
import logging
import sys
import traceback

from cte_web_transactions import get_web_transactions

import import_declare_test
from solnlib import conf_manager, log
from solnlib.modular_input import KVStoreCheckpointer
from splunklib import modularinput as smi
from splunklib import binding

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


class CTE_WEBTRANSACTIONS_HAR(smi.Script):
    def __init__(self):
        super().__init__()

    def get_scheme(self):
        scheme = smi.Scheme("cte_web_transactions_har_input")
        scheme.description = "cte_web_transactions_har_input input"
        scheme.use_external_validation = True
        scheme.streaming_mode_xml = True
        scheme.use_single_instance = False
        scheme.add_argument(
            smi.Argument(
                "name", title="Name", description="Name", required_on_create=True
            )
        )
        scheme.add_argument(
            smi.Argument(
                "account",
                required_on_create=True,
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
        input_items = [{"count": len(inputs.inputs)}]
        for input_name, input_item in inputs.inputs.items():
            normalized_input_name = input_name.split("/")[-1]
            input_item["name"] = input_name
            input_items.append(input_item)
            logger = logger_for_input(normalized_input_name)
            try:
                session_key = inputs.metadata["session_key"]
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
                api_endpoint = f"https://api.thousandeyes.com/v7"

                config = {
                    "api_endpoint": api_endpoint,
                    "access_token": access_token,
                    "index": input_item.get("index"),
                    "input_name": input_name,
                    "sourcetype": "cisco:thousandeyes:har",
                }
                checkpointer = KVStoreCheckpointer(input_name, session_key, ADDON_NAME)
                data = get_web_transactions(checkpointer, config, logger, event_writer)

                log.modular_input_end(logger, input_name)

            except Exception as e:
                logger.error(
                    f"Exception raised while ingesting data for "
                    f"har_ingester: {e}. Traceback: "
                    f"{traceback.format_exc()}"
                )


if __name__ == "__main__":
    exit_code = CTE_WEBTRANSACTIONS_HAR().run(sys.argv)
    sys.exit(exit_code)
