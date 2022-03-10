#  Copyright (c) ZenML GmbH 2021. All Rights Reserved.
#
#  Licensed under the Apache License, Version 2.0 (the "License");
#  you may not use this file except in compliance with the License.
#  You may obtain a copy of the License at:
#
#       https://www.apache.org/licenses/LICENSE-2.0
#
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS,
#  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express
#  or implied. See the License for the specific language governing
#  permissions and limitations under the License.
"""CLI for manipulating ZenML local and global config file."""
from typing import TYPE_CHECKING, Optional

import click

from zenml.cli import utils as cli_utils
from zenml.cli.cli import cli
from zenml.config.global_config import (
    BaseGlobalConfiguration,
    ConfigProfile,
    GlobalConfig,
)
from zenml.console import console
from zenml.enums import LoggingLevels, StoreType
from zenml.repository import Repository
from zenml.utils.analytics_utils import AnalyticsEvent, track_event

if TYPE_CHECKING:
    pass


# Analytics
@cli.group()
def analytics() -> None:
    """Analytics for opt-in and opt-out"""


@analytics.command("get")
def is_analytics_opted_in() -> None:
    """Check whether user is opt-in or opt-out of analytics."""
    gc = GlobalConfig()
    cli_utils.declare(f"Analytics opt-in: {gc.analytics_opt_in}")


@analytics.command("opt-in", context_settings=dict(ignore_unknown_options=True))
def opt_in() -> None:
    """Opt-in to analytics"""
    gc = GlobalConfig()
    gc.analytics_opt_in = True
    cli_utils.declare("Opted in to analytics.")
    track_event(AnalyticsEvent.OPT_IN_ANALYTICS)


@analytics.command(
    "opt-out", context_settings=dict(ignore_unknown_options=True)
)
def opt_out() -> None:
    """Opt-out to analytics"""
    gc = GlobalConfig()
    gc.analytics_opt_in = False
    cli_utils.declare("Opted out of analytics.")
    track_event(AnalyticsEvent.OPT_OUT_ANALYTICS)


# Logging
@cli.group()
def logging() -> None:
    """Configuration of logging for ZenML pipelines."""


# Setting logging
@logging.command("set-verbosity")
@click.argument(
    "verbosity",
    type=click.Choice(
        list(map(lambda x: x.name, LoggingLevels)), case_sensitive=False
    ),
)
def set_logging_verbosity(verbosity: str) -> None:
    """Set logging level"""
    # TODO [ENG-150]: Implement this.
    verbosity = verbosity.upper()
    if verbosity not in LoggingLevels.__members__:
        raise KeyError(
            f"Verbosity must be one of {list(LoggingLevels.__members__.keys())}"
        )
    cli_utils.declare(f"Set verbosity to: {verbosity}")


# Profiles
@cli.group()
def profile() -> None:
    """Configuration of ZenML profiles."""


@profile.command("create")
@click.argument(
    "name",
    type=str,
    required=True,
)
@click.option(
    "--url",
    "-u",
    "url",
    help="The store URL to use for the profile.",
    required=False,
    type=str,
)
@click.option(
    "--store-type",
    "-t",
    "store_type",
    help="The store type to use for the profile.",
    required=False,
    type=click.Choice(list(StoreType)),
    default=StoreType.LOCAL,
)
def create_profile_command(
    name: str, url: Optional[str], store_type: Optional[StoreType]
) -> None:
    """Create a new configuration profile."""

    cli_utils.print_active_profile()

    cfg = GlobalConfig()

    if cfg.get_profile(name):
        cli_utils.error(f"Profile {name} already exists.")
        return
    cfg.add_or_update_profile(
        ConfigProfile(name=name, store_url=url, store_type=store_type)
    )
    cli_utils.declare(f"Profile `{name}` successfully created.")


@profile.command("list")
def list_profiles_command() -> None:
    """List configuration profiles."""

    cli_utils.print_active_profile()

    cfg = GlobalConfig()
    repo = Repository()

    profiles = cfg.profiles

    if len(profiles) == 0:
        cli_utils.warning("No profiles configured!")
        return

    profile_dicts = []
    for profile_name, profile in profiles.items():
        active_str = ""
        local_stack = ""
        if profile_name == cfg.active_profile_name:
            active_str += ":crown:"
        if profile_name == repo.active_profile_name:
            active_str += ":point_right:"
            local_stack = repo.active_stack_name or ""
        store_type = "N/A"
        if profile.store_type:
            store_type = profile.store_type.value
        profile_config = {
            "ACTIVE": active_str,
            "PROFILE NAME": profile_name,
            "STORE TYPE": store_type,
            "URL": profile.store_url,
            "GLOBAL ACTIVE STACK": profile.active_stack,
            "LOCAL ACTIVE STACK": local_stack,
        }
        profile_dicts.append(profile_config)

    cli_utils.print_table(profile_dicts)


@profile.command(
    "describe",
    help="Show details about the active profile.",
)
@click.argument(
    "name",
    type=click.STRING,
    required=False,
)
@click.option(
    "--global",
    "-g",
    "global_profile",
    is_flag=True,
    help="Describe the global active profile",
)
def describe_profile(name: Optional[str], global_profile: bool = False) -> None:
    """Show details about a named profile or the active profile.

    If the `--global` flag is set, the global active profile will be shown,
    otherwise the repository local active profile is shown.
    """
    cli_utils.print_active_profile()

    repo = Repository()
    cfg = GlobalConfig()
    if global_profile:
        name = name or cfg.active_profile_name
    else:
        name = name or repo.active_profile_name

    if len(GlobalConfig().profiles) == 0:
        cli_utils.warning("No profiles registered!")
        return
    if not name:
        cli_utils.warning("No profile is set as active!")
        return

    profile = GlobalConfig().get_profile(name)
    if not profile:
        cli_utils.error(f"Profile `{name}` does not exist.")
        return

    cli_utils.print_profile(
        profile,
        locally_active=name == repo.active_profile_name,
        globally_active=name == cfg.active_profile_name,
    )


@profile.command("delete")
@click.argument("name", type=str)
def delete_profile(name: str) -> None:
    """Delete a profile.

    If the profile is currently active, it cannot be deleted.
    """
    cli_utils.print_active_profile()

    with console.status(f"Deleting profile `{name}`...\n"):

        cfg = GlobalConfig()
        repo = Repository()
        if not cfg.get_profile(name):
            cli_utils.error(f"Profile {name} doesn't exist.")
            return
        if cfg.active_profile_name == name:
            cli_utils.error(
                f"Profile {name} cannot be deleted because it's globally active. "
                f"Please choose a different active global profile first by running "
                "`zenml profile set --global PROFILE`."
            )
            return

        if repo.active_profile_name == name:
            cli_utils.error(
                f"Profile {name} cannot be deleted because it's locally active. "
                f"Please choose a different active profile first by running "
                "`zenml profile set PROFILE`."
            )
            return

        cfg.delete_profile(name)
        cli_utils.declare(f"Deleted profile {name}.")


@profile.command("set")
@click.argument("name", type=str)
@click.option(
    "--global",
    "-g",
    "global_profile",
    is_flag=True,
    help="Set the global active profile",
)
def set_active_profile(name: str, global_profile: bool = False) -> None:
    """Set a profile as active.

    If the `--global` flag is set, the profile will be set as the global
    active profile, otherwise as the repository local active profile.
    """
    cli_utils.print_active_profile()

    with console.status(f"Setting the active profile to `{name}`..."):

        cfg: BaseGlobalConfiguration
        if global_profile:
            cfg = GlobalConfig()
        else:
            cfg = Repository()

        current_profile_name = cfg.active_profile_name
        if current_profile_name == name:
            cli_utils.declare(f"Profile `{name}` is already active.")
            return

        try:
            cfg.activate_profile(name)
        except Exception as e:
            cli_utils.error(f"Error activating profile: {str(e)}. ")
            if current_profile_name:
                cli_utils.declare(
                    f"Keeping current profile: {current_profile_name}."
                )
                cfg.activate_profile(current_profile_name)
            return
        cli_utils.declare(f"Active profile changed to: {name}")


@profile.command("get")
def get_active_profile() -> None:
    """Get the active profile."""
    with console.status("Getting the active profile..."):

        cfg = GlobalConfig()
        repo = Repository()

        active_profile_name = cfg.active_profile_name
        if active_profile_name:
            cli_utils.declare(
                f"Globally active profile is: {active_profile_name}"
            )
        active_profile_name = repo.active_profile_name
        if active_profile_name:
            cli_utils.declare(
                f"Locally active profile is: {active_profile_name}"
            )
