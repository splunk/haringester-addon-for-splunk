import logging
import import_declare_test
from splunktaucclib.rest_handler.error_ctl import RestHandlerError as RH_Err


def run_module(name):
    instance = __import__(name, fromlist=["main"])
    instance.main()


def run_rest_handler(name):
    logging.root.addHandler(logging.NullHandler())
    run_module(name)


if __name__ == "__main__":
    try:
        run_rest_handler("haringester_get_tests")
    except BaseException as exc:
        RH_Err.ctl(-1, exc, logLevel=logging.ERROR, shouldPrint=False)
