from __future__ import annotations

import os
import pathlib

import typer

from bucket.main import emit, fail


SUPPORTED_SHELLS = {"bash", "zsh", "fish", "powershell", "pwsh"}


def _detect_shell() -> str | None:
    shell_path = os.environ.get("SHELL", "")
    if shell_path:
        return pathlib.Path(shell_path).name
    return None


def _resolve_shell(shell: str | None) -> str:
    target = shell or _detect_shell() or ""
    if target not in SUPPORTED_SHELLS:
        supported = ", ".join(sorted(SUPPORTED_SHELLS))
        fail(f"Shell '{target}' is not supported. Supported: {supported}", code=1)
    return target


def register(app: typer.Typer) -> None:
    completion_app = typer.Typer(no_args_is_help=True)

    @completion_app.command("install")
    def install(
        ctx: typer.Context,
        shell: str | None = typer.Option(
            None,
            "--shell",
            help="Shell to install completion for (bash, zsh, fish). Detected automatically if omitted.",
        ),
    ) -> None:
        """Install shell tab completion for bucket."""
        from typer.completion import install as typer_install

        target_shell = _resolve_shell(shell)
        detected_shell, path = typer_install(shell=target_shell, prog_name="bucket")
        msg = f"{detected_shell} completion installed in {path}\n"
        msg += "Completion will take effect once you restart the terminal."
        emit(ctx, {"shell": detected_shell, "path": str(path)}, lambda console: console.print(msg))

    @completion_app.command("show")
    def show(
        ctx: typer.Context,
        shell: str | None = typer.Option(
            None,
            "--shell",
            help="Shell to show completion for (bash, zsh, fish). Detected automatically if omitted.",
        ),
    ) -> None:
        """Print the shell completion script to stdout."""
        from typer.completion import get_completion_script

        target_shell = _resolve_shell(shell)
        complete_var = "_BUCKET_COMPLETE"
        script = get_completion_script(
            prog_name="bucket", complete_var=complete_var, shell=target_shell
        )
        emit(ctx, {"shell": target_shell, "script": script}, lambda console: console.print(script))

    app.add_typer(completion_app, name="completion")
