import import_declare_test
from solnlib import conf_manager, log
from splunklib import modularinput as smi
import json


def write_events(data, config, logger, event_writer):
    sourcetype = "splunk:synthetics:har"
    index_name = config.get("index")
    input_name = config.get("input_name")
    if len(data) > 0:
        for line in data:
            event_writer.write_event(
                smi.Event(
                    data=json.dumps(line, ensure_ascii=False, default=str),
                    index=index_name,
                    sourcetype=sourcetype,
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
