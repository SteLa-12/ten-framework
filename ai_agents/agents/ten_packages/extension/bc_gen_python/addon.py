#
# This file is part of TEN Framework, an open source project.
# Licensed under the Apache License, Version 2.0.
# See the LICENSE file for more information.
#
from ten_runtime import (
    Addon,
    register_addon_as_extension,
    TenEnv,
    LogLevel,
)
from .extension import BCGenPythonExtension


@register_addon_as_extension("bc_gen_python")
class ExtensionAddon(Addon):
    def on_create_instance(
        self, ten_env: TenEnv, name: str, context: object
    ) -> None:
        ten_env.log(LogLevel.INFO, "on_create_instance")
        ten_env.on_create_instance_done(BCGenPythonExtension(name), context)
