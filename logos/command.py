from abc import ABC, abstractmethod
from logos.context import context
from argparse import ArgumentParser


class AbstractCommand(ABC):

    argument_parser = ArgumentParser(
        description="Logos command tools"
    )

    def define_arguments(self):
        pass

    @property
    def arguments(self):
        self.define_arguments()
        return self.argument_parser.parse_known_args()[0]

    @abstractmethod
    def execute(self):
        raise NotImplementedError('Please implement it!')


class DelegateCommand(AbstractCommand):

    def __init__(self, commands: dict):
        self.commands = commands

    def define_arguments(self):
        self.argument_parser.add_argument(
            '--command',
            help='type a command to execute',
            choices=self.commands.keys(),
            required=True
        )

    def execute(self):
        command: AbstractCommand = context.get(self.commands[self.arguments.command])
        command.execute()
