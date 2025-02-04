# -*- coding: utf-8 -*-
# supervisor-alert - Receive notifications for Supervisor process events
# Copyright 2016-2017 Rahiel Kasim
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
import argparse
import shlex
from functools import partial
from os.path import expanduser
from pwd import getpwnam
from socket import gethostname
from subprocess import CalledProcessError, check_call

from supervisor.childutils import listener, get_headers

__version__ = "0.6.2"

telegram_conf_args = ["--config", "/etc/telegram-send.conf"]


def main():
    parser = argparse.ArgumentParser(description="Supervisor event listener to notify on process events.",
                                     epilog="Homepage: https://github.com/rahiel/supervisor-alert")
    parser.add_argument("-c", "--command", help="Specify the command to process the event messages.")
    parser.add_argument("--telegram", help="Use telegram-send to send event messages.", action="store_true")
    parser.add_argument("--configure", help="configure %(prog)s", action="store_true")
    parser.add_argument("--show-hostname", help="show hostname in messages", action="store_true")
    parser.add_argument("--version", action="version", version="%(prog)s {}".format(__version__))
    parser.add_argument("--exclude", help="Comma separated list of processes to exclude")
    args = parser.parse_args()

    if args.configure:
        return configure()

    s = "PROCESS_STATE_"

    hostname = gethostname()

    if args.telegram:
        alert = telegram
    elif args.command:
        alert = partial(send, command=shlex.split(args.command))
    else:
        raise Exception("No command specified.")

    excluded = set()
    if args.exclude:
        for process in args.exclude.split(','):
            excluded.add(process)

    while True:
        headers, payload = listener.wait()
        event_name = headers["eventname"]
        success = True

        if event_name.startswith(s):
            event_name = event_name[len(s):].lower()
            data = get_headers(payload)  # keys: from_state, pid, processname
            process_name = data["processname"]
            message = process_name + " has entered state " + event_name
            if args.show_hostname:
                message = hostname + ": " + message
            if process_name not in excluded:
                success = alert(message=message)

        if success:
            listener.ok()
        else:
            listener.fail()


def telegram(message):
    """Send message with telegram-send."""
    try:
        check_call(["telegram-send", message] + telegram_conf_args)
        return True
    except OSError:     # command not found
        cmd = expanduser("~/.local/bin/telegram-send")
        check_call([cmd, message] + telegram_conf_args)
        return True
    except CalledProcessError:
        return False


def send(command, message):
    """Send message with an arbitrary command."""
    try:
        check_call(command + [message])
        return True
    except CalledProcessError:
        return False


def configure():
    """Automatically set up supervisor-alert."""
    conf = "/etc/supervisor/conf.d/supervisor_alert.conf"

    config = """[eventlistener:supervisor_alert]
command=supervisor-alert --telegram{}
events=PROCESS_STATE_RUNNING,PROCESS_STATE_EXITED,PROCESS_STATE_FATAL
autostart=true
autorestart=true
stdout_logfile=NONE
user=supervisor_alert
"""

    show_hostname = raw_input("Prepend messages with the hostname? [y/n] ").strip().lower()
    if show_hostname == "y":
        config = config.format(" --show-hostname")
    else:
        config = config.format("")

    try:
        with open(conf, "w") as f:
            f.write(config)
    except IOError:
        raise Exception("Can't save config, please execute as root: sudo supervisor-alert --configure")

    try:
        try:
            getpwnam("supervisor_alert")
        except KeyError:
            check_call("adduser supervisor_alert --system --no-create-home".split())

        # restart supervisor
        check_call("supervisorctl reread".split())
        check_call("supervisorctl update".split())
    except CalledProcessError:
        raise Exception("Please retry as root or configure manually: "
                        "https://github.com/rahiel/supervisor-alert#manual-configuration")

    print("Setting up telegram-send...")
    check_call(["telegram-send", "--configure"] + telegram_conf_args)
    print("Supervisor-alert has been set up successfully!")


if __name__ == "__main__":
    main()
