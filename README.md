# Opset

[![Coverage Status](https://coveralls.io/repos/github/ElementAI/opset/badge.svg)](https://coveralls.io/github/ElementAI/opset)

A library for simplifying the configuration of Python applications at all stages of deployment.

Opset is a config manager that let you manage your configuration via yaml file or environment variables.
The general principle of Opset is that you want to hold your secrets and manage your configurations via
configuration files when doing local development and via environment variables when your app is deployed. It is however
possible to also handle local development through environment variables if the developer see fit.

With Opset you define everything that can be tweaked with your application in one specific
file (`default.yml`). This way the developers and integrators working with your code will know exactly what setting they
can change on your code base. You can then overwrite the default config with a local config stored in a file called
`local.yml`, this file is aimed to be used for local development by your developers and let them easily manage a
configuration file that fits their development need. Finally, you can also have environment variables that have a
matching name to your config that will overwrite your config, letting you use your config in a deployed environment
without having your secret written down in a config file. Opset aims to reconcile the ease of use of a
config file with the added security of environment variables.

This library is available on PyPI under the name Opset. You can install with pip by running `pip install opset`.

# Table of Contents

1. [Lexicon](#lexicon)
1. [Architecture Overview](#architecture-overview)
    1. [Loading the config for unit tests](#loading-the-config-for-unit-tests)
    1. [Safeguards](#safeguards)
        1. [Settings not declared in default.yml are not loaded](#settings-not-declared-in-defaultyml-are-not-loaded)
        1. [Forcing all default settings to have values](#forcing-all-default-settings-to-have-values)
1. [Usage Guide](#usage-guide)
    1. [Making the difference between null and empty](#making-the-difference-between-null-and-empty)
1. [Example of Usage](#example-of-usage)
    1. [Opset + Environment Variables](#Opset--environment-variables)
    1. [Naming your config sections](#naming-your-config-sections)
    1. [Controlling your entry points](#controlling-your-entry-points)
1. [Example Configuration file](#example-configuration-file)
    1. [default.yml](#defaultyml)
    1. [local.yml](#localyml)
    1. [unit_test.yml](#unit_testyml)
    1. [Example Logging Configuration values](#example-logging-configuration-values)
    1. [Log Processors](#log-processors)
1. [Support for unit tests](#support-for-unit-tests)
    1. [setup_unit_test_config](#setup_unit_test_config)
        1. [Usage example of setup_unit_test_config](#usage-example-of-setup_unit_test_config)
    1. [mock_config](#mock_config)
        1. [Usage example of mock_config](#usage-example-of-mock_config)
1. [Contributing and getting set up for local development](#contributing-and-getting-set-up-for-local-development)

## Lexicon

| Term | Definition |
|--- | --- |
| config |	A configuration file (format: YAML). |
| section	| A section within a configuration file, a section tend to group different settings together under a logical block. For example a section named redis would encompass all settings related specifically to redis. Section name should not contain underscore. |
| setting	| A key within a section in a configuration file. A value is associated with a key and querying the config for a setting within a section will return the value associated with it. |

![Lexicon](https://github.com/ElementAI/opset/raw/master/doc/lexicon.png)

## Architecture Overview

There are three possible config files

| Config Name | Purpose |
| --- | --- |
| default.yml | This is the base config, `default.yml` needs to have the declaration of all sections and settings. |
| local.yml | This is a local config that overwrites the default config, this file is not committed to the repository and is meant to be used in a local development environment. |
| unit_test.yml | This is a local config that overwrites the default config during unit tests, this file is not committed to the repository and is meant to be used in a local development environment. When the config is initialized for unit tests, if a `unit_test.yml` file is present it will be loaded, otherwise the environment variables will be loaded on top of the default config. |

The content of the default config is loaded first, and if any settings are redefined in `local.yml`, the values from
`default.yml` are overwritten by `local.yml`.

Environment variables will apply after the `local.yml` overwrite of the config settings if they have a matching name. To
do so, the environment variable must be named in the following way:

> {APP_NAME_ALL_CAPS_UNDERSCORE}_{SECTION}_{SETTING}

So for the application my-small-project if we wanted to overwrite the setting port from the section app, your
environment variable would need to be named like this:

> MY_SMALL_PROJECT_APP_PORT

![Order](https://github.com/ElementAI/opset/raw/master/doc/setup_config_overwrite_order.png)

### Loading the config for unit tests

Opset provides a specific function to load the config when performing unit testing that provides the
developer with some additional tool to better handle the reality of unit testing. When initializing the config for
unit tests, the content of the default config is loaded first, and if the `unit_test.yml` file is present and have
values, the values from `default.yml` are overwritten by `unit_test.yml`. Then the values from the environment variables
apply and if you need some config values to be specific to your unit tests you have the option to pass config values
when loading the unit tests that will overwrite all other sources.

![Order](https://github.com/ElementAI/opset/raw/master/doc/setup_config_unit_test_overwrite_order.png)

### Safeguards

There are two safeguards in the code to try to prevent developer mistakes.

#### Settings not declared in `default.yml` are not loaded

Your `default.yml` is what defines what can be tweaked in your application, it is made to be the one place to look at if
you are wondering what can be changed in the configuration of your application.

When loading the configuration a warning will be raised if a setting is detected from the local config, environment
variables or unit tests values that is not present in `default.yml`. This means that if your `local.yml`
config looks like this:

```
app:
  host: 127.0.0.1
  port: 7777
  ham_level: 7
  api_key: 332d5c3e-a7a3-41db-aa5c-c0dfbac8f3d2
```

And your default config looks like this:

```
app:
  host: 127.0.0.1
  port: 7777
  debug: False
  api_key: null
```

A warning will be issued when the config is loaded because the setting `ham_level` from the section `app` is not known to
the default config. The setting and value of `ham_level` will not be loaded in the config and will not be usable in the
application if it's not present in `default.yml`. As per the example above, you are not forced to set a value for
settings in the default config (see api_key), but the setting needs to be there.

#### Forcing all default settings to have values

There is a special flag called `critical_settings` that is passed to the function `setup_config` from the module.
This flag is set to `True` by default and will make Opset raises an error if there is no
value defined for a setting in `default.yml` after having applied all possible configuration files and environment
variables.

## Usage Guide

You interact with the library through the function `opset.setup_config` to set up the config and with the
singleton object `opset.config` to read config values. Optionally Opset can also manage your
application logging via the function `opset.load_logging_config` or the argument `setup_logging` from the
function `opset.setup_config`. The `opset.config` object is a singleton which means that no matter where
it is accessed in the code and the loading order, as long as it has been initiated with `opset.setup_config` it
will hold the same configuration values in all of your application.

The library expects that your project will contain [yaml](https://yaml.org/) files named `default.yml` and
(optionally) `local.yml` and `unit_test.yml`. You will be able to point to the location of those config files when
invoking `opset.setup_config` as the second positional argument. The file `default.yml` should be committed and follow your
project and should not contain any secrets. The files `local.yml` and `unit_test.yml` should be added to your
`.gitignore` to avoid having them committed by accident as those files can contain secrets.

The `opset.setup_config` function will handle everything from reading the yaml file containing your project's config values,
to loading them into your environment being mindful not to overwrite ENV variables already present. It needs to be
passed the name of your application along with the python style path (eg. `module.submodule`) to where the
`default.yml`, `local.yml` or `unit_test.yml` files are located in the project.

To initialize the configuration, use the function `opset.setup_config` and that's it. After that you can import
the variable `opset.config` from the module to use the config. You can safely import the config variable before
initializing it because access to the config object attributes is dynamic. It is important to note that the config is
built to be read-only, it gets populated when `opset.setup_config` and from then on you just read the values from
the config as needed in your implementation.

The function setup_config takes the following arguments:

| Parameter | Description | Default value | Example
| --- | --- | --- | --- |
| `app_name` | The name of the application, usually the name of the repo. Ex: myproject-example. This will be used for finding the prefix to the environment variables. The name of the app will be uppercased and dashes will be replaced by underscores. | | `myproject-example` |
| `config_path` | A python path to where the configuration files are. Relative to the application. Ex: `tasks.config` would mean that the config files are located in the directory config of the directory tasks from the root of the repo. | | `tasks.config` |
| `critical_settings` | A boolean to specify how null settings in `default.yml` should be handled. If set to `True`, the function will raise an exception when a key in `default.yml` is not defined in `local.yml` or in an environment variable. | `True` | `True` |
| `setup_logging` | Whether the logging config should be loaded immediately after the config has been loaded. Default to `True`. | `True` | `True` |

### Making the difference between null and empty

The configuration is stored in yaml and follows the yaml standard. As such, it makes a distinction between null keys
and empty keys. 

```
app:
  # this setting's value is declared but not defined
  # it will be set to None when accessed unless it is overwritten in local.yml or in an environment variable
  api_key: null
  # this setting's value is set to an empty string
  log_prefix: 
```

### Naming your config sections

Due to certain limitations when loading environment variables, your config sections should not contain underscores to
avoid issues when loading environment variables.

### Controlling your entry points

The config object is initiated once you call the function `opset.setup_config`, before that, trying to get read
a value from the config will throw an exception. It is very important to have a good idea of what the entry points
are in your application and to call `opset.setup_config` as early as possible in your application to avoid issues.

To avoid duplicating calls to `opset.setup_config` we recommend you add the call to `opset.setup_config`
in a function that is called whenever you need to start your application, you can then safely call this function
whenever you create a new entry points in your application.

Be mindful about reading values from the config object at module level. If you need to import modules before you can
call `opset.setup_config` and one of those modules has a module-level call to read the config, Opset
will raise an error when importing because the code will be read at import time and the config will not have been
initiated.

For a more concrete example, avoid doing something like this:

```python
from opset import config

FULL_DB_URI = f"{config.db.scheme}{config.db.user}:{config.db.password}@{config.db.host}:{config.db.port}"
```

And do something like this instead:

```python
from opset import config

def get_full_db_uri():
    return f"{config.db.scheme}{config.db.user}:{config.db.password}@{config.db.host}:{config.db.port}"
```

Last thing, remember that it is safe to import the config object before the config has been initiated. The config
object is a singleton and will be populated after `opset.setup_config` has been called, even if it was imported
first.

## Example Of Usage

Here is a little example of how to use the opset features in a simple Flask app.

```python
from flask import Flask, jsonify
from opset import config, setup_config


setup_config("myproject-example", "myproject-example.config")
 
app = Flask(config.app.name)

@app.route("/")
def hello():
    return jsonify({"Hello and welcome to": config.app.welcome_message})
```

This example will leverage the config values stored under the `myproject-example/config` folder, with the following content:

```yaml
app:
  welcome_message: Hi lads
```

### Opset + Environment Variables

One of the features of Opset is how it handles the interaction between the config values in your projects' yaml
files and the values that might already be set in your environment. Values already in your environment have higher
priority and will overwrite any values in your config files. In order to compare against the environment variables,
Opset builds the names for config values using `<APP_NAME>_<SECTION_NAME>_<SETTING_NAME>` as a template.
This means that if your environment contains the value `MYPROJECT_EXAMPLE_DATABASE_HOST`, and your application is named
`myproject-example` it will overwrite the value of the database host from the following config file:

```yaml
database:
  host: 89.22.102.02
```

The conversion to python types from the yaml config file is handled by pyyaml but for environment variables
Opset do its own conversion depending on the value:

- `true`, `t`, `yes`, `y` (case-insensitive) will be converted to a `True` `bool`
- `false`, `f`, `no`, `n` (case-insensitive) will be converted to a `False` `bool`
- Any number-only string will be converted to an `int` if they have no decimals and `float` if they do
- A JSON-valid array will be converted to a `list`
- A JSON-valid object will be converted to a `dict`
- Any other value will remain a `str`

NOTE: Be sure to respect JSON conventions when defining arrays and objects, use lower-case booleans, double quotes, etc.

## Example Configuration file

### default.yml

Declare in the `default.yml` file all the settings that the app will require. For each of the keys,
you can define a default value. If there is no sensible defaults for a setting, leave it blank (which
is equivalent to setting it to _null_).

As a rule of thumb, a default value should be equally good and safe for local, staging or prod environments.
For example, setting `app.debug` above to `True` would be an error as it may cause prod to run with debug
messages enabled if prod is not overriding it. The opposite is also true. A default value pointing to a production
system can easily wipe or overload it during testing if tests do not overwrite the defaults properly. When in doubt,
prefer a null value.

Also, secrets should NEVER be added to this file.

### local.yml

This file is typically defined by developers for their own development and local usage of the app. This file
may contain secrets and as such it must be added to the `.gitignore` file.

### unit_test.yml

This file is used to handle configuration values when running unit tests locally by developers. The content of this
file is only used when initiating the config through `opset.setup_unit_test_config` and is discussed in more
details in the section of the documentation dedicated to unit testing. This file may contain secrets and as such it
must be added to the `.gitignore` file.

### Example Logging Configuration values

Opset also provides functionality for configuring the logging handlers for your project, this uses
`structlog` in the background. This is provided through the aforementioned `load_logging_config` function. If you
choose to use this functionality, you will need to add some more values to your configuration files, and you can find
an example of such values here:

```yaml
logging:
  date_format: "iso"  # strftime-valid date format, e.g.: "%Y-%M-%d", or "iso" to use the standard ISO format
  use_utc: True  # Use UTC timezone if true, or local otherwise
  min_level: DEBUG  # Minimum level to display log for
  colors: False  # Use colors for log display, defaults to False
  disable_processors: False  # Disables log processors (additional info at the end of the log record)
  logger_overrides:  # overwrite min log level of third party loggers
    googleapiclient: ERROR
```

### Log Processors

Since we are using `structlog` you can use the Processor feature to add additional info to your log records, this
can be useful to add a request ID, or the hostname of the machine to all your log records without having to pass
anything to your logging calls.

To use this simply define any processors you want by inheriting from the `BaseProcessor` class of `opset`
and pass an instance to the `load_logging_config` call:

```python
import logging

from flask import Flask
from opset import BaseProcessor, load_logging_config, setup_config

from my_app.request_context import get_request_id


class RequestContextProcessor(BaseProcessor):
    def __call__(self, logger, name, event_dict):
        event_dict["request_id"] = get_request_id()
        return event_dict


setup_config("my_app", "my_app.config", setup_logging=False)  # Defer the logging setup
load_logging_config(custom_processors=[RequestContextProcessor()])  # Pass your custom processors

app = Flask(__name__)

@app.route("/")
def root():
    logging.info("This will include the request ID!")
    return "OK"
```

A processor receives the logger object, the logger name and most importantly the `event_dict` which contains all the
info of the log record. So simply add to the `event_dict` in your processor and return it.

In local development processors can add some unnecessary noise to the log output, so they can be disabled by setting
`logging.disable_processors` to `True` in your `local.yml`.

By default, Opset enables the built-in `HostNameProcessor`, which adds the machine hostname to log records.
It can be disabled by passing `use_hostname_processor=False` in the `load_logging_config` call.

### Log Handlers

Since we are using python's `logging` library, you can use custom log handlers to customize how and where the
information is logged when using the logger.

To use this simply define any log handlers you want by inheriting from the `Handler` class of `logging` and overwriting
the `emit` method, and pass an instance to the `load_logging_config` call:

```python
import logging

from flask import Flask
from opset import load_logging_config, setup_config
from logging import Handler
import json

class LocalFileHandler(Handler):
    def __init__(self):
        Handler.__init__(self)

    def emit(self, record):
        """
        Will log the record in the root log.json file
        """
        with open("log.json", "w") as fp:
            json.dump(record.msg, fp)


setup_config("my_app", "my_app.config", setup_logging=False)  # Defer the logging setup
load_logging_config(custom_handlers=[LocalFileHandler()])  # Pass your custom handlers

app = Flask(__name__)

@app.route("/")
def root():
    logging.info("Log me in a local file!")
    return "OK"
```

The handler receives the record object, containing all the log information that was processed by the
processors. The handler can chose what to do with that information, should it be to log it in a local file,
send it to a blob storage, send it to an external tool (ex: Sentry)

## Support for unit tests

Opset support unit testing to make sure you can handle the special cases that may come up in your
application configuration during unit testing.

### setup_unit_test_config

The function `opset.setup_unit_test_config` is made to replace `opset.setup_config` when running unit
tests. Remember to control your entry points and call this function as early as possible when running the unit tests.
If you are using pytest it is recommended to add it to a
[conftest.py](https://docs.pytest.org/en/2.7.3/plugins.html?highlight=re#conftest-py-plugins) module set at the root of
your unit tests package.

`opset.setup_unit_test_config` works in the same way as `opset.setup_config` but will load the yaml
config file `unit_test.yml` if present instead of `local.yml`. It also accepts an additional parameter called
`config_values` that is a dictionary representation of a config file that will have the highest priority when doing
overwrites.

| Parameter | Description | Default value | Example
| --- | --- | --- | --- |
| `app_name` | The name of the application, usually the name of the repo. Ex: myproject-example. This will be used for finding the prefix to the environment variables. The name of the app will be uppercased and dashes will be replaced by underscores. | | `myproject-example` |
| `config_path` | A python path to where the configuration files are. Relative to the application. Ex: `tasks.config` would mean that the config files are located in the directory config of the directory tasks from the root of the repo. | | `tasks.config` |
| `config_values` | A dictionary mimicking the structure of the config files, to be applied as an overwrite on top of default + unit_test config (if available) and env variables. | | `{"app": {"debug": False}}` |

#### Usage example of setup_unit_test_config

In `default.yml`:

```yaml
db:
    user: 
    password:
    name: staging
```

In `unit_test.yml`:

```yaml
db:
    user: serge
    password: mystrongpassword
```

In the `conftest.py` module a the root of your unit tests package:

```python
from opset import config, setup_unit_test_config

setup_unit_test_config("myproject-example", "myproject-example.config", config_values={"db": {"name": "test"}})
```

After running `opset.setup_unit_test_config` the config will hold the following values:

```
>>> config.db.user
'serge'

>>> config.db.password
'mystrongpassword'

>>> config.db.name
'test' 
```

### mock_config

The function `opset.mock_config` is a context manager that lets you overwrite config values from the config
object for the time of a unit tests. If your unit test requires for the time of a test to have your config hold a
special temporary value, `opset.mock_config` is there for you. It takes the parameter `config_values` which
is identical to what `opset.setup_unit_test_config` uses.

Your config object will be duplicated for the duration of your context manager and overwritten by the values you send
to the parameter `config_values`. Once you exit the context manager the copy of the config disappears and your
application resumes with the config object being in the same state as it was before entering the context manager.

#### Usage example of mock_config

In your module to be tested:

```python
from opset import config

def is_admin(user_name: str) -> bool:
    return user_name in config.app.admin_list
```

In your `default.yml`:
```yaml
app:
    admin_list: 
```

In your `unit_test.yml`:
```yaml
app:
    admin_list:
      - "jotaro kujo"
```

In your unit test module:
```python
from opset import mock_config

from my_package.my_module import is_admin


def test_is_admin():
    # Test true
    assert is_admin("jotaro kujo")
    
    # Test false
    with mock_config(config_values={"app": {"admin_list": []}}):
        assert not is_admin("jotaro kujo")
```


## Contributing and getting set up for local development

To set yourself up for development on Opset, make sure you are using
[poetry](https://poetry.eustace.io/docs/) and simply run the following commands from the root directory:

```bash
make bootstrap
make install
```
