import sys
import multiprocessing
import argparse
from com_window.main import comWindow
from PyQt5 import QtWidgets
from main_window.main import MainApp
from connections.debug.debug_connection_factory import DebugConnectionFactory
from profiles.rockets.tantalus import tantalus
from util.self_test import SelfTest

if __name__ == "__main__":
    # Pyinstaller fix https://stackoverflow.com/questions/32672596/pyinstaller-loads-script-multiple-times
    multiprocessing.freeze_support()

    parser = argparse.ArgumentParser()

    parser.add_argument("-t", "--self-test", action='store_true')

    args, unparsed_args = parser.parse_known_args()

    # QApplication expects the first argument to be the program name.
    qt_args = sys.argv[:1] + unparsed_args
    app = QtWidgets.QApplication(qt_args)

    if not args.self_test:
        # Open com_window dialog to get startup details
        com_window = comWindow()
        com_window.show()
        return_code = app.exec_()
        if return_code != 0 or com_window.chosen_rocket is None or com_window.chosen_connection is None:
            sys.exit(return_code)

        rocket = com_window.chosen_rocket
        connection = com_window.chosen_connection

    else:
        rocket = tantalus
        connection = DebugConnectionFactory().construct(rocket=rocket)
        test = SelfTest()
        test.start()

    main_window = MainApp(connection, rocket)
    main_window.show()
    return_code = app.exec_()
    sys.exit(return_code)

