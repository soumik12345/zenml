#  Copyright (c) ZenML GmbH 2022. All Rights Reserved.
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
import logging
import os
import shutil
from typing import Generator

import pytest
from pytest_mock import MockerFixture
from zenml.config.global_config import GlobalConfig

from zenml.container_registries import BaseContainerRegistry
from zenml.repository import Repository
from zenml.stack import Stack


@pytest.fixture(scope="module")
def shared_kubeflow_repo(
    base_repo: Repository,
    tmp_path_factory: pytest.TempPathFactory,
    module_mocker: MockerFixture,
) -> Generator[Repository, None, None]:
    """Creates a clean global configuration and repository with a locally
    provisioned kubeflow stack.

    As the resource provisioning for the local kubeflow deployment takes quite
    a while, this fixture has a module scope and will therefore only run once.

    **Note**: The fixture should not be used directly. Use the
    `clean_kubeflow_repo` fixture instead that builds on top of this and
    provides the  test with a clean working directory and artifact/metadata
    store.

     Args:
        base_repo: The base ZenML repository for tests.
        tmp_path_factory: Factory to generate temporary test paths.
        module_mocker: Mocker fixture

    Yields:
        A repository with a provisioned local kubeflow stack.
    """
    from zenml.integrations.kubeflow.orchestrators import KubeflowOrchestrator

    # Patch the ui daemon as forking doesn't work well with pytest
    module_mocker.patch(
        "zenml.integrations.kubeflow.orchestrators.local_deployment_utils.start_kfp_ui_daemon"
    )

    tmp_path = tmp_path_factory.mktemp("tmp")
    os.chdir(tmp_path)

    logging.info(f"Tests are running in clean environment: {tmp_path}")

    # save the current global configuration and repository singleton instances
    # to restore them later, then reset them
    original_config = GlobalConfig.get_instance()
    original_repository = Repository.get_instance()
    GlobalConfig._reset_instance()
    Repository._reset_instance()

    # set the ZENML_CONFIG_PATH environment variable to ensure that the global
    # configuration, the configuration profiles and the local stacks used in
    # the scope of this function are separate from those used in the global
    # testing environment
    orig_config_path = os.getenv("ZENML_CONFIG_PATH")
    os.environ["ZENML_CONFIG_PATH"] = str(tmp_path / "zenml")

    # initialize repo with new tmp path
    repo = Repository()

    repo.original_cwd = base_repo.original_cwd

    # Register and activate the kubeflow stack
    orchestrator = KubeflowOrchestrator(
        name="local_kubeflow_orchestrator",
        custom_docker_base_image_name="zenml-base-image:latest",
        synchronous=True,
    )
    metadata_store = repo.active_stack.metadata_store.copy(
        update={"name": "local_kubeflow_metadata_store"}
    )
    artifact_store = repo.active_stack.artifact_store.copy(
        update={"name": "local_kubeflow_artifact_store"}
    )
    container_registry = BaseContainerRegistry(
        name="local_registry", uri="localhost:5000"
    )
    kubeflow_stack = Stack(
        name="local_kubeflow_stack",
        orchestrator=orchestrator,
        metadata_store=metadata_store,
        artifact_store=artifact_store,
        container_registry=container_registry,
    )
    repo.register_stack(kubeflow_stack)
    repo.activate_stack(kubeflow_stack.name)

    # Provision resources for the kubeflow stack
    kubeflow_stack.provision()

    yield repo

    # Deprovision the resources after all tests in this module are finished
    kubeflow_stack.deprovision()
    os.chdir(str(base_repo.root))
    shutil.rmtree(tmp_path)

    # restore the global configuration path
    os.environ["ZENML_CONFIG_PATH"] = orig_config_path

    # restore the original global configuration and the repository singleton
    GlobalConfig._reset_instance(original_config)
    Repository._reset_instance(original_repository)

@pytest.fixture
def clean_kubeflow_repo(
    shared_kubeflow_repo: Repository, clean_repo: Repository
) -> Generator[Repository, None, None]:
    """Creates a clean repo with a provisioned local kubeflow stack.

    Args:
        shared_kubeflow_repo: A repository with a provisioned local kubeflow
            stack
        clean_repo: An empty repository

    Yields:
        An empty repository with a provisioned local kubeflow stack.
    """
    # Copy the stack configuration from the shared kubeflow repo. At this point
    # the stack resources are already provisioned by the module-scoped fixture.
    kubeflow_stack = shared_kubeflow_repo.active_stack
    clean_repo.register_stack(kubeflow_stack)
    clean_repo.activate_stack(kubeflow_stack.name)

    # Delete the artifact store of previous tests
    if os.path.exists(kubeflow_stack.artifact_store.path):
        shutil.rmtree(kubeflow_stack.artifact_store.path)

    yield clean_repo
