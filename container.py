import pylxd
import logging
import asyncio
import psutil
import functools
import copy
from bitmath import Byte
from concurrent.futures import ThreadPoolExecutor
from faker import Faker
from fakerproviders import GreekMythologicalFiguresProvider


class ContainerPool:

    def __init__(self, config, size=1, max_size=5):
        self.__size = size
        self.__max_size = max_size
        self.__logger = logging.getLogger(self.__class__.__name__)
        self.__logger.setLevel(logging.INFO)
        self.__container_pool = list()
        self.__stopped = False
        self.__config = config
        self.__faker = Faker()
        self.__faker.add_provider(GreekMythologicalFiguresProvider)

    async def run(self):
        self.__logger.info("Starting")
        try:
            await self.print_pool_infos()
            while not self.__stopped:
                total_containers = len(await AsyncContainer.all())
                needed_containers = max(0, min(self.__max_size - total_containers, self.__size - len(self)))
                if needed_containers:
                    self.__logger.info("Creation of {} new container(s)".format(needed_containers))
                    new_containers = [self.push(self.gen_hostname()) for _ in range(needed_containers)]
                    # TODO custom exceptions
                    await asyncio.gather(*new_containers)
                    await self.print_pool_infos()
                await asyncio.sleep(1)
        except asyncio.CancelledError:
            self.__logger.info("Stopping")
            self.__logger.info("Waiting for threads to shutdown")
            self.__logger.info("Cleaning up")
            await ContainerPool.clean_up()

    def stop(self):
        self.__stopped = True

    async def push(self, name):
        config = copy.deepcopy(self.__config)
        config.update({'name': name})
        new_container = await AsyncContainer.create(config)
        if new_container:
            await new_container.up()
            self.__container_pool.append(new_container)
        else:
            self.__logger.error("Failed to push new container")

    @staticmethod
    async def clean_up():
        containers_to_down = [container.down() for container in await AsyncContainer.all()]
        await asyncio.gather(*containers_to_down)

    def pull(self):
        if len(self):
            container = self.__container_pool.pop()
            return container

    def gen_hostname(self):
        return '{}-{}'.format(self.__faker.gods_and_spirits().lower(), self.__faker.random_number(digits=5, fix_len=True))

    async def print_pool_infos(self):
        total_containers = len(await AsyncContainer.all())
        self.__logger.info(
            "Pool {} | Total LXC : {}/{} - host memory : {}".format(len(self), total_containers, self.__max_size, Byte(
                psutil.virtual_memory().available).best_prefix()))
        if total_containers == self.__max_size:
            self.__logger.warning("Max container limit reached")

    def __len__(self):
        return len(self.__container_pool)


class AsyncContainer:
    __lxd_client = pylxd.Client()

    def __init__(self, container):
        self.ip = None
        self.__container = container
        self.__lock = asyncio.Lock()
        self.__logger = logging.getLogger(container.name)
        self.__logger.setLevel(logging.INFO)
        self.__thread_pool = ThreadPoolExecutor(max_workers=1)

    @classmethod
    async def create(cls, config):
        logger = logging.getLogger(config['name'])
        logger.setLevel(logging.INFO)
        logger.info('Creating container')
        try:
            new_container = await asyncio.get_running_loop().run_in_executor(None,
                                                                             functools.partial(pylxd.models.Container.create,
                                                                                               cls.__lxd_client, config,
                                                                                               wait=True, target=None))
        except pylxd.exceptions.NotFound as e:
            logger.critical(e)
            return

        return cls(new_container)

    @classmethod
    async def all(cls):
        all_containers = await asyncio.get_running_loop().run_in_executor(None,
                                                                          functools.partial(pylxd.models.Container.all,
                                                                                            cls.__lxd_client))
        return [AsyncContainer(container) for container in all_containers if 'user.proxy' in container.config]

    @classmethod
    async def get(cls, name):
        container = await asyncio.get_running_loop().run_in_executor(None,
                                                                     functools.partial(pylxd.models.Container.get, name))
        return cls(container)

    async def start(self, timeout=30, force=True):
        async with self.__lock:
            self.__logger.info('Starting container')
            try:
                return await asyncio.get_running_loop().run_in_executor(self.__thread_pool,
                                                                        functools.partial(self.__container.start,
                                                                                          timeout,
                                                                                          force, wait=True))
            except pylxd.exceptions.LXDAPIException as e:
                self.__logger.error(e)

    async def stop(self, timeout=30, force=True):
        async with self.__lock:
            self.__logger.info("Stopping container")
            try:
                return await asyncio.get_running_loop().run_in_executor(self.__thread_pool,
                                                                        functools.partial(self.__container.stop,
                                                                                          timeout,
                                                                                          force, wait=True))
            except pylxd.exceptions.LXDAPIException as e:
                self.__logger.error(e)

    async def delete(self):
        async with self.__lock:
            self.__logger.info("Deleting container")
            try:
                return await asyncio.get_running_loop().run_in_executor(self.__thread_pool,
                                                                        functools.partial(self.__container.delete,
                                                                                          wait=True))
            except pylxd.exceptions.LXDAPIException as e:
                self.__logger.error(e)

    async def up(self):
        await self.start()
        await self.get_ipv4()

    async def down(self):
        await self.stop()
        await self.delete()

    async def state(self):
        return await asyncio.get_running_loop().run_in_executor(None,
                                                                functools.partial(self.__container.state))

    async def get_ipv4(self, interface="eth0", timeout=60):
        # TODO improvements needed
        while timeout:
            try:
                for address in (await self.state()).network[interface]['addresses']:
                    if address['family'] == 'inet':
                        self.ip = address['address']
                        self.__logger.info("Container online")
                        return self.ip
            except KeyError:
                await asyncio.sleep(0.5)
                timeout -= 1
        self.__logger.warning("Failed to get an ipv4 address")

    def __getattr__(self, item):
        return self.__container.__getattribute__(item)
