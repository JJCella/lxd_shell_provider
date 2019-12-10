import asyncio
import asyncssh
import logging
import sys
import signal
import functools
import os
import json

from container import ContainerPool
from sshserver import SSHServer

logging.basicConfig(level=logging.INFO,
                    format='%(asctime)-18s %(name)-20s %(levelname)-8s %(message)s',
                    datefmt='%d-%m %H:%M:%S')

os.environ['PYLXD_WARNINGS'] = 'none'
asyncssh.set_log_level(logging.WARNING)

pool = ContainerPool(json.load(open('config/container.json')))

logger = logging.getLogger('main')
logger.setLevel(logging.INFO)

ssh_config = json.load(open('config/container_ssh.json'))


async def handle_client(client_process):
    client_ip = client_process.get_extra_info('peername')[0]
    logger.info("Opening channel for {}".format(client_ip))

    if not client_process.command and not client_process.subsystem:
        container = pool.pull()
        if container:
            logger.info("{} assigned to {} ({})".format(client_ip, container.name, container.ip))
            try:
                async with asyncssh.connect(container.ip, port=ssh_config['port'], username=ssh_config['username'], password=ssh_config['password'],
                                            known_hosts=None) as container_conn:
                    async with container_conn.create_process(encoding=None,
                                                             term_type=client_process.get_terminal_type(),
                                                             term_size=client_process.get_terminal_size()) as container_process:

                        try:
                            await client_process.redirect(
                                stdin=container_process.stdin,
                                stderr=container_process.stderr,
                                stdout=container_process.stdout)
                        except TypeError:  # TerminalSizeChange on stdin
                            pass

                        for f in asyncio.as_completed({client_process.wait_closed(), container_process.wait_closed()}):
                            await f
                            break
            except ConnectionError as e:
                logger.error(e)
            else:
                container_conn.close()
                await container_conn.wait_closed()

            logger.info('{} disconnected (was previously assigned to {})'.format(client_ip, container.name))
            client_process.close()
            await container.down()
            await pool.print_pool_infos()
        else:
            logger.warning(
                "Ooopsi no available container for {} - Closing connection".format(client_ip))
            client_process.stdout.write(
                b'We are sorry but our server is busy - Please try again later - Press enter to continue')
            # client_process.stdin.at_eof()
            client_process.close()
    else:
        logger.warning(
            "Client {} requested command/subsystem - Closing connection".format(client_ip))
        client_process.close()


loop = asyncio.get_event_loop()
# loop.set_debug(True)


def cancel_all_asks():
    tasks = [t for t in asyncio.all_tasks() if t is not
             asyncio.current_task()]
    for task in tasks:
        task.cancel()
        # task.exception()


for signal_name in {'SIGINT', 'SIGTERM'}:
    loop.add_signal_handler(
        getattr(signal, signal_name),
        functools.partial(cancel_all_asks))

try:
    server_config = json.load(open('config/server.json'))
    loop.run_until_complete(asyncssh.create_server(SSHServer, '', port=server_config['port'],
                                                   server_host_keys=server_config['host_keys'],
                                                   keepalive_interval=server_config['keepalive_interval'],
                                                   keepalive_count_max=server_config['keepalive_count_max'],
                                                   login_timeout=server_config['login_timeout'],
                                                   server_version=server_config['server_version'],
                                                   process_factory=handle_client,
                                                   allow_scp=False,
                                                   encoding=None
                                                   )
                            )
    loop.create_task(pool.run())
except (OSError, asyncssh.Error, KeyboardInterrupt) as exc:
    sys.exit('Error starting server: ' + str(exc))

try:
    loop.run_forever()
finally:
    loop.close()
