# Logos

Logos is a simple implementation of dependency injection and service container for python 


## Create a app file `app.py`

```py
from logos.context import ApplicationContainer, Context

app = ApplicationContainer(
    modules=[...] # type your modules with containers defined here, see a logos/__init__.py file to understand about container declaration
)

app.run()
```


## Execute command

```sh
python app.py --help
```
