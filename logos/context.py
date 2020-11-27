from abc import ABC, abstractmethod
from typing import Dict, List, Any, Union
from contextvars import ContextVar
from importlib import import_module
from overload import overload
from re import match, sub


class ContainerException(Exception):

    def __init__(self, message: str):
        self.message = message
        super().__init__(message)


class AbstractContainer(ABC):

    @abstractmethod
    def get(self, name: str):
        raise NotImplementedError('Please implement it')

    @abstractmethod
    def has(self, name: str):
        raise NotImplementedError('Please implement it')


class AbstractResource(ABC):

    @abstractmethod
    def resolve(self, container: AbstractContainer):
        raise NotImplementedError('Please implement it')


class Parameter(AbstractResource):

    def __init__(self, value: Any):
        self.value = value

    @classmethod
    def resolve_value(cls, value, container: AbstractContainer):
        if isinstance(value, dict):
            return {k: cls.resolve_value(v, container) for k, v in value.items()}
        if isinstance(value, list):
            return [cls.resolve_value(v, container) for v in value]
        if isinstance(value, str) and value.startswith('%') and value.endswith('%'):
            return cls.resolve_value(container.get(value.replace('%', '')), container)
        return value

    def resolve(self, container: AbstractContainer):
        return self.resolve_value(self.value, container)


class Service(AbstractResource):

    def __init__(self, klz: str = None, factory: str = None, parameters: dict = None):
        if klz is not None:
            self.klz = klz
        elif factory is not None:
            self.factory = factory
        else:
            raise ValueError('class or factory is required')
        self.parameters = parameters or {}

    def resolve(self, container: AbstractContainer):
        factory = None
        if hasattr(self, 'klz'):
            def factory(*args, **kwargs):
                module_path, class_name = self.klz.split(':')
                service_class = getattr(import_module(module_path), class_name)
                return service_class(*args, **kwargs)
        if hasattr(self, 'factory'):
            def factory(*args, **kwargs):
                factory = container.get(self.factory)
                return factory.create(*args, **kwargs)
        return factory(**Parameter.resolve_value(self.parameters, container))


class Class(AbstractResource):

    def __init__(self, class_path: str):
        self.class_path = class_path

    def resolve(self, container: AbstractContainer):
        module_path, class_name = self.class_path.split(':')
        return getattr(import_module(module_path), class_name)


class ResourceGroup(AbstractResource):

    def __init__(self, pattern: str):
        self.pattern = pattern

    def resolve(self, container: AbstractContainer):
        return {
            sub(self.pattern, '', v): v for v in context.find(self.pattern)
        }


class Container(AbstractContainer):

    def __init__(self, resources: Dict[str, AbstractResource]):
        self.resources = resources

    def get(self, name: str):
        resource = self.resources.get(name)
        if resource is None:
            raise ContainerException(f'{name} not in container')
        return resource.resolve(context)

    def has(self, name: str):
        return name in self.resources.keys()


class StackContainer(AbstractContainer):

    def __init__(self, containers: List[AbstractContainer]):
        self.containers = containers
        self._resources_names = set()

    def get(self, name: str):
        for container in reversed(self.containers):
            if container.has(name):
                return container.get(name)
        return self.containers[0].get(name)  # throws error

    def has(self, name: str):
        return any(container.has(name) for container in self.containers)

    @property
    def resources_names(self):
        if not self._resources_names:
            resources = set()
            for container in self.containers:
                if isinstance(container, ApplicationContainer):
                    container = container.container
                if isinstance(container, Container):
                    resources = resources.union(container.resources.keys())
                if isinstance(container, StackContainer):
                    resources = resources.union(container.resources_names)
            self._resources_names.update(resources)
        return self._resources_names


class ApplicationContainer(AbstractContainer):

    instance = None

    def __init__(self, modules: List[str], configuration: dict = None):
        self._container = None
        self.modules = modules
        self.modules.append('logos')
        self.configuration = configuration or {}

    @property
    def container(self) -> AbstractContainer:
        if self._container is None:
            stack = [
                Container({
                    "app.modules": Parameter(self.modules),
                    "app.configuration": Parameter(self.configuration)
                })
            ]
            for module in self.modules:
                try:
                    stack.append(getattr(import_module(module), 'container'))
                except AttributeError as e:
                    pass
            self._container = StackContainer(stack)
        return self._container

    def get(self, name: str):
        return self.container.get(name)

    def has(self, name: str):
        return self.container.has(name)

    def run(self):
        command = context.get('app.command')
        command.execute()

    def __new__(cls, *args, **kwargs):
        if cls.instance is None:
            cls.instance = object.__new__(cls)
        else:
            raise ContainerException('application container already initialized')
        return cls.instance


class Context(AbstractContainer):

    instances = ContextVar('context_instances')

    @overload
    def __init__(self, container: StackContainer, runtime: Union[dict, None] = None):
        self.container = container
        self.runtime = runtime or {}

    @__init__.add
    def __init__(self, container: AbstractContainer, runtime: Union[dict, None] = None):
        self.__init__(StackContainer([container]), runtime=runtime)

    def get(self, name: str):
        if name not in self.runtime.keys():
            self.runtime[name] = self.container.get(name)
        return self.runtime.get(name)

    def has(self, name: str):
        return name in self.runtime.keys() or self.container.has(name)

    def __enter__(self):
        if self.instances.get(None) is None:
            self.instances.set([])
        self.instances.get([]).append(self)

    def __exit__(self, exc_type, exc_val, exc_tb):
        contexts = self.instances.get([])
        index = contexts.index(self)
        if index != -1:
            contexts.pop(index)

    @classmethod
    def new_from(cls, context: 'Context', runtime: dict = None, container: AbstractContainer = None) -> 'Context':
        runtime = runtime or {}
        for name, value in context.runtime.items():
            if name not in runtime.keys() and hasattr(value, 'clone'):
                runtime[name] = value.clone()
        if container is not None:
            container = StackContainer([context.container, container])
        else:
            container = StackContainer([context.container])
        return cls(container, runtime)


class __ContextWrapper(AbstractContainer):

    def __init__(self):
        self._stack = None

    @property
    def container(self) -> Context:
        if self._stack is None:
            self._stack = StackContainer([ApplicationContainer.instance])
        contexts = Context.instances.get([])
        if len(contexts):
            return contexts[-1]
        else:
            stack_list = [self._stack]
            _context = Context(StackContainer(stack_list))
            stack_list.append(Container({
                'context': Parameter(_context)
            }))
            return _context

    def get(self, name: str):
        return self.container.get(name)

    def has(self, name: str):
        return self.container.has(name)

    def find(self, pattern: str):
        services_names = []
        for name in self.container.container.resources_names:
            if match(pattern, name):
                services_names.append(name)
        return services_names


context = __ContextWrapper()
