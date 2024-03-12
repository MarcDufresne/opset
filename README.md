# Opset

[![Coverage Status](https://coveralls.io/repos/github/MarcDufresne/opset/badge.svg)](https://coveralls.io/github/MarcDufresne/opset)

A library for simplifying the configuration of Python applications at all stages of deployment.

Opset is a config manager that let you manage your configuration via YAML file or environment variables.
The general principle of Opset is that you want to hold your secrets and manage your configurations via
configuration files when doing local development and via environment variables when your app is deployed. It is however
possible to also handle local development through environment variables if the developer sees fit.

With Opset you define everything that can be tweaked with your application in
one Pydantic model. This way the developers and integrators working with your code will know exactly what setting they
can change on your code base. You can then overwrite the default config with a local config stored in a file called
`local.yml`, this file is aimed to be used for local development by your developers and let them easily manage a
configuration file that fits their development need. Finally, you can also have environment variables that have a
matching name to your config that will overwrite your config, letting you use your config in a deployed environment
without having your secret written down in a config file. Opset aims to reconcile the ease of use of a
config file with the added security of environment variables.

This library is available on PyPI under the name Opset. You can install with pip by running `pip install opset`.

# Table of Contents

1. [Lexicon](#lexicon)
2. [Architecture Overview](#architecture-overview)
    1. [Loading the config for unit tests](#loading-the-config-for-unit-tests)
3. [Usage Guide](#usage-guide)
    1. [Making the difference between null and empty](#making-the-difference-between-null-and-empty)
    2. [Opset + Google Cloud Secret Manager](#Opset--google-cloud-secret-manager)
    3. [Naming your config sections](#naming-your-config-sections)
    4. [Controlling your entry points](#controlling-your-entry-points)
4. [Example Configuration file](#example-configuration-file)
    1. [default.yml](#defaultyml)
    2. [local.yml](#localyml)
    3. [unit_test.yml](#unit_testyml)
    4. [Example Logging Configuration values](#example-logging-configuration-values)
    5. [Log Processors](#log-processors)
5. [Support for unit tests](#support-for-unit-tests)
    1. [setup_unit_test_config](#setup_unit_test_config)
    2. [mock_config](#mock_config)
6. [Contributing and getting set up for local development](#contributing-and-getting-set-up-for-local-development)

## Lexicon

| Term     | Definition                                                                                                                                                                                                      |
|----------|-----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| config   | The config Pydantic model or a configuration file (format: YAML).                                                                                                                                               |
| section	 | A section within a configuration file, a section tend to group different settings together under a logical block. For example a section named redis would encompass all settings related specifically to redis. |
| setting	 | A key within a section in a configuration file. A value is associated with a key and querying the config for a setting within a section will return the value associated with it.                               |

## Architecture Overview

There are three possible config files

| Config Name  | Purpose                                                                                                                                                             |
|--------------|---------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| Config Model | This is the user defined config model based on `OpsetSettingsModel`.                                                                                                |
| local.yml    | This is a local config that overwrites the default config, this file is not committed to the repository and is meant to be used in a local development environment. |

The content of the default config is loaded first, and if any settings are redefined in `local.yml`, the default values
from the model are overwritten by `local.yml`.

Environment variables will apply after the `local.yml` overwrite of the config settings if they have a matching name. To
do so, the environment variable must be named in the following way:

> `{APP_NAME_ALL_CAPS}_{SECTION}_{SETTING}`

So for the application `my-small-project` if we wanted to overwrite the setting `port` from the section `app`, your
environment variable would need to be named like this:

> `MY_SMALL_PROJECT_APP_PORT`

It is also possible to have nested sections, so following the example above, if you wanted to override the value of
`api.weather.host` you could do so using the following environment variable:

> `MY_SMALL_PROJECT_API_WEATHER_HOST`

## Usage Guide

To create a new configuration you need to first implement a pydantic model based on `OpsetSettingsModel` to represent
your configuration. It can contain sub models all based on `OpsetSettingsModel`. Then you can initialize your
configuration by instantiating the `Config` class. Your config object will be available in the `config` attribute of the
opset config.

Opset will also check for `local.yml`. The location needs to be specified when instantiating the `Config` object. Your
`local.yml` should be added to `.gitignore`.

A basic Opset setup will look like this:

```python
from opset import OpsetSettingsMainModel, Config


class MyConfig(OpsetSettingsMainModel):
    host: str
    port: int = 8080


config = Config("my-app", MyConfig, "my_app.config").config
```
You would then import your new `config` variable where needed in your app. 

The `Config` class takes the following arguments:

| Parameter       | Description                                                                                                                                                                                                                                   | Default value | Example             |
|-----------------|-----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|---------------|---------------------|
| `app_name`      | The name of the application, usually the name of the repo. Ex: `myproject-example`. This will be used for finding the prefix to the environment variables. The name of the app will be uppercased and dashes will be replaced by underscores. |               | `myproject-example` |
| `config_model`  | Your implementation of `OpsetSettingsModel` that defines your configuration.                                                                                                                                                                  |
| `config_path`   | A python path to where the configuration files are. Relative to the application. Ex: `tasks.config` would mean that the config files are located in the directory config of the directory tasks from the root of the repo.                    |               | `tasks.config`      |
| `setup_logging` | Whether the logging config should be loaded immediately after the config has been loaded. Your configuration model will need to have the logging attribute of type `OpsetLoggingConfig` for this to work.  Default to `True`.                 | `True`        | `True`              |

### Making the difference between null and empty

The configuration is stored in YAML and follows the YAML standard. As such, it makes a distinction between `null` keys
and empty keys.

```
app:
  # this setting's value is declared but not defined
  # it will be set to None when accessed unless it is overwritten in local.yml or in an environment variable
  api_key: null
  # this setting's value is set to an empty string
  log_prefix: 
```

### Controlling your entry points

The config object is initiated once you create the `Config` object, before that, trying to get read
a value from the config will throw an exception. It is very important to have a good idea of what the entry points
are in your application and to create your `Config` object as early as possible in your application to avoid issues.

You cannot instantiate `Config` more than one time, so make sure the code handling your configuration is only ran once.

### Opset + Google Cloud Secret Manager

You need to install opset with the extras `gcp` in order to use this feature.

Opset is able to fetch secrets from Google Cloud Secret Manager.
You need to be authenticated using [gcloud CLI](https://cloud.google.com/sdk/docs/install-sdk) or setting up a service
account.

The config value should respect on of these formats

- `opset+gcp://projects/<my_project>/secrets/<my_secret>`
- `opset+gcp://projects/<my_project>/secrets/<my_secret>/versions/<my_version>`

Example

```yaml
database:
  host: opset+gcp://projects/dev-3423/secrets/db_host
```

It is also possible to create a file `.opset.yml` in your project to create mapping for project name.
For instance, with the following config.

```yaml
gcp_project_mapping:
  dev: dev-3423
```

Opset will be able to map the project name like this.

`opset+gcp://projects/dev/secrets/db_host -> opset+gcp://projects/dev-3423/secrets/db_host`

## Example Configuration file

### local.yml

This file is typically defined by developers for their own development and local usage of the app. This file
may contain secrets and as such it must be added to the `.gitignore` file.

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
  logger_overrides: # overwrite min log level of third party loggers
    googleapiclient: ERROR
  json_format: False  # Whether the logs should be formatted as json. Defaults to False.
  json_event_key: "event"  # The key to use for the event in the json format. Defaults to "event"
```

### Log Processors

Since we are using `structlog` you can use the Processor feature to add additional info to your log records, this
can be useful to add a request ID, or the hostname of the machine to all your log records without having to pass
anything to your logging calls.

To use this simply define any processors you want by inheriting from the `BaseProcessor` class of `opset`
and pass an instance to the `load_logging_config` on your opset config call:

```python
import logging

from flask import Flask
from opset import BaseProcessor, Config, OpsetSettingsMainModel, OpsetLoggingConfig, load_logging_config

from my_app.request_context import get_request_id


class MyConfig(OpsetSettingsMainModel):
    host: str
    port: int = 8080
    logging: OpsetLoggingConfig


class RequestContextProcessor(BaseProcessor):
    def __call__(self, logger, name, event_dict):
        event_dict["request_id"] = get_request_id()
        return event_dict


config = Config("my_app", MyConfig, "my_app.config", setup_logging=False).config  # Defer the logging setup
load_logging_config(config.logging, custom_processors=[RequestContextProcessor()])  # Pass your custom processors

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
from opset import Config, OpsetSettingsMainModel, OpsetLoggingConfig, load_logging_config
from logging import Handler
import json


class MyConfig(OpsetSettingsMainModel):
    host: str
    port: int = 8080
    logging: OpsetLoggingConfig


class LocalFileHandler(Handler):
    def __init__(self):
        Handler.__init__(self)

    def emit(self, record):
        """
        Will log the record in the root log.json file
        """
        with open("log.json", "w") as fp:
            json.dump(record.msg, fp)


config = Config("my_app", MyConfig, "my_app.config", setup_logging=False).config  # Defer the logging setup
load_logging_config(config.logging, custom_handlers=[LocalFileHandler()])  # Pass your custom handlers

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

To setup your config for unit tests you will want to import your opset_config object and call `setup_unit_test` on it. 
This function takes a dictionary of all the configuration you want to overwrite. This call should happen only once in 
your unit test setup.

### mock_config

The `mock_config` contextmanager on the opset config is used to temporarily overwrite your configuration. Like 
`setup_unit_test` you pass a dictionary of the configurations you want to overwrite.

## Contributing and getting set up for local development

To set yourself up for development on Opset, make sure you are using
[poetry](https://poetry.eustace.io/docs/) and simply run the following commands from the root directory:

```bash
make install
```
