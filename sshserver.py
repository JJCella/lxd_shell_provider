import asyncssh
import logging


class SSHServer(asyncssh.SSHServer):

    __logger = logging.getLogger('SSHServer')
    __logger.setLevel(logging.INFO)

    def connection_made(self, conn):
        pass

    def connection_lost(self, exc):
        pass

    def begin_auth(self, username):
        return True

    def password_auth_supported(self):
        return True

    def validate_password(self, username, password):
        self.__logger.info('Auth username:{} password:{}'.format(username, password))
        return True
